"""Portfolio selection — OWNER: Rizve.

STUB. Picks the first `budget` gate-passing designs in a deterministic order so
the pipeline produces a complete result today. That ordering carries no
scientific meaning and every record it picks says so in its rationale.

What belongs here: four slots, four *distinct hypotheses*. S-tier requires all
three axes at once, so the real objective is the expected count of designs that
win on three axes simultaneously — not a top-N sort on predicted affinity, and
never four variants of one parent. Cluster first, then take the best of each
cluster, then justify all four.
"""

from __future__ import annotations

from ..schema import AXES, DesignRecord

STUB_RATIONALE = (
    "STUB SELECTION — ordered by design_id among gate-passing records. "
    "No axis prediction informed this choice."
)


def joint_score(rec: DesignRecord) -> float | None:
    """Expected-S-tier proxy: a design is only as good as its weakest axis.

    A product (not a mean) because S-tier needs all three at once — a design
    that is excellent on two axes and hopeless on the third is not a candidate.
    Returns None while any axis is unscored.
    """
    vals = [rec.axes.get(a) for a in AXES]
    if any(v is None for v in vals):
        return None
    score = 1.0
    for v in vals:
        score *= float(v)
    return score


def run(records: list[DesignRecord], budget: int = 4, **kwargs) -> list[DesignRecord]:
    for rec in records:
        rec.joint_score = joint_score(rec)

    eligible = [r for r in records if r.gates.passed and not r.is_baseline]

    scored = [r for r in eligible if r.joint_score is not None]
    if scored:
        ordered = sorted(scored, key=lambda r: (-r.joint_score, r.design_id))
        stub = False
    else:
        ordered = sorted(eligible, key=lambda r: r.design_id)
        stub = True

    for i, rec in enumerate(ordered[:budget], start=1):
        rec.selected = True
        rec.rank = i
        if stub:
            rec.rationale.append(STUB_RATIONALE)
            rec.kill_criterion = "UNSET — no hypothesis behind this pick yet"
        rec.note("portfolio", f"selected rank {i}/{budget}")

    return records
