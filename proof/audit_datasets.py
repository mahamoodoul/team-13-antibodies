#!/usr/bin/env python3
"""Audit the three provided datasets against the claims in docs/brief.md and docs/plan.md.

Prints a report; writes nothing. Run before trusting any headline number.

Claims under test
  A. 524,346 trastuzumab CDRH3 variants, 3 FACS affinity classes, <=10 mutated positions
  B. ~700 optimisation designs, 190 SPR-measured
  C. 454 VHH-antigen true negatives, 21 with AF3 ipTM >= 0.7, "SPR, no measurable binding"

Usage: python3 audit_datasets.py [--data DIR]
"""

import argparse
import csv
import io
import zipfile
from collections import Counter
from pathlib import Path

DEF_DATA = Path.home() / "data"


def rule(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def audit_facs(data):
    rule("A. FACS CDRH3 variant set  (claim: 524,346 rows, 3 classes, <=10 mutations)")
    zp = data / "her2-trastuzumab" / "tz_her2_facs_3classes_524346.csv.zip"
    if not zp.exists():
        print(f"MISSING {zp}")
        return
    with zipfile.ZipFile(zp) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        cls, ed, n, bad_len = Counter(), Counter(), 0, 0
        seen = set()
        with z.open(name) as fh:
            for row in csv.DictReader(io.TextIOWrapper(fh, "utf-8")):
                n += 1
                cls[row["binding_class"]] += 1
                ed[int(row["edit_distance"])] += 1
                c = row["cdrh3"]
                if len(c) != 10:
                    bad_len += 1
                seen.add(c)
    print(f"rows                : {n:,}   (claim 524,346 -> {'MATCH' if n == 524346 else 'MISMATCH'})")
    print(f"unique cdrh3        : {len(seen):,}   duplicates: {n - len(seen):,}")
    print(f"cdrh3 not 10 aa     : {bad_len:,}")
    print(f"classes             : {dict(cls)}")
    print("edit_distance       : " + ", ".join(f"{k}:{v:,}" for k, v in sorted(ed.items())))
    mx = max(ed)
    print(f"max edit_distance   : {mx}   (claim <=10 -> {'MATCH' if mx <= 10 else 'MISMATCH'})")
    print("\nNOTE  edit_distance is the split axis the plan calls for: hold out high-distance")
    print("      variants so the test set is not a near-neighbour of training.")


def audit_spr(data):
    rule("B. SPR optimisation designs  (claim: ~700 designs, 190 measured)")
    p = data / "her2-trastuzumab" / "trastuzumab_her2_spr_all_768.csv"
    if not p.exists():
        print(f"MISSING {p}")
        return
    rows = list(csv.DictReader(p.open()))
    res = Counter(r["binding_result"] for r in rows)
    kd = [float(r["kd_nM"]) for r in rows if r["kd_nM"].strip()]
    print(f"rows                : {len(rows)}")
    print(f"binding_result      : {dict(res)}")
    print(f"rows with a kd_nM   : {len(kd)}   (claim 190 -> {'MATCH' if len(kd) == 190 else 'MISMATCH'})")
    if kd:
        kd.sort()
        print(f"kd_nM range         : {kd[0]:g} .. {kd[-1]:g} nM   median {kd[len(kd) // 2]:g}")
    cd = Counter(len(r["cdrh3"]) for r in rows)
    print(f"cdrh3 lengths       : {dict(sorted(cd.items()))}")
    print("\nNOTE  this is the held-out validation set: same assay the judges use (SPR).")
    print("      The enrichment number must be computed on these, blind.")


def audit_negatives(data):
    rule("C. VHH-antigen true negatives  (claim: 454 pairs, 21 with AF3 ipTM >= 0.7, SPR)")

    # --- C1: the ipTM cross-pairing matrices (computational) ---
    zp = data / "zenodo-18390239-ab-ag-complexes" / "iptm_confidence_scores.zip"
    print("\nC1. ipTM matrices in iptm_confidence_scores.zip")
    if not zp.exists():
        print(f"MISSING {zp}")
    else:
        with zipfile.ZipFile(zp) as z:
            for model in ("af3", "boltz2", "chai1"):
                nm = f"iptm_confidence_scores/{model}_matrix_clean.csv"
                if nm not in z.namelist():
                    continue
                with z.open(nm) as fh:
                    r = list(csv.reader(io.TextIOWrapper(fh, "utf-8")))
                cols = r[0][1:]
                diag = off = blank = 0
                off_ge = diag_ge = 0
                for line in r[1:]:
                    ab, vals = line[0], line[1:]
                    for c, v in zip(cols, vals):
                        if not v.strip():
                            blank += 1
                            continue
                        x = float(v)
                        if c == ab:
                            diag += 1
                            diag_ge += x >= 0.7
                        else:
                            off += 1
                            off_ge += x >= 0.7
                print(
                    f"  {model:7s} {len(r) - 1} ab x {len(cols)} ag | "
                    f"cognate(diag) {diag:4d} (>=0.7: {diag_ge:3d}) | "
                    f"non-cognate(off-diag) {off:5d} (>=0.7: {off_ge:4d}) | empty {blank}"
                )
        print("  These off-diagonal pairs are SHUFFLED/computational non-binders.")
        print("  They are NOT SPR-measured. No SPR column exists in this archive.")

    # --- C2: the actual SPR measurements ---
    sp = data / "sigma2-ab-ag-champloo" / "spr-supplementary" / "spr_table_s1_pairwise.csv"
    print("\nC2. Actual SPR measurements (spr_table_s1_pairwise.csv)")
    if not sp.exists():
        print(f"MISSING {sp}")
        return
    rows = list(csv.DictReader(sp.open()))
    pt = Counter(r["pair_type"] for r in rows)
    oc = Counter(r["outcome_class"] for r in rows)
    noncog = [r for r in rows if r["pair_type"] == "non-cognate"]
    nofit = [r for r in noncog if "no reportable" in r["outcome_class"]]
    print(f"  rows            : {len(rows)}")
    print(f"  pair_type       : {dict(pt)}")
    print(f"  outcome_class   : {dict(oc)}")
    print(f"  non-cognate     : {len(noncog)}   of which 'no reportable fit': {len(nofit)}")
    have_iptm = [r for r in noncog if r.get("af3_iptm", "").strip()]
    print(f"  non-cognate rows carrying an af3_iptm value: {len(have_iptm)}")

    rule("VERDICT")
    print(f"""
Claim C does not hold as written.

  claimed : 454 VHH-antigen pairs, SPR-measured, no measurable binding,
            21 of them with AF3 ipTM >= 0.7
  actual  : {len(noncog)} non-cognate pairs were SPR-tested, all {len(nofit)} returned
            "no reportable fit". Per-pair AF3 ipTM is tabulated for {len(have_iptm)} of them.

Three separate problems:

1. SCALE. There is no 454-row SPR table. The only SPR data for these complexes is
   Supplementary Table S1 ({len(rows)} rows), extracted from the paper's PDF. The 454 figure
   can only refer to shuffled/computational non-cognate pairs, which carry ipTM but
   no measurement at all.

2. LABEL. The authors state explicitly: "N/A denotes no reportable affinity fit,
   NOT confirmed non-binding." Calling these "measured true negatives" is the
   relabelling they warn against. One design (8fsl_c) expressed very poorly and was
   flagged for discard, so its N/A may be material quality, not absence of binding.

3. THE 21. The paper reports AF3 ipTM 0.75-0.90 for eleven of the twelve non-cognate
   pairs, as printed cells in Supplementary Figure S1B - not as data. Per-pair values
   are not in any archive we hold. "21 with ipTM >= 0.7" is not reproducible from
   what we have.

What survives, and is still a strong result:

  The qualitative claim is intact and is the paper's own headline - high structure
  confidence does not imply binding. We can support it from data we actually hold:
  the off-diagonal ipTM counts in C1 show how many shuffled non-binding pairs clear
  any given confidence cutoff, which is exactly the calibration curve the plan wants.
  Say "shuffled non-cognate pairs, computational" and the claim is airtight.

  There is also a sharper, fully-measured fact in Table S1: 8w90_a binds CD4 at
  7.41 nM with AF3 ipTM 0.12 - a confirmed binder a confidence filter would reject.
  And in the 14-target screen, 8c5h_n bound 11 of 14 targets. One false negative and
  one polyreactive binder, both measured, both named in the paper.

Action: rewrite the proof section of docs/plan.md to cite the shuffled-pair curve for
calibration and Table S1 for the specificity inversion. Do not put "454 measured true
negatives" on a slide - Victor Greiff co-authored this paper and the event is in Oslo.
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEF_DATA)
    a = ap.parse_args()
    print(f"data root: {a.data}")
    audit_facs(a.data)
    audit_spr(a.data)
    audit_negatives(a.data)


if __name__ == "__main__":
    main()
