#!/usr/bin/env python3
"""Select submittable designs CLOSEST to the parent, for refolding.

Rizve's SPR analysis found median K_D degrades monotonically with distance from
the parent loop: 0.18 nM near-parent to 160 nM below 40% identity. The <70%
identity rule forces every submittable design onto the far side of that cliff, so
among designs that clear the gate we want the *least* changed, not the most.

The first fold selection ranked by interface H-bond count, which picked mostly
7-8 substitution designs. This picks the other end.

Usage:
  python3 -I scripts/select_close.py runs/optA/designs.jsonl \
      runs/optA/prepared/holo/queries.all.json \
      runs/optA/prepared/holo/queries.close.json --max 18
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", type=Path)
    ap.add_argument("queries", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--max", type=int, default=18)
    ap.add_argument("--exclude-already-folded", action="store_true",
                    help="skip designs that already carry refold metrics")
    args = ap.parse_args()

    by_example = {}
    for line in args.designs.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            by_example[r["example_id"]] = r

    queries = json.loads(args.queries.read_text())["queries"]

    cands = []
    for q in queries:
        r = by_example.get(q["query_id"])
        if r is None:
            continue
        if not (r.get("novelty") or {}).get("passes_challenge_filter"):
            continue
        if args.exclude_already_folded and "refold" in r:
            continue
        muts = r["novelty"].get("mutations_from_parent")
        if muts is None:
            continue
        m = r.get("design_metrics") or {}
        cands.append((muts, -(m.get("hotspot_obedience") or 0),
                      -(m.get("interface_hbond_pairs") or 0), q, r))

    cands.sort(key=lambda t: (t[0], t[1], t[2]))
    picked = cands[: args.max]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"queries": [t[3] for t in picked]}))

    print(f"submittable candidates: {len(cands)}")
    print(f"folding {len(picked)} closest to the parent -> {args.out}")
    print(f"{'design':<16} {'cdrh3':<11} {'subs':>4} {'hotspot':>8} {'hbond':>6}")
    for muts, nh, nb, q, r in picked:
        m = r.get("design_metrics") or {}
        print(f"{q['query_id']:<16} {r['cdrh3']:<11} {muts:>4} "
              f"{m.get('hotspot_obedience'):>8} {m.get('interface_hbond_pairs'):>6}")
    hist = {}
    for muts, *_ in picked:
        hist[muts] = hist.get(muts, 0) + 1
    print(f"substitution counts: {dict(sorted(hist.items()))}")


if __name__ == "__main__":
    main()
