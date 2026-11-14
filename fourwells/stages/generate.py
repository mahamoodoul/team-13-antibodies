"""Generation — OWNER: Ruhit.

STUB. Produces syntactically valid candidates by mutating the reference CDRH3
so the pipeline runs end to end today. It is not design; every record it emits
is flagged `is_stub=True` and the runner prints a warning.

To make it real, replace `_stub_candidates` with a Foundry call:

    docker run --gpus all quay.io/apheris/oslo-hackathon:\\
        apheris-rfd4-proteina-v0.3.0-her2-novel-2026-11-09 design ...

then refold-prepare -> a Predict Structure model -> refold-score, and return
one DesignRecord per surviving design with `generator` set to the image tag and
`axis_evidence["refold"]` carrying min_ipae / iptm / binder_plddt.

Keep the signature. The runner and every downstream stage depend on it.
"""

from __future__ import annotations

import random

from ..schema import DesignRecord
from ..targets import ReferenceAntibody, Target

AA = "ACDEFGHIKLMNPQRSTVWY"

# The novelty gate needs >=4 of 11 CDRH3 positions changed (<70% identity on an
# 11-mer). The stub deliberately spans that boundary so the gate stage has both
# passing and failing records to chew on from the first run.
_MUTATION_COUNTS = [1, 2, 4, 5, 6, 7]


def _mutate(seq: str, n: int, rng: random.Random) -> str:
    positions = rng.sample(range(len(seq)), min(n, len(seq)))
    out = list(seq)
    for p in positions:
        choices = [a for a in AA if a != out[p]]
        out[p] = rng.choice(choices)
    return "".join(out)


def _stub_candidates(
    n: int, ref: ReferenceAntibody, rng: random.Random
) -> list[DesignRecord]:
    parent_cdrh3 = ref.cdrh3 or "WGGDGFYAMDY"
    vh = ref.vh or ""
    records = []
    for i in range(n):
        muts = _MUTATION_COUNTS[i % len(_MUTATION_COUNTS)]
        cdrh3 = _mutate(parent_cdrh3, muts, rng)
        # Splice the new loop back into the VH so the record carries a real
        # full-length sequence rather than a bare loop.
        seq = vh.replace(parent_cdrh3, cdrh3) if parent_cdrh3 in vh else vh + cdrh3
        rec = DesignRecord(
            design_id=f"stub-{i:03d}",
            sequence=seq or cdrh3,
            track="optimisation",
            format="scfv",
            parent=ref.name,
            generator="STUB:cdrh3-random-mutation",
            cdrh3=cdrh3,
            cdrh3_mutations_from_tras=muts,
            is_stub=True,
        )
        rec.note("generate", f"stub: {muts} random CDRH3 substitutions")
        records.append(rec)
    return records


def run(
    target: Target,
    ref: ReferenceAntibody,
    n: int = 24,
    seed: int = 0,
    cache=None,
    **kwargs,
) -> list[DesignRecord]:
    """Return candidate designs for `target`, to be scored against `ref`."""
    rng = random.Random(seed)
    records = _stub_candidates(n, ref, rng)

    # The baseline travels the identical path so every score has a reference.
    # Do not special-case it downstream — that is the point.
    if ref.vh:
        baseline = DesignRecord(
            design_id="trastuzumab",
            sequence=ref.vh,
            track="optimisation",
            format="scfv",
            parent=ref.name,
            generator="reference",
            cdrh3=ref.cdrh3,
            cdrh3_mutations_from_tras=0,
        )
        baseline.note("generate", "reference baseline, same path as every design")
        records.append(baseline)

    return records
