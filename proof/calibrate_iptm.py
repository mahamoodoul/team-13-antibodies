#!/usr/bin/env python3
"""Calibrate a structure-confidence cutoff from measured separability, not a round number.

The plan called for this using "454 SPR-measured true negatives". That set does not
exist — see audit_datasets.py. What we do hold is the Champloo cross-pairing matrices:
91 cognate VHH-antigen pairs (known binders) against ~8,100 shuffled pairs per model.
Shuffled pairs are computational non-binders, not measurements, and we say so.

That is still exactly the curve we need: for each model, how much cognate signal does a
confidence cutoff keep, and how many shuffled pairs does it let through?

Outputs:
  iptm_calibration.csv   per model, per cutoff: TPR, FPR, precision, Youden J
  iptm_calibration.md    the readable result, with the recommended cutoff per model

Usage: python3 calibrate_iptm.py [--tidy DIR] [--out DIR]
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

NAIVE = 0.7  # the round number the plan assumed
TARGET_FPR = 0.05  # "let through at most 5% of shuffled pairs"


def auc(pos, neg):
    """Mann-Whitney U / ROC AUC, ties counted as half."""
    s = sorted([(x, 1) for x in pos] + [(x, 0) for x in neg])
    rank, i, rsum = 0, 0, 0.0
    while i < len(s):
        j = i
        while j < len(s) and s[j][0] == s[i][0]:
            j += 1
        avg = (i + j + 1) / 2  # average 1-based rank of the tie block
        for k in range(i, j):
            if s[k][1] == 1:
                rsum += avg
        i = j
    n1, n0 = len(pos), len(neg)
    return (rsum - n1 * (n1 + 1) / 2) / (n1 * n0)


def curve(pos, neg):
    """Sweep every observed value as a cutoff."""
    out = []
    for c in sorted({round(x, 3) for x in pos + neg}):
        tp = sum(x >= c for x in pos)
        fp = sum(x >= c for x in neg)
        tpr = tp / len(pos)
        fpr = fp / len(neg)
        out.append(
            {
                "cutoff": c,
                "cognate_kept": tp,
                "cognate_total": len(pos),
                "tpr": round(tpr, 4),
                "shuffled_passed": fp,
                "shuffled_total": len(neg),
                "fpr": round(fpr, 4),
                "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
                "youden_j": round(tpr - fpr, 4),
            }
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", type=Path, default=Path.home() / "mahamodul" / "proof" / "tidy")
    ap.add_argument("--out", type=Path, default=Path.home() / "mahamodul" / "proof" / "tidy")
    a = ap.parse_args()

    vals = defaultdict(lambda: defaultdict(list))
    with (a.tidy / "iptm_pairs.csv").open() as fh:
        for r in csv.DictReader(fh):
            vals[r["model"]][r["pair_type"]].append(float(r["iptm"]))

    rows, summary = [], {}
    for model in ("af3", "boltz2", "chai1"):
        pos, neg = vals[model]["cognate"], vals[model]["non_cognate"]
        if not pos or not neg:
            continue
        cv = curve(pos, neg)
        for r in cv:
            rows.append({"model": model, **r})

        best = max(cv, key=lambda r: r["youden_j"])
        ok = [r for r in cv if r["fpr"] <= TARGET_FPR]
        at_fpr = min(ok, key=lambda r: r["cutoff"]) if ok else None
        naive = min(cv, key=lambda r: abs(r["cutoff"] - NAIVE))
        summary[model] = {
            "auc": auc(pos, neg),
            "best": best,
            "at_fpr": at_fpr,
            "naive": naive,
            "n_pos": len(pos),
            "n_neg": len(neg),
            "pos_med": sorted(pos)[len(pos) // 2],
            "neg_med": sorted(neg)[len(neg) // 2],
        }

    with (a.out / "iptm_calibration.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    L = []
    A = L.append
    A("# Calibrating a structure-confidence cutoff\n")
    A("91 cognate VHH-antigen pairs (known binders) vs ~8,100 **shuffled** pairs per model.")
    A("Shuffled pairs are computational non-binders from the Champloo benchmark, not")
    A("measurements. Source: Smorodina et al., bioRxiv 2026, doi 10.64898/2026.03.02.709004.\n")

    A("## How well does ipTM separate binders from shuffled pairs at all?\n")
    A("| Model | AUC | Cognate median | Shuffled median | Verdict |")
    A("| --- | --- | --- | --- | --- |")
    for m, s in summary.items():
        v = ("usable" if s["auc"] >= 0.8 else "weak" if s["auc"] >= 0.65 else "near-useless")
        A(f"| {m} | **{s['auc']:.3f}** | {s['pos_med']:.2f} | {s['neg_med']:.2f} | {v} |")

    A(f"\n## What the round number ({NAIVE}) actually does\n")
    A("| Model | Cognate kept | Shuffled passed | Precision |")
    A("| --- | --- | --- | --- |")
    for m, s in summary.items():
        n = s["naive"]
        A(f"| {m} | {n['cognate_kept']}/{n['cognate_total']} ({100 * n['tpr']:.0f}%) | "
          f"{n['shuffled_passed']:,}/{n['shuffled_total']:,} ({100 * n['fpr']:.0f}%) | "
          f"{n['precision']:.3f} |")
    A("\nThe same number means three different things. This is the finding.\n")

    A("## Recommended cutoff per model\n")
    A(f"Two defensible rules: maximise Youden's J, or hold shuffled pass-through at "
      f"<={100 * TARGET_FPR:.0f}%.\n")
    A("| Model | Best J cutoff | Cognate kept | Shuffled passed | Cutoff at <=5% shuffled | Cognate kept there |")
    A("| --- | --- | --- | --- | --- | --- |")
    for m, s in summary.items():
        b, t = s["best"], s["at_fpr"]
        tc = f"{t['cutoff']:.2f}" if t else "unreachable"
        tk = f"{t['cognate_kept']}/{t['cognate_total']} ({100 * t['tpr']:.0f}%)" if t else "—"
        A(f"| {m} | **{b['cutoff']:.2f}** | {b['cognate_kept']}/{b['cognate_total']} "
          f"({100 * b['tpr']:.0f}%) | {b['shuffled_passed']:,} ({100 * b['fpr']:.1f}%) | {tc} | {tk} |")

    A("\n## What to do with this\n")
    best_model = max(summary, key=lambda m: summary[m]["auc"])
    bs = summary[best_model]
    n = 1

    near = abs(bs["best"]["cutoff"] - NAIVE) < 0.03
    A(f"{n}. **Gate on {best_model} ipTM only.** It is the one model here that separates")
    A(f"   binders from shuffled pairs at all (AUC {bs['auc']:.3f}), and even that is weak.")
    if near:
        A(f"   Its best cutoff, {bs['best']['cutoff']:.2f}, sits within noise of the round")
        A(f"   {NAIVE:.2f} — so {NAIVE:.2f} is defensible for {best_model}, but now we can say *why*,")
        A(f"   and we know its price: it keeps only {100 * bs['best']['tpr']:.0f}% of known binders.")
    else:
        A(f"   Use {bs['best']['cutoff']:.2f}, not {NAIVE:.2f}: the round number keeps "
          f"{100 * bs['naive']['tpr']:.0f}% of binders")
        A(f"   and passes {100 * bs['naive']['fpr']:.0f}% of shuffled pairs.")
    n += 1

    # Each weak model fails differently - name the failure mode that actually applies.
    for m, s in summary.items():
        if m == best_model:
            continue
        nv = s["naive"]
        if nv["fpr"] > 0.5:
            why = (f"at {NAIVE:.2f} it admits {100 * nv['fpr']:.0f}% of shuffled pairs "
                   f"({nv['shuffled_passed']:,} of {nv['shuffled_total']:,}) - it rejects almost nothing")
        elif nv["tpr"] < 0.3:
            why = (f"at {NAIVE:.2f} it discards {100 * (1 - nv['tpr']):.0f}% of *known binders* "
                   f"(keeps {nv['cognate_kept']}/{nv['cognate_total']}) - its whole distribution "
                   f"sits below {NAIVE:.2f}, so the cutoff is on the wrong scale")
        else:
            why = (f"at {NAIVE:.2f} it keeps {100 * nv['tpr']:.0f}% of binders while passing "
                   f"{100 * nv['fpr']:.0f}% of shuffled pairs")
        A(f"{n}. **Do not gate on {m} ipTM.** AUC {s['auc']:.3f}; {why}.")
        n += 1

    A(f"{n}. **Treat confidence as a weak prior, never a hard gate.** At the best cutoff")
    A(f"   available anywhere here, {100 * bs['best']['fpr']:.1f}% of shuffled pairs still clear it")
    A(f"   while {100 * (1 - bs['best']['tpr']):.0f}% of real binders are thrown away.")
    A("   Rank on the joint score; use confidence to break ties, not to exclude.\n")

    A("## Honest limits\n")
    A("- Shuffled pairs are computational non-binders, not SPR measurements. They are a")
    A("  model of non-binding, and the curve inherits that assumption.")
    A("- 91 cognate pairs is a small positive set; the cutoffs carry real uncertainty.")
    A("- This is VHH-antigen data, not trastuzumab-HER2. It calibrates how much to trust")
    A("  a confidence score in general, not HER2 binding specifically.")
    A("- The measured counterexample is stronger than any of this: 8w90_a binds CD4 at")
    A("  7.41 nM with AF3 ipTM 0.12. One confirmed binder a confidence filter throws away.")

    p = a.out / "iptm_calibration.md"
    p.write_text("\n".join(L) + "\n")

    print(f"wrote {a.out / 'iptm_calibration.csv'} ({len(rows)} cutoff rows)")
    print(f"wrote {p}\n")
    for m, s in summary.items():
        print(f"{m:7s} AUC {s['auc']:.3f}  best cutoff {s['best']['cutoff']:.2f} "
              f"(keeps {100 * s['best']['tpr']:.0f}% cognate, passes {100 * s['best']['fpr']:.1f}% shuffled)")


if __name__ == "__main__":
    main()
