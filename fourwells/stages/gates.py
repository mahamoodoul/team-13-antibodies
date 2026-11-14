"""Entry gates — OWNER: Rizve.

PARTIAL. The rules that are pure string arithmetic are implemented here because
they are unambiguous and the pipeline is worthless without them. The rules that
need `abguard` or a numbering library are stubbed and marked `unchecked`.

Implemented:   length <= 250, no unpaired cysteines, CDRH3 identity vs parent
Stubbed:       immunum numbering confidence, identity to nearest known antibody

Two correctness notes before anyone trusts these numbers:

1. CDRH3 boundaries here are Kabat, taken from data/reference/trastuzumab.json.
   If abguard uses IMGT or Chothia the loop shifts and identity changes.
2. The parent row in the 524k dataset is authoritative. Confirm the reference
   CDRH3 against it and fix the reference file if they disagree.
"""

from __future__ import annotations

from ..schema import DesignRecord
from ..targets import ReferenceAntibody

MAX_LENGTH = 250
MAX_CDRH3_IDENTITY = 0.70  # strictly under
MIN_POINT_MUTATIONS = 2  # strictly more than


def _identity(a: str, b: str) -> float | None:
    """Fraction of identical positions. None if lengths differ.

    Indels would need real alignment; the stub refuses rather than guessing,
    because a wrong identity silently decides whether a design is submittable.
    """
    if not a or not b or len(a) != len(b):
        return None
    same = sum(1 for x, y in zip(a, b) if x == y)
    return same / len(a)


def _unpaired_cysteines(seq: str) -> bool:
    return seq.count("C") % 2 != 0


def check(rec: DesignRecord, ref: ReferenceAntibody) -> DesignRecord:
    failed: list[str] = []
    checks: dict = {}

    # --- length ---
    checks["length"] = len(rec.sequence)
    if len(rec.sequence) > MAX_LENGTH:
        failed.append(f"length {len(rec.sequence)} > {MAX_LENGTH}")

    # --- cysteines ---
    checks["cysteines"] = rec.sequence.count("C")
    if _unpaired_cysteines(rec.sequence):
        failed.append(f"unpaired cysteine (count={rec.sequence.count('C')})")

    # --- CDRH3 identity to the parent ---
    if rec.cdrh3 and ref.cdrh3:
        ident = _identity(rec.cdrh3, ref.cdrh3)
        rec.cdrh3_identity_to_tras = ident
        checks["cdrh3_identity"] = ident
        if ident is None:
            checks["cdrh3_identity_note"] = "length differs — needs real alignment"
        elif not rec.is_baseline:
            if ident >= MAX_CDRH3_IDENTITY:
                failed.append(
                    f"CDRH3 identity {ident:.2f} >= {MAX_CDRH3_IDENTITY} "
                    f"({rec.cdrh3_mutations_from_tras} muts; needs >=4 of 11)"
                )
            muts = rec.cdrh3_mutations_from_tras
            if muts is not None and muts <= MIN_POINT_MUTATIONS:
                failed.append(f"only {muts} point mutations, needs > {MIN_POINT_MUTATIONS}")
    else:
        checks["cdrh3_identity"] = None

    # --- stubbed rules ---
    checks["immunum_confidence"] = "unchecked — needs abguard/immunum"
    checks["identity_to_nearest_known"] = "unchecked — needs the known-antibody DB"

    # The baseline is a reference point, not a submission; it is exempt from the
    # novelty rules by construction but still reports its real measurements.
    if rec.is_baseline:
        failed = [f for f in failed if "identity" not in f and "mutations" not in f]

    rec.gates.passed = not failed
    rec.gates.failed_rules = failed
    rec.gates.checks = checks
    rec.note("gates", "pass" if not failed else f"fail: {'; '.join(failed)}")
    return rec


def run(records: list[DesignRecord], ref: ReferenceAntibody, **kwargs) -> list[DesignRecord]:
    return [check(r, ref) for r in records]
