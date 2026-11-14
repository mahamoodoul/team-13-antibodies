"""The design record — the contract between all four lanes.

FROZEN at 11:00. If you need a field added, say so in #team-13 and we add it
here; do not invent fields in your own stage. Every stage takes a list of
DesignRecord and returns the list enriched.

The rule that keeps us unblocked: any axis may be None while its predictor is
still being built. That is the normal state before 14:00, not an error. Write
your stage against this schema with dummy data and integrate later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

SCHEMA_VERSION = "1.0"

Track = Literal["optimisation", "de_novo"]
Format = Literal["vhh", "scfv", "fab"]

# The three axes the lab actually measures. Scores are *relative to
# trastuzumab*: > 0.5 means we predict it beats the baseline on that axis.
AXES = ("binding", "epitope", "stability")


def distance_cap(nov: dict) -> int | None:
    """The ceiling the export applied to the provided-sequence distance, if any.

    The cap moved from 2 to 3 when the strict reading of the novelty rule was
    adopted, and the key moved with it: `min_substitutions_is_capped_at_2: true`
    became `min_substitutions_is_capped_at: 3`. Both are read so batches
    exported either side of that change describe themselves correctly.
    """
    v = nov.get("min_substitutions_is_capped_at")
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if nov.get("min_substitutions_is_capped_at_2"):
        return 2
    return None


def distance_is_capped(nov: dict) -> bool:
    """Whether this record's distance is a ceiling ("at least N") or an exact value.

    Only a distance that reaches the cap is a ceiling. The export stops
    counting at the cap because the filter only asks whether a design differs
    at N or more positions, so a design reported at the cap may sit far beyond
    it -- but one reported below the cap was measured exactly. Reading the cap
    as "every distance is approximate" understates the close designs; ignoring
    it reports "exactly 3" for a design that may be at 7. Both are wrong in a
    string a judge reads, and they are wrong in opposite directions.
    """
    cap = distance_cap(nov)
    dist = nov.get("min_substitutions_from_any_provided")
    return cap is not None and isinstance(dist, int) and dist >= cap


@dataclass
class Gates:
    """Hard filters. A design that fails any of these never reaches the lab."""

    passed: bool | None = None
    failed_rules: list[str] = field(default_factory=list)
    # Populated by the gate stage so the pitch can show the real numbers.
    checks: dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignRecord:
    design_id: str
    sequence: str

    # --- provenance: who made this and how ---
    track: Track | None = None
    format: Format | None = None
    parent: str | None = None
    generator: str | None = None  # e.g. "rfd4-proteina:her2-novel-2026-11-09"

    # --- identity, the numbers abguard cares about ---
    cdrh3: str | None = None
    cdrh3_identity_to_tras: float | None = None
    identity_to_nearest_known: float | None = None
    cdrh3_mutations_from_tras: int | None = None

    # --- gates ---
    gates: Gates = field(default_factory=Gates)

    # --- prediction: one entry per lab axis, each vs the trastuzumab baseline ---
    axes: dict[str, float | None] = field(
        default_factory=lambda: {a: None for a in AXES}
    )
    axis_evidence: dict[str, Any] = field(default_factory=dict)

    # --- the decision ---
    joint_score: float | None = None
    cluster: str | None = None
    selected: bool = False
    rank: int | None = None

    # --- the dossier, which is 40% of the pitch score ---
    rationale: list[str] = field(default_factory=list)
    kill_criterion: str | None = None

    # --- bookkeeping ---
    stage_log: list[str] = field(default_factory=list)
    is_stub: bool = False

    def note(self, stage: str, msg: str) -> None:
        self.stage_log.append(f"{stage}: {msg}")

    @property
    def is_baseline(self) -> bool:
        return self.design_id == "trastuzumab"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DesignRecord:
        d = dict(d)
        g = d.pop("gates", None) or {}
        rec = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        rec.gates = Gates(**{k: v for k, v in g.items() if k in Gates.__dataclass_fields__})
        return rec


def validate(rec: DesignRecord) -> list[str]:
    """Structural validation only — this is not the gate stage.

    Returns a list of problems; empty means the record is well-formed. We check
    shape, not science, so a record with every axis None is perfectly valid.
    """
    problems: list[str] = []
    if not rec.design_id:
        problems.append("design_id is empty")
    if not rec.sequence:
        problems.append("sequence is empty")
    elif not rec.sequence.isalpha():
        problems.append("sequence contains non-letter characters")
    if rec.track not in (None, "optimisation", "de_novo"):
        problems.append(f"unknown track {rec.track!r}")
    if rec.format not in (None, "vhh", "scfv", "fab"):
        problems.append(f"unknown format {rec.format!r}")
    for axis, val in rec.axes.items():
        if axis not in AXES:
            problems.append(f"unknown axis {axis!r} (expected {AXES})")
        if val is not None and not 0.0 <= float(val) <= 1.0:
            problems.append(f"axis {axis} = {val} outside [0, 1]")
    return problems


def write_jsonl(records: list[DesignRecord], path) -> None:
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r.to_dict(), sort_keys=True) + "\n")


def read_jsonl(path) -> list[DesignRecord]:
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(DesignRecord.from_dict(json.loads(line)))
    return out
