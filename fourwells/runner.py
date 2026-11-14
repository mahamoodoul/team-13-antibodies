"""Stage runner.

Runs the pipeline with a timebox per stage and reports honestly on what is real
and what is still stubbed. The run never silently degrades: if a stage is a
stub, it says so on every line of the summary.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cache import Cache
from .schema import AXES, SCHEMA_VERSION, DesignRecord, validate, write_jsonl
from .stages import gates as gates_stage
from .stages import generate as generate_stage
from .stages import portfolio as portfolio_stage
from .stages import score as score_stage
from .targets import ReferenceAntibody, Target


@dataclass
class StageResult:
    name: str
    seconds: float
    n_in: int
    n_out: int
    note: str = ""


@dataclass
class RunResult:
    records: list[DesignRecord]
    stages: list[StageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def selected(self) -> list[DesignRecord]:
        return sorted(
            [r for r in self.records if r.selected], key=lambda r: r.rank or 999
        )

    @property
    def passed(self) -> list[DesignRecord]:
        return [r for r in self.records if r.gates.passed]


def run_pipeline(
    target: Target,
    ref: ReferenceAntibody,
    budget: int = 4,
    n_candidates: int = 24,
    seed: int = 0,
    cache: Cache | None = None,
    timebox: float = 300.0,
) -> RunResult:
    cache = cache or Cache()
    result = RunResult(records=[])
    result.warnings.extend(ref.warnings)

    def timed(name: str, fn, n_in: int):
        t0 = time.monotonic()
        out = fn()
        dt = time.monotonic() - t0
        result.stages.append(StageResult(name, dt, n_in, len(out)))
        if dt > timebox:
            result.warnings.append(f"stage {name} took {dt:.1f}s, over its {timebox}s box")
        return out

    records = timed(
        "generate",
        lambda: generate_stage.run(target, ref, n=n_candidates, seed=seed, cache=cache),
        0,
    )
    records = timed("gates", lambda: gates_stage.run(records, ref), len(records))
    records = timed(
        "score", lambda: score_stage.run(records, target, ref, cache=cache), len(records)
    )
    records = timed(
        "portfolio", lambda: portfolio_stage.run(records, budget=budget), len(records)
    )

    # Structural validation — shape, not science.
    for rec in records:
        problems = validate(rec)
        if problems:
            result.warnings.append(f"{rec.design_id}: {'; '.join(problems)}")

    n_stub = sum(1 for r in records if r.is_stub)
    if n_stub:
        result.warnings.append(
            f"{n_stub}/{len(records)} records came from the STUB generator — "
            "these are not designs"
        )
    unscored = sum(1 for r in records if any(r.axes.get(a) is None for a in AXES))
    if unscored:
        result.warnings.append(
            f"{unscored}/{len(records)} records have unscored axes — "
            "selection is not yet evidence-based"
        )

    result.records = records
    return result


def git_sha() -> str:
    """The commit this run came from. 'unknown' if we are not in a git checkout.

    A ranked list nobody can tie back to a revision is not reproducible, and the
    20% execution score is exactly that claim.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=5,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and sha:
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=Path(__file__).resolve().parent,
                capture_output=True, text=True, timeout=5,
            )
            return sha + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def make_run_id(config: dict[str, Any]) -> str:
    """Timestamp plus a short hash of the inputs.

    The timestamp keeps successive runs from overwriting each other; the hash
    makes it obvious at a glance when two runs had identical inputs, which is
    how we spot an accidental re-run during the demo.
    """
    basis = json.dumps(
        {k: config.get(k) for k in ("target", "reference", "budget", "candidates", "seed")},
        sort_keys=True,
    )
    digest = hashlib.sha256(basis.encode()).hexdigest()[:8]
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{digest}"


def write_outputs(
    result: RunResult,
    out_dir: Path,
    config: dict[str, Any] | None = None,
    run_id: str | None = None,
    report: bool = True,
) -> dict[str, Path]:
    """Write one run into its own directory. Never overwrites a previous run.

    Pass `run_id` to pin the directory name — the tests rely on that, and so does
    anyone comparing two runs byte for byte.
    """
    config = dict(config or {})
    config.setdefault("schema_version", SCHEMA_VERSION)
    config.setdefault("git_sha", git_sha())
    config["warnings"] = list(result.warnings)
    config["stages"] = [
        {"name": s.name, "seconds": round(s.seconds, 3), "n_in": s.n_in, "n_out": s.n_out}
        for s in result.stages
    ]
    config["run_id"] = run_id or config.get("run_id") or make_run_id(config)

    out_dir = Path(out_dir) / config["run_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "config": out_dir / "config.json",
        "all": out_dir / "designs.jsonl",
        "selected": out_dir / "selected.jsonl",
    }
    paths["config"].write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    write_jsonl(result.records, paths["all"])
    write_jsonl(result.selected, paths["selected"])

    if report:
        # Imported here so a failure in the renderer can never stop a run from
        # saving its records. The JSONL is the evidence; the report is a view of it.
        from . import report as report_mod

        try:
            paths["report_md"] = out_dir / "report.md"
            paths["report_md"].write_text(
                report_mod.render_markdown(
                    result.records, result.selected, config, result.warnings
                )
            )
            paths["report_html"] = out_dir / "report.html"
            paths["report_html"].write_text(
                report_mod.render_html(
                    result.records, result.selected, config, result.warnings
                )
            )
        except Exception as exc:  # noqa: BLE001 — a bad view must not lose the data
            result.warnings.append(
                f"report rendering failed ({exc.__class__.__name__}: {exc}); "
                f"records are still in {paths['all']}. Re-render with "
                f"`python3 -m fourwells.report {out_dir}`"
            )
            paths.pop("report_md", None)
            paths.pop("report_html", None)

    return paths
