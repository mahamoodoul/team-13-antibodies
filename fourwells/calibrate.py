"""The structure-confidence cutoff — OWNER: Rizve. Calibrated, not remembered.

The brief promises 454 VHH-antigen pairs "measured not to bind", 21 of them at
AF3 ipTM >= 0.7, and that would be the most valuable thing in the bundle:
direct, measured proof that high structure confidence does not mean binding.

Those measurements are not in the archive. `proof/audit_datasets.py` found no
SPR column in it: what ships is three 91x91 cross-pairing matrices whose
off-diagonal pairs are SHUFFLED — a computational model of non-binding, not an
experiment. 246 of 8,137 shuffled pairs clear AF3 ipTM 0.7, and under Boltz-2
7,723 of 8,190 do. That is still the right curve to calibrate against, and it
still says a team filtering on ipTM >= 0.7 would order non-binders. It is just
not a measurement, so the `basis` argument below records which kind it is and
the scorer treats the two differently.

The one genuinely measured counterexample we do hold is stronger than any
cutoff: 8w90_a binds CD4 at 7.41 nM with AF3 ipTM 0.12. One confirmed binder
that a confidence filter throws away.

So this module exists to make sure we never set that threshold from a round
number someone remembered. Two states, and the scorer behaves differently in
each:

  UNCALIBRATED (today, until the bundle lands)
      Confidence may only LOWER a binding score, never raise it. The asymmetry
      is the whole lesson of those 21 rows: high confidence is not evidence of
      binding, while low confidence is still weak evidence against it. A
      pipeline that cannot yet justify a cutoff should not be allowed to earn
      credit from the number.

  CALIBRATED (once `calibrate` has run over the negatives)
      Confidence enters as (conf - cutoff), where the cutoff is read off the
      curve at a target specificity on the measured non-binders. Only then is
      a high value allowed to help.

Run it:

    python3 -m fourwells.calibrate data/negatives.csv \\
        --positives data/spr_measured.csv --target-specificity 0.95

and it writes data/models/confidence_cutoff.json, which the scorer picks up on
the next run with no code change.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
CUTOFF_FILE = MODEL_DIR / "confidence_cutoff.json"

# The threshold the field reaches for by default, and the one the 21 measured
# non-binders in our own bundle clear. Present here only as the thing we are
# refusing to trust without evidence.
FOLKLORE_CUTOFF = 0.70

# Column names we will accept for the confidence value and the label, in
# preference order. The bundle's exact header is unknown until it is unpacked,
# and guessing wrong silently is worse than failing loudly.
CONF_COLUMNS = ("iptm", "ipTM", "af3_iptm", "iptm_af3", "confidence", "min_ipae_inv")
LABEL_COLUMNS = ("binds", "label", "is_binder", "binder", "measured_binding")


# Not all non-binders are equal evidence. A molecule MEASURED not to bind is a
# fact about the world; a shuffled antigen-antibody pair is a computational
# decoy that was never expected to bind, and separating those is an easier
# problem than the one we face. Only a measured basis unlocks letting
# confidence raise a binding score.
MEASURED, COMPUTATIONAL = "measured", "computational"


@dataclass
class ConfidencePolicy:
    cutoff: float | None
    calibrated: bool
    meta: dict
    basis: str = MEASURED

    @property
    def trusted(self) -> bool:
        """Whether confidence is allowed to help, not just to hurt."""
        return self.calibrated and self.basis == MEASURED

    def adjustment(self, conf: float) -> tuple[float, str]:
        """Feature value contributed by a structure-confidence number.

        Returns (value, note). The value is added to the binding axis with a
        deliberately small weight; see W_BINDING in stages/score.py.
        """
        if not self.trusted:
            # Clamped at zero from above: high confidence contributes nothing.
            ref = float(self.cutoff) if self.cutoff is not None else FOLKLORE_CUTOFF
            adj = min(0.0, conf - ref)
            if adj == 0.0:
                why = (
                    "uncalibrated"
                    if not self.calibrated
                    else f"calibrated only against {self.basis} non-binders"
                )
                note = (
                    f"confidence {conf:.2f} ignored — {why}, and high confidence "
                    "is not allowed to raise a binding score (246 of 8,137 shuffled "
                    "non-binding pairs clear AF3 ipTM 0.7)"
                )
            else:
                note = (
                    f"confidence {conf:.2f} below the {ref} line, "
                    "counted as weak evidence against binding only"
                )
            return adj, note
        adj = conf - float(self.cutoff)
        return adj, (
            f"confidence {conf:.2f} vs calibrated cutoff {self.cutoff:.3f} "
            f"({self.meta.get('basis', 'measured negatives')})"
        )

    def describe(self) -> dict:
        return {
            "calibrated": self.calibrated,
            "cutoff": self.cutoff,
            "basis": self.basis,
            "policy": (
                "confidence may lower a binding score but never raise it"
                if not self.trusted
                else "confidence enters as (conf - cutoff)"
            ),
            **({"meta": self.meta} if self.meta else {}),
        }


def confidence_policy(path: Path | None = None) -> ConfidencePolicy:
    path = path or CUTOFF_FILE
    if not path.exists():
        return ConfidencePolicy(
            cutoff=None,
            calibrated=False,
            meta={"why": f"{path.name} absent — calibration has not been run"},
        )
    blob = json.loads(path.read_text())
    return ConfidencePolicy(
        cutoff=float(blob["cutoff"]),
        calibrated=True,
        meta=blob.get("meta", {}),
        basis=blob.get("basis", MEASURED),
    )


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def _pick(header: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {h.lower().strip(): h for h in header}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _read_confidences(path: Path, expect_label: bool) -> tuple[list[float], list[int] | None]:
    with open(path, newline="") as fh:
        sniff = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sniff, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        header = reader.fieldnames or []
        conf_col = _pick(header, CONF_COLUMNS)
        if not conf_col:
            raise SystemExit(
                f"{path}: no confidence column found. Looked for {CONF_COLUMNS}; "
                f"header is {header}. Pass the real name with --conf-column."
            )
        label_col = _pick(header, LABEL_COLUMNS) if expect_label else None
        confs: list[float] = []
        labels: list[int] = []
        for row in reader:
            raw = (row.get(conf_col) or "").strip()
            if not raw:
                continue
            try:
                confs.append(float(raw))
            except ValueError:
                continue
            if label_col:
                v = (row.get(label_col) or "").strip().lower()
                labels.append(1 if v in {"1", "true", "yes", "binder", "y"} else 0)
    return confs, (labels or None)


def calibrate(
    negatives: list[float], positives: list[float] | None, target_specificity: float
) -> dict:
    """Pick the cutoff from the measured non-binders.

    Specificity is what we control, because the cost we are avoiding is
    concrete: a non-binder in one of four wells is a quarter of our lab budget
    spent on a molecule already known to fail. We set the cutoff so that
    `target_specificity` of the measured non-binders fall below it, then report
    what that costs in sensitivity if positives are supplied.
    """
    if not negatives:
        raise SystemExit("no negative confidences read — nothing to calibrate against")

    ordered = sorted(negatives)
    idx = min(len(ordered) - 1, int(round(target_specificity * len(ordered))) - 1)
    cutoff = ordered[max(idx, 0)]

    above_folklore = [c for c in negatives if c >= FOLKLORE_CUTOFF]
    rejected_of_those = [c for c in above_folklore if c < cutoff]

    meta: dict = {
        "basis": f"{len(negatives)} measured non-binders, specificity target {target_specificity:.0%}",
        "n_negatives": len(negatives),
        "negatives_at_or_above_folklore": len(above_folklore),
        "folklore_cutoff": FOLKLORE_CUTOFF,
        "of_those_rejected_by_this_cutoff": len(rejected_of_those),
        "achieved_specificity": round(
            sum(1 for c in negatives if c < cutoff) / len(negatives), 4
        ),
    }

    if positives:
        tp = sum(1 for c in positives if c >= cutoff)
        meta["n_positives"] = len(positives)
        meta["sensitivity_at_cutoff"] = round(tp / len(positives), 4)
        meta["sensitivity_at_folklore"] = round(
            sum(1 for c in positives if c >= FOLKLORE_CUTOFF) / len(positives), 4
        )

    # The question the slide actually turns on: could ANY threshold have
    # rejected the confident non-binders, and what would it have cost?
    conclusion = None
    if above_folklore:
        needed = max(above_folklore)
        meta["cutoff_needed_to_reject_all_confident_negatives"] = round(needed, 4)
        if positives:
            survivors = sum(1 for c in positives if c > needed)
            cost = 1 - survivors / len(positives)
            meta["binder_loss_at_that_cutoff"] = round(cost, 4)
            if cost > 0.5:
                conclusion = (
                    f"No usable threshold separates them. Rejecting all "
                    f"{len(above_folklore)} confident non-binders needs a cutoff above "
                    f"{needed:.3f}, which discards {cost:.0%} of measured binders. This is "
                    "the argument for the joint score: those decoys have to be rejected by "
                    "the OTHER axes — epitope and stability — because structure confidence "
                    "cannot do it at any setting. A team that only tunes this threshold "
                    "cannot win this one."
                )
            else:
                conclusion = (
                    f"A cutoff above {needed:.3f} rejects all {len(above_folklore)} "
                    f"confident non-binders for {cost:.0%} of measured binders — "
                    "affordable, so set it there and say what it cost."
                )

    headline = (
        f"A confidence filter at {FOLKLORE_CUTOFF} would have ordered "
        f"{len(above_folklore)} of {len(negatives)} molecules measured NOT to bind. "
        f"Our cutoff of {cutoff:.3f} rejects {len(rejected_of_those)} of those "
        f"{len(above_folklore)}."
    )

    out = {"cutoff": round(cutoff, 4), "meta": meta, "headline": headline}
    if conclusion:
        out["conclusion"] = conclusion
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fourwells.calibrate",
        description="Set the structure-confidence cutoff from measured non-binders",
    )
    ap.add_argument("negatives", type=Path, help="CSV of non-binding pairs; see --basis for whether they are measured")
    ap.add_argument("--positives", type=Path, help="CSV of measured binders, for the sensitivity cost")
    ap.add_argument("--conf-column", help="override the confidence column name")
    ap.add_argument("--target-specificity", type=float, default=0.95)
    ap.add_argument(
        "--basis",
        choices=[MEASURED, COMPUTATIONAL],
        default=MEASURED,
        help="measured: molecules assayed and found not to bind. computational: "
        "shuffled/decoy pairs. Only a measured basis lets confidence raise a score.",
    )
    ap.add_argument("--out", type=Path, default=CUTOFF_FILE)
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args(argv)

    if args.conf_column:
        global CONF_COLUMNS
        CONF_COLUMNS = (args.conf_column,) + CONF_COLUMNS

    neg, neg_labels = _read_confidences(args.negatives, expect_label=True)
    # If the negatives file is actually a mixed table, honour its labels.
    if neg_labels and any(neg_labels):
        pos = [c for c, l in zip(neg, neg_labels) if l == 1]
        neg = [c for c, l in zip(neg, neg_labels) if l == 0]
    else:
        pos = []
    if args.positives:
        extra, _ = _read_confidences(args.positives, expect_label=False)
        pos.extend(extra)

    result = calibrate(neg, pos or None, args.target_specificity)
    result["basis"] = args.basis
    if args.basis == COMPUTATIONAL:
        result["meta"]["basis_caveat"] = (
            "Calibrated against computational decoys, not measured non-binders. "
            "Separating shuffled pairs is an easier problem than the one we face, so "
            "this cutoff may still LOWER a binding score and may not raise one. "
            "Point this at genuinely measured negatives to unlock that."
        )
    print(json.dumps(result, indent=2))
    print("\n" + result["headline"])
    if result.get("conclusion"):
        print("\n" + result["conclusion"])
    print()

    if not args.dry_run:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
