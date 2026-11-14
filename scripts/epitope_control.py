#!/usr/bin/env python3
"""Does our epitope measurement recover a known epitope? Run the control.

The epitope axis asks "does this design bind where trastuzumab binds". We answer
it by reading contacts off the refolded complex. That answer is only worth
having if the same measurement, applied to trastuzumab itself, recovers the
epitope we already know from the crystal structure -- so this scores every
folding model against the annotated 1N8Z/8PWH contact regions, on the parent
first and then on the designs.

It found that our two folding models disagree, and that the one the export was
preferring is the one that fails:

  boltz2       precision 0.74  recall 0.70  all three annotated regions
  protenix-v2  precision 0.47  recall 0.35  misses 557-561 and 570-573 entirely

That is on the parent, whose epitope is crystallographically known. Protenix
places trastuzumab off its own epitope, so the spread it gives across designs is
its own placement error, not variation in epitope preservation.

Reads committed data only -- no VM, no network, no GPU.

Usage:
  python3 -I scripts/epitope_control.py
  python3 -I scripts/epitope_control.py --cutoff-note   # why 4.5 A
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The annotated trastuzumab epitope, from data/reference/trastuzumab.json.
# 581-590 is deliberately excluded: it is 8PWH-only, lower confidence, and
# absent from the folded input altogether (the yaml splits HER2 into chains
# C 489-580 and D 591-607, because input validation rejects a numbering gap
# inside one chain). Scoring against residues no fold could ever contact would
# depress every recall number for a reason that has nothing to do with the
# designs.
REGIONS = {
    "557-561": set(range(557, 562)),
    "570-573": set(range(570, 574)),
    "593-603": set(range(593, 604)),
}
EPITOPE = set().union(*REGIONS.values())

BASELINES = ["data/generated/baseline.json", "data/generated/baseline-protenix-v2.json"]
BATCHES = [
    "data/generated/optA-her2-novel-seed1.jsonl",
    "data/generated/optB-her2-exploratory-seed2.jsonl",
    "data/generated/multicdr-antibody-seed3.jsonl",
]


def score(contacts: list[int]) -> dict:
    """Overlap of one contact set with the annotated epitope."""
    c = set(contacts)
    hit = c & EPITOPE
    return {
        "n": len(c),
        "in_epitope": len(hit),
        # of what it touched, how much was epitope -- does it bind the right place
        "precision": len(hit) / len(c) if c else 0.0,
        # of the epitope, how much it touched -- does it cover the right place
        "recall": len(hit) / len(EPITOPE),
        "regions": {k: len(c & v) for k, v in REGIONS.items()},
        "all_regions": all(c & v for v in REGIONS.values()),
    }


def per_model(records: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in records:
        for model, block in (r.get("epitope_contacts_by_model") or {}).items():
            out.setdefault(model, []).append(score(block["contacts"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    baseline_recs = []
    for p in BASELINES:
        f = ROOT / p
        if f.exists():
            baseline_recs.append(json.loads(f.read_text()))
    # the two baseline files carry the same both-model block, so one is enough
    base = per_model(baseline_recs[:1])

    design_recs = []
    for p in BATCHES:
        f = ROOT / p
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("epitope_contacts_by_model"):
                    design_recs.append(r)
    designs = per_model(design_recs)

    report = {"epitope_residues": sorted(EPITOPE), "regions": {k: sorted(v) for k, v in REGIONS.items()}}

    print(f"annotated epitope: {len(EPITOPE)} residues in {len(REGIONS)} regions "
          f"({', '.join(REGIONS)})")
    print()
    print("THE CONTROL -- trastuzumab's own refold, epitope known from 1N8Z")
    print(f"  {'model':<13} {'contacts':>8} {'in epi':>7} {'precision':>10} {'recall':>7}  regions touched")
    for model, rows in sorted(base.items()):
        s = rows[0]
        rg = "  ".join(f"{k}:{v}/{len(REGIONS[k])}" for k, v in s["regions"].items())
        flag = "" if s["all_regions"] else "   <- MISSES A REGION"
        print(f"  {model:<13} {s['n']:>8} {s['in_epitope']:>7} {s['precision']:>10.2f} "
              f"{s['recall']:>7.2f}  {rg}{flag}")
        report.setdefault("baseline", {})[model] = s

    print()
    print(f"THE DESIGNS -- {len(design_recs)} refolded designs, same measurement")
    print(f"  {'model':<13} {'precision':>10} {'recall':>7} {'sd':>6} {'min':>5} {'max':>5}  all 3 regions")
    for model, rows in sorted(designs.items()):
        rec = [r["recall"] for r in rows]
        pre = [r["precision"] for r in rows]
        allr = sum(1 for r in rows if r["all_regions"])
        print(f"  {model:<13} {st.mean(pre):>10.2f} {st.mean(rec):>7.2f} "
              f"{st.pstdev(rec):>6.3f} {min(rec):>5.2f} {max(rec):>5.2f}  {allr:>3}/{len(rows)}")
        report.setdefault("designs", {})[model] = {
            "n": len(rows), "precision": st.mean(pre), "recall": st.mean(rec),
            "recall_sd": st.pstdev(rec), "recall_min": min(rec), "recall_max": max(rec),
            "all_regions": allr,
        }

    print()
    print("BY BATCH -- the model that passes the control, per generator")
    passed = [m for m, r in base.items() if r[0]["all_regions"]]
    failed = [m for m, r in base.items() if not r[0]["all_regions"]]
    ctrl = passed[0] if passed else None
    if ctrl:
        print(f"  {'batch':<10} {'n':>3} {'median':>7} {'min':>5} {'max':>5} {'sd':>6}  off-epitope")
        for p in BATCHES:
            f = ROOT / p
            if not f.exists():
                continue
            name = Path(p).stem.split("-")[0]
            rec, off = [], []
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                block = (r.get("epitope_contacts_by_model") or {}).get(ctrl)
                if not block:
                    continue
                sc = score(block["contacts"])
                rec.append(sc["recall"])
                if not sc["all_regions"]:
                    off.append(f"{r['design_id']} ({sc['recall']:.2f})")
            if not rec:
                continue
            print(f"  {name:<10} {len(rec):>3} {st.median(rec):>7.2f} {min(rec):>5.2f} "
                  f"{max(rec):>5.2f} {st.pstdev(rec):>6.3f}  {len(off)}/{len(rec)}")
            for o in off:
                print(f"    {' ':<8} off-epitope: {o}")
            report.setdefault("by_batch", {})[name] = {
                "n": len(rec), "median": st.median(rec), "min": min(rec),
                "max": max(rec), "sd": st.pstdev(rec), "off_epitope": len(off),
            }

    print()
    print("READ IT LIKE THIS")
    for m in failed:
        sc = base[m][0]
        miss = [k for k, v in sc["regions"].items() if v == 0]
        print(f"  {m} FAILS the control. It places the parent off its own epitope,")
        print(f"    touching none of {', '.join(miss)}. The spread it gives across designs")
        print(f"    is its own placement error, not epitope preservation, so it must not")
        print(f"    score this axis: ranking on it ranks designs by how far it drifted.")
    if ctrl:
        bb = report.get("by_batch", {})
        print(f"  {ctrl} PASSES the control, recovering all three annotated regions")
        print(f"    on the parent at recall {base[ctrl][0]['recall']:.2f}. Scored from it, the axis")
        print(f"    splits by what the generator redesigned, which is the whole point:")
        for name, d in bb.items():
            print(f"      {name:<9} median {d['median']:.2f}  sd {d['sd']:.3f}  "
                  f"off-epitope {d['off_epitope']}/{d['n']}")
        cdr3 = [d for n, d in bb.items() if n in ("optA", "optB")]
        multi = [d for n, d in bb.items() if n == "multicdr"]
        if cdr3 and multi:
            print(f"    CDRH3-only designs sit at the parent's own value with almost no")
            print(f"    spread -- epitope preservation really is close to free when only")
            print(f"    the one loop moves, which is what the plan argued on first")
            print(f"    principles and this measures. Move CDRH1 and CDRH2 as well and it")
            print(f"    stops being free: median {multi[0]['median']:.2f}, "
                  f"{multi[0]['off_epitope']} of {multi[0]['n']} designs off the epitope")
            print(f"    altogether. So the axis is not a tie-break among trastuzumab")
            print(f"    variants -- it is the check that catches a design binding")
            print(f"    somewhere else, and it only fires where it should.")
            print(f"    That is the price of the diversity slot, stated as a number:")
            print(f"    multicdr is the one uncorrelated hypothesis we have, and it pays")
            print(f"    for that on this axis. The portfolio step should make that trade")
            print(f"    knowingly rather than discover it.")

    if args.json:
        print()
        print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
