#!/usr/bin/env python3
"""Export the trastuzumab baseline row from its refold.

The parent is folded through the identical path as every design (same model, same
template, same seed, same flags), so its confidence metrics are directly
comparable. refold-score is not run on it -- there is no "design" to compare a
refold against -- so binder_plddt is computed from the model's per-atom pLDDT.
That method is verified to reproduce refold-score's own binder_plddt exactly on
designs that did go through refold-score.

Usage:
  python3 -I scripts/export_baseline.py runs/baseline/boltz2 --model boltz2 \
      --out data/generated/baseline.json
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

# The 8 measured reference rows of trastuzumab_her2_spr_all_768.csv.
MEASURED_KD_NM = [0.02851802, 0.0378713, 0.07916459, 0.123, 0.146, 0.152, 0.165, 0.178]
BINDER_CHAIN = "B"


def chain_plddt(path: Path) -> dict[str, float]:
    """Mean per-atom pLDDT (the B-factor column) for each chain."""
    cols: list[str] = []
    in_loop = False
    per: dict[str, list[float]] = {}
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("_atom_site."):
                cols.append(s.split(".", 1)[1].split()[0])
                in_loop = True
                continue
            if in_loop and (s.startswith("ATOM") or s.startswith("HETATM")):
                parts = s.split()
                if len(parts) < len(cols):
                    continue
                rec = dict(zip(cols, parts))
                chain = rec.get("auth_asym_id") or rec.get("label_asym_id")
                try:
                    b = float(rec.get("B_iso_or_equiv", ""))
                except (TypeError, ValueError):
                    continue
                if chain:
                    per.setdefault(chain, []).append(b)
            elif in_loop and s.startswith("#"):
                in_loop = False
    return {c: round(sum(v) / len(v), 4) for c, v in sorted(per.items()) if v}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fold_dir", type=Path, help="e.g. runs/baseline/boltz2")
    ap.add_argument("--model", default="boltz2")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    scores_files = sorted(glob.glob(str(args.fold_dir / "**" / "*_scores.json"), recursive=True))
    model_files = sorted(glob.glob(str(args.fold_dir / "**" / "*_model.cif"), recursive=True))
    if not scores_files or not model_files:
        raise SystemExit(f"no scores/model under {args.fold_dir}")

    scores = json.loads(Path(scores_files[0]).read_text())
    plddt_by_chain = chain_plddt(Path(model_files[0]))

    refold = {
        "model": args.model,
        "iptm": scores.get("interface_predicted_tm_score"),
        "ptm": scores.get("predicted_tm_score"),
        "plddt": scores.get("average_predicted_local_distance_difference_test"),
        "binder_plddt": plddt_by_chain.get(BINDER_CHAIN),
        "ranking_score": scores.get("model_ranking_score"),
        "global_pde": scores.get("global_predicted_distance_error"),
        "plddt_by_chain": plddt_by_chain,
        "_binder_plddt_method": (
            "mean per-atom pLDDT over chain B. Verified to reproduce refold-score's "
            "binder_plddt exactly on designs that went through refold-score."
        ),
        "_min_ipae_absent": (
            "min_ipae is a refold-score output comparing a design to its refold. The "
            "parent has no design to compare against, so it has no min_ipae. Compare "
            "designs to each other on min_ipae, and to the parent on iptm/ptm/plddt."
        ),
    }

    blob = {
        "design_id": "trastuzumab",
        "_what": (
            "The baseline row. Folded through the identical path as every design: same "
            "model, same 1N8Z template, same seed, same flags."
        ),
        "refold": refold,
        "measured_kd_nM": MEASURED_KD_NM,
        "measured_kd_median_nM": 0.1345,
        "_read_this_before_using_iptm": (
            "Boltz-2 ipTM barely separates binders from non-binders. On the 91x91 "
            "Smorodina matrices, 94.3% of shuffled non-binding pairs score ipTM >= 0.7 "
            "(median 0.88) against 99% of cognate pairs (median 0.91). AF3 separates "
            "far better: 3.0% of shuffled vs 47% of cognate at that cutoff. So a design "
            "scoring above this baseline on ipTM has NOT been shown to bind better. Use "
            "refold confidence as a feature, never as the binding score."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    for k in ("iptm", "ptm", "plddt", "binder_plddt", "ranking_score"):
        print(f"  {k:<14} {refold[k]}")


if __name__ == "__main__":
    main()
