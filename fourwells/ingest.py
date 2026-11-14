"""Adapt the generation export into design records — OWNER: Rizve.

`scripts/export_batch.py` writes a richer row than the frozen schema holds:
`novelty`, `design_metrics` and `refold` blocks computed on the VM where the
525,063-sequence provided universe and the folding models actually live.
`DesignRecord.from_dict` filters to known fields, so loading that export
directly **silently discards all three** — the novelty verdict, the Foundry
design metrics and the refold confidence. This module is the seam that moves
them into the places the schema already has for them, so nothing is lost and
no new schema fields are invented:

    novelty        -> gates.checks["novelty"]  (+ the identity fields)
    refold         -> axis_evidence["confidence"]  (the binding/stability axes)
    design_metrics -> axis_evidence["design_metrics"]

    python3 -m fourwells.ingest runs/optA/designs.jsonl --out gated.jsonl

WHY THE NOVELTY VERDICT IS TAKEN FROM GENERATION AND NOT RECOMPUTED: the rule
is distance from *every* provided sequence, and all 525,063 of them are on the
VM. The export tests it by enumerating the loop's own substitution
neighbourhood — ~190 set lookups instead of 525,063 string comparisons, exact
rather than approximate — which is the right algorithm and is already written.
Recomputing it here against a reference set we do not have would be worse than
useless; it would be reassuring.

THE ONE PLACE WE DO NOT TAKE ITS WORD. See `novelty_verdict` below: the export
caps its distance at 2 and treats 2 as passing, while the rule we are gating on
is "more than 2 point mutations from any provided antibody". A capped value of
2 means "2 or more", so it cannot distinguish a design that fails the rule from
one that passes it. We fail those closed and name the reason, rather than
submit on a number that cannot answer the question.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .schema import DesignRecord

LINKER = "GGGGSGGGGSGGGGS"

# The rule, as the project states it: strictly more than 2 point mutations from
# any provided antibody. So 3 is the minimum passing distance.
MIN_DISTANCE_FROM_PROVIDED = 3


def novelty_verdict(nov: dict[str, Any]) -> tuple[bool | None, str]:
    """(passes, reason) for the provided-sequence distance rule.

    Returns None for "cannot be decided from this data", which the gate stage
    treats as a failure rather than a pass. Fail-closed is the only safe
    direction here: the cost of wrongly rejecting a design is one slot in a
    shortlist of twenty, and the cost of wrongly accepting one is a submission
    the organisers throw out.
    """
    dist = nov.get("min_substitutions_from_any_provided")
    capped = nov.get("min_substitutions_is_capped_at_2")

    if dist is None:
        return None, (
            "provided-sequence distance not computed by the export "
            "(provided_cdrh3_universe.txt missing on the generation box)"
        )
    if nov.get("in_provided_data") or dist == 0:
        return False, "CDRH3 is already in the provided data — a known binder fails novelty"
    if dist >= MIN_DISTANCE_FROM_PROVIDED:
        return True, f"{dist} substitutions from the nearest provided sequence"
    if capped and dist == 2:
        # "2 or more" — could be 2 (fails) or 3+ (passes). Undecidable.
        return None, (
            "export reports '2 or more' substitutions from the nearest provided "
            "sequence, capped at 2. The rule needs MORE than 2, so this cannot be "
            "decided from the export. Re-run export_batch.py with the cap raised to "
            f"{MIN_DISTANCE_FROM_PROVIDED} to resolve it"
        )
    return False, (
        f"only {dist} substitution(s) from the nearest provided sequence, "
        f"needs >= {MIN_DISTANCE_FROM_PROVIDED}"
    )


def refold_confidence(refold: dict[str, Any] | None) -> dict[str, Any]:
    """Map the refold block into the shape the axis predictors read.

    `refold_disagreement` is the signal that matters most and the one the
    folding model's own confidence cannot give us: a model handed only the
    sequence must recover the designed complex, and backbone RMSD against the
    design is how far it failed to. A design whose refold diverges from its
    intended complex is a bad bet however good its design score looked.
    """
    if not refold:
        return {}
    out: dict[str, Any] = {}
    for key in ("iptm", "ptm", "min_ipae", "binder_plddt", "plddt", "binder_ptm", "model"):
        if refold.get(key) is not None:
            out[key] = refold[key]
    rmsd = refold.get("backbone_rmsd")
    if rmsd is not None:
        try:
            # Normalised to roughly 0..1 over a 0-10 A range so it reads as a
            # feature rather than as angstroms. 2 A is a clean recovery.
            out["refold_disagreement"] = round(min(max(float(rmsd) - 2.0, 0.0) / 8.0, 1.0), 4)
            out["backbone_rmsd"] = float(rmsd)
        except (TypeError, ValueError):
            pass
    if refold.get("pass") is not None:
        out["refold_pass"] = refold["pass"]
        out["refold_pass_note"] = refold.get("pass_note")
    return out


def to_record(row: dict[str, Any]) -> DesignRecord:
    """One export row -> one DesignRecord, losing nothing we can place."""
    vh = (row.get("vh") or "").strip().upper()
    vl = (row.get("vl") or "").strip().upper()
    seq = row.get("sequence") or (vh + LINKER + vl if vh and vl else vh or vl)

    rec = DesignRecord(
        design_id=row.get("design_id") or row.get("example_id") or "unnamed",
        sequence=seq,
        track=row.get("track"),
        format=row.get("format"),
        parent=row.get("parent"),
        generator=row.get("generator") or row.get("weight"),
        cdrh3=(row.get("cdrh3") or "").strip().upper() or None,
    )

    nov = row.get("novelty") or {}
    if nov:
        passes, reason = novelty_verdict(nov)
        rec.gates.checks["novelty"] = {
            **nov,
            "verdict": "pass" if passes else ("undecidable" if passes is None else "fail"),
            "reason": reason,
        }
        if nov.get("mutations_from_parent") is not None:
            rec.cdrh3_mutations_from_tras = nov["mutations_from_parent"]
        if nov.get("identity_to_parent") is not None:
            rec.cdrh3_identity_to_tras = nov["identity_to_parent"]

    conf = refold_confidence(row.get("refold"))
    if conf:
        rec.axis_evidence["confidence"] = conf
    if row.get("design_metrics"):
        rec.axis_evidence["design_metrics"] = row["design_metrics"]

    # Carry the hotspot signal where the epitope axis can see it. Foundry's
    # hotspot_obedience says whether the design actually engaged the residues
    # it was conditioned on, which for a de novo design is the whole question.
    obedience = (row.get("design_metrics") or {}).get("hotspot_obedience")
    if obedience is not None:
        rec.axis_evidence["hotspot_obedience"] = obedience

    rec.note("ingest", f"from generation export ({len(nov)} novelty fields, {len(conf)} refold)")
    return rec


def read_export(path: Path) -> list[DesignRecord]:
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            out.append(to_record(json.loads(line)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fourwells.ingest", description=__doc__)
    ap.add_argument("export", type=Path, help="designs.jsonl from scripts/export_batch.py")
    ap.add_argument("--out", type=Path, help="write schema-shaped records here")
    args = ap.parse_args(argv)

    recs = read_export(args.export)
    print(f"{len(recs)} records from {args.export}")

    verdicts: dict[str, int] = {}
    for r in recs:
        v = (r.gates.checks.get("novelty") or {}).get("verdict", "absent")
        verdicts[v] = verdicts.get(v, 0) + 1
    print("novelty verdicts:", verdicts)
    if verdicts.get("undecidable"):
        print(
            f"\n  {verdicts['undecidable']} design(s) cannot be decided on the provided-"
            "sequence rule.\n  The export caps its distance at 2 and the rule needs more "
            "than 2. These fail\n  closed. Raise the cap in scripts/export_batch.py to "
            "resolve them."
        )
    n_conf = sum(1 for r in recs if r.axis_evidence.get("confidence"))
    print(f"refold confidence present on {n_conf}/{len(recs)}")

    if args.out:
        from .schema import write_jsonl

        write_jsonl(recs, args.out)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
