"""Generation — OWNER: Ruhit.

Candidates come from Apheris Foundry: RFD4-Proteina redesigns trastuzumab's CDRH3
against HER2 domain IV, a folding model refolds the result, and refold-score says
whether the folding model agrees with the design.

That pipeline needs an H100 and 15 GB of Docker images, so it does not run on a
judge's laptop. This stage therefore has three paths, in order of preference:

1. **replay** (the default) — read batches committed under `data/generated/`. These
   are real Foundry designs with their real refold metrics, exported from the VM by
   `scripts/export_batch.py`. Offline, deterministic, under a second.
2. **live** — run Foundry over Docker, for use on the VM. `live=True`.
3. **stub** — random CDRH3 substitutions, only if no batch is committed and Docker
   is unavailable. Every record is flagged `is_stub=True` so nothing downstream can
   mistake it for a design.

The baseline travels the identical path. `trastuzumab` is emitted as an ordinary
record carrying its own refold metrics, so every axis has a reference row.

Generation is deliberately thin: it supplies candidates and the refold evidence,
and makes no ranking decisions. Those belong to the gate and scoring stages.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

from ..schema import DesignRecord
from ..targets import ReferenceAntibody, Target

AA = "ACDEFGHIKLMNPQRSTVWY"

BATCH_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "generated"

# The CDRH3 sits between these two framework anchors in the trastuzumab VH:
#   ...LRAEDTAV-YYCSR-[WGGDGFYAMD]-YWGQGT-LVTVSS
# Only the loop between them is designed, so this recovers it whatever its length.
CDRH3_PREFIX = "YYCSR"
CDRH3_SUFFIX = "YWGQGT"

# The stub spans the novelty boundary (>=4 of 10 positions changed) so the gate
# stage sees both passing and failing records on its very first run.
_MUTATION_COUNTS = [1, 2, 4, 5, 6, 7]


# --------------------------------------------------------------------------- #
# sequence helpers
# --------------------------------------------------------------------------- #

def extract_cdrh3(vh: str) -> str | None:
    """Pull the designed loop out of a full VH by its flanking framework.

    Returns None rather than guessing if either anchor is missing, so a design we
    cannot parse is dropped loudly instead of scored on a wrong loop.
    """
    if not vh:
        return None
    i = vh.find(CDRH3_PREFIX)
    if i < 0:
        return None
    start = i + len(CDRH3_PREFIX)
    # rfind: the suffix is terminal framework, so the last match is the real one
    # even in the unlikely case that the designed loop contains it too.
    j = vh.rfind(CDRH3_SUFFIX)
    if j <= start:
        return None
    return vh[start:j]


def hamming(a: str, b: str) -> int | None:
    """Substitutions between two equal-length loops; None if lengths differ."""
    if a is None or b is None or len(a) != len(b):
        return None
    return sum(1 for x, y in zip(a, b) if x != y)


def _identity(a: str, b: str) -> float | None:
    d = hamming(a, b)
    if d is None:
        return None
    return round(1.0 - d / len(a), 4)


def _splice(vh: str, old_loop: str, new_loop: str) -> str:
    """Put a new loop into a VH between the framework anchors."""
    i = vh.find(CDRH3_PREFIX)
    j = vh.rfind(CDRH3_SUFFIX)
    if i < 0 or j <= i:
        return vh.replace(old_loop, new_loop) if old_loop in vh else vh + new_loop
    return vh[: i + len(CDRH3_PREFIX)] + new_loop + vh[j:]


# --------------------------------------------------------------------------- #
# path 1: replay committed Foundry batches
# --------------------------------------------------------------------------- #

def _batch_files(batch_dir: Path) -> list[Path]:
    if not batch_dir.is_dir():
        return []
    return sorted(p for p in batch_dir.glob("*.jsonl") if p.is_file())


def _record_from_row(row: dict, ref: ReferenceAntibody) -> DesignRecord | None:
    """Turn one exported Foundry design into a DesignRecord."""
    vh = (row.get("vh") or row.get("binder_sequence") or "").strip().upper()
    cdrh3 = (row.get("cdrh3") or extract_cdrh3(vh) or "").strip().upper() or None
    if not vh or not cdrh3:
        return None

    parent_loop = ref.cdrh3
    muts = hamming(cdrh3, parent_loop)

    rec = DesignRecord(
        design_id=row["design_id"],
        sequence=vh,
        track=row.get("track", "optimisation"),
        format=row.get("format", "scfv"),
        parent=row.get("parent", ref.name),
        generator=row.get("generator"),
        cdrh3=cdrh3,
        cdrh3_identity_to_tras=_identity(cdrh3, parent_loop),
        cdrh3_mutations_from_tras=muts,
    )

    # Refold evidence. This is the generator's honest signal about its own output:
    # whether a folding model, given only the sequence, recovers the designed
    # complex. The scoring stage uses it as a FEATURE, never as the score --
    # Boltz-2 ipTM in particular barely separates real binders from shuffled
    # non-binding pairs (94.3% of known non-binders clear 0.7), so a high ipTM
    # here means much less than it looks like.
    refold = row.get("refold") or {}
    if refold:
        rec.axis_evidence["refold"] = refold

    design_metrics = row.get("design_metrics") or {}
    if design_metrics:
        rec.axis_evidence["design"] = design_metrics

    if row.get("vl"):
        rec.axis_evidence["vl"] = row["vl"]

    src = row.get("batch") or "foundry"
    if muts is None:
        rec.note("generate", f"{src}: CDRH3 {cdrh3} ({len(cdrh3)} aa), length differs from parent")
    else:
        rec.note("generate", f"{src}: CDRH3 {cdrh3}, {muts} substitutions from the parent loop")
    if refold:
        bits = ", ".join(
            f"{k}={v}" for k, v in refold.items() if k in ("model", "min_ipae", "iptm", "binder_plddt")
        )
        if bits:
            rec.note("generate", f"refold {bits}")
    return rec


def _replay(batch_dir: Path, ref: ReferenceAntibody) -> tuple[list[DesignRecord], list[str]]:
    records: list[DesignRecord] = []
    sources: list[str] = []
    seen: set[str] = set()
    for path in _batch_files(batch_dir):
        n_before = len(records)
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = _record_from_row(json.loads(line), ref)
            if rec is None or rec.design_id in seen:
                continue
            seen.add(rec.design_id)
            records.append(rec)
        if len(records) > n_before:
            sources.append(f"{path.name} ({len(records) - n_before})")
    return records, sources


# --------------------------------------------------------------------------- #
# path 2: live Foundry over Docker (VM only)
# --------------------------------------------------------------------------- #

def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _live(
    n: int, seed: int, weight: str, work_dir: Path, tsr_k: str | None = None
) -> list[dict]:
    """Run design -> refold-prepare -> fold -> refold-score, then export rows.

    Returns exported rows in the same shape as a committed batch, so the replay
    path and the live path produce identical records.
    """
    script = work_dir / "scripts" / "run_pipeline.sh"
    if not script.exists():
        raise FileNotFoundError(
            f"{script} not found. The live path runs on the hackathon VM, where "
            "~/ruhit/gen holds the Foundry scripts. Use the committed batches "
            "instead (the default), or pass work_dir."
        )
    env_bits = [f"WEIGHT={weight}", f"N={n}", f"SEED={seed}"]
    if tsr_k:
        env_bits.append(f"TSRK={tsr_k}")
    out = work_dir / "runs" / f"live-{weight}-s{seed}"
    env_bits.append(f"OUT=runs/live-{weight}-s{seed}")
    from .. import calllog

    with calllog.active().call(
        "foundry", "run_pipeline", stage="generate",
        request={"env": env_bits, "script": str(script), "cwd": str(work_dir)},
    ) as slot:
        proc = subprocess.run(
            ["env", *env_bits, "bash", str(script), "all"],
            cwd=work_dir, check=True, capture_output=True, text=True,
        )
        slot["response"] = {
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    export = out / "designs.jsonl"
    if not export.exists():
        raise RuntimeError(f"live run finished but {export} is missing")
    return [json.loads(l) for l in export.read_text().splitlines() if l.strip()]


# --------------------------------------------------------------------------- #
# path 3: stub
# --------------------------------------------------------------------------- #

def _mutate(seq: str, n: int, rng: random.Random) -> str:
    positions = rng.sample(range(len(seq)), min(n, len(seq)))
    out = list(seq)
    for p in positions:
        out[p] = rng.choice([a for a in AA if a != out[p]])
    return "".join(out)


def _stub_candidates(n: int, ref: ReferenceAntibody, rng: random.Random) -> list[DesignRecord]:
    parent_cdrh3 = ref.cdrh3 or "WGGDGFYAMD"
    vh = ref.vh or ""
    records = []
    for i in range(n):
        muts = _MUTATION_COUNTS[i % len(_MUTATION_COUNTS)]
        cdrh3 = _mutate(parent_cdrh3, muts, rng)
        seq = _splice(vh, parent_cdrh3, cdrh3) if vh else cdrh3
        rec = DesignRecord(
            design_id=f"stub-{i:03d}",
            sequence=seq or cdrh3,
            track="optimisation",
            format="scfv",
            parent=ref.name,
            generator="STUB:cdrh3-random-mutation",
            cdrh3=cdrh3,
            cdrh3_identity_to_tras=_identity(cdrh3, parent_cdrh3),
            cdrh3_mutations_from_tras=hamming(cdrh3, parent_cdrh3),
            is_stub=True,
        )
        rec.note("generate", f"stub: {muts} random CDRH3 substitutions, NOT a design")
        records.append(rec)
    return records


# --------------------------------------------------------------------------- #
# the baseline row
# --------------------------------------------------------------------------- #

def _baseline(ref: ReferenceAntibody, batch_dir: Path) -> DesignRecord | None:
    """Trastuzumab as an ordinary record, with its real refold metrics if we have them.

    Do not special-case this downstream. Its whole purpose is to travel the
    identical path so that every number has a reference.
    """
    if not ref.vh:
        return None
    rec = DesignRecord(
        design_id="trastuzumab",
        sequence=ref.vh,
        track="optimisation",
        format="scfv",
        parent=ref.name,
        generator="reference",
        cdrh3=ref.cdrh3,
        cdrh3_identity_to_tras=1.0,
        cdrh3_mutations_from_tras=0,
    )
    path = batch_dir / "baseline.json"
    if path.exists():
        blob = json.loads(path.read_text())
        if blob.get("refold"):
            rec.axis_evidence["refold"] = blob["refold"]
            rec.note("generate", "baseline refolded through the identical path")
        for k in ("measured_kd_nM", "measured_kd_median_nM"):
            if blob.get(k) is not None:
                rec.axis_evidence.setdefault("measured", {})[k] = blob[k]
    else:
        rec.note(
            "generate",
            "reference baseline, same path as every design (no refold metrics committed yet)",
        )
    if ref.vl:
        rec.axis_evidence["vl"] = ref.vl
    return rec


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def run(
    target: Target,
    ref: ReferenceAntibody,
    n: int = 24,
    seed: int = 0,
    cache=None,
    **kwargs,
) -> list[DesignRecord]:
    """Return candidate designs for `target`, to be scored against `ref`.

    kwargs:
      live      run Foundry over Docker instead of replaying (VM only)
      weight    RFD4-Proteina weight for the live path
      tsr_k     sequenceTsrK for the live path (1 most varied, 4 default)
      work_dir  where the Foundry scripts live, for the live path
      batch_dir override the committed batch directory
    """
    batch_dir = Path(kwargs.get("batch_dir") or BATCH_DIR)
    records: list[DesignRecord] = []
    how = "stub"

    if kwargs.get("live"):
        if not _docker_available():
            raise RuntimeError(
                "live=True but Docker is not available. Generation needs the "
                "hackathon VM; drop live= to replay the committed batches."
            )
        rows = _live(
            n=n,
            seed=seed,
            weight=kwargs.get("weight", "her2-novel-2026-11-09"),
            work_dir=Path(kwargs.get("work_dir", ".")),
            tsr_k=kwargs.get("tsr_k"),
        )
        records = [r for r in (_record_from_row(x, ref) for x in rows) if r]
        how = "live"
    else:
        records, sources = _replay(batch_dir, ref)
        if records:
            how = "replay"

    if not records:
        # Last resort. The pipeline must still run end to end for the judges even
        # with no batch committed and no GPU, but it has to be obvious that these
        # are not designs.
        records = _stub_candidates(n, ref, random.Random(seed))
        how = "stub"

    # Deterministic subset. Sorted by design_id first so `n` and `seed` pick the
    # same designs on every machine, which the reproducibility score depends on.
    if how != "stub" and n and len(records) > n:
        records.sort(key=lambda r: r.design_id)
        records = records[:n]

    for rec in records:
        rec.note("generate", f"source: {how}")

    baseline = _baseline(ref, batch_dir)
    if baseline is not None:
        baseline.note("generate", f"source: {how}")
        records.append(baseline)

    return records
