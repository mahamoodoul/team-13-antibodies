"""Stage runner.

Runs the pipeline with a timebox per stage and reports honestly on what is real
and what is still stubbed. The run never silently degrades: if a stage is a
stub, it says so on every line of the summary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .cache import Cache
from .schema import AXES, DesignRecord, validate, write_jsonl
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
    if not ref.matches_target(target):
        result.warnings.append(
            f"reference mismatch: {ref.name} was raised against "
            f"{ref.target_uniprot}, but this run targets {target.identifier} — "
            "the epitope axis is unscorable and every score below is a "
            "sequence-and-structure readout, not a comparison to a real rival"
        )

    unscored = sum(1 for r in records if any(r.axes.get(a) is None for a in AXES))
    if unscored:
        result.warnings.append(
            f"{unscored}/{len(records)} records have unscored axes — "
            "selection is not yet evidence-based"
        )

    result.records = records
    return result


def write_outputs(result: RunResult, out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "all": out_dir / "designs.jsonl",
        "selected": out_dir / "selected.jsonl",
    }
    write_jsonl(result.records, paths["all"])
    write_jsonl(result.selected, paths["selected"])
    return paths
