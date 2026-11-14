#!/usr/bin/env python3
"""Keep only submittable designs in a refold queries.json, before spending GPU.

refold-prepare ranks by its own structural criteria -- hotspot obedience,
interface H-bonds, clashes -- and knows nothing about the challenge filter. On a
4-design test it picked a design with only 3 CDRH3 substitutions, which cannot be
submitted in the optimisation track, so half the refold budget went on a design
we could never send. Folding is the expensive step, so the filter belongs in
front of it.

Writes a filtered queries.json and prints what it dropped and why.

Usage:
  python3 -I scripts/filter_queries.py runs/optA/designs.jsonl \
      runs/optA/prepared/holo/queries.json runs/optA/prepared/holo/queries.filtered.json \
      --max 25 --rank-by interface_hbond_pairs
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", type=Path, help="designs.jsonl from export_batch.py")
    ap.add_argument("queries", type=Path, help="prepared/holo/queries.json")
    ap.add_argument("out", type=Path)
    ap.add_argument("--max", type=int, default=25, help="cap on designs to fold")
    ap.add_argument(
        "--rank-by",
        default="interface_hbond_pairs",
        help="design metric to prefer when capping (higher is better)",
    )
    ap.add_argument(
        "--allow-borderline",
        action="store_true",
        help="also keep designs with exactly 3 substitutions, which pass the "
             "Apheris reading of the identity ceiling but fail the strict <70% one",
    )
    ap.add_argument(
        "--prefer-ids",
        type=Path,
        help="file of example_ids, one per line, to fold before anything else. "
             "The ranker's own order, so the fold budget lands on the designs we "
             "are actually considering rather than the ones refold-prepare liked",
    )
    ap.add_argument(
        "--only-ids",
        action="store_true",
        help="with --prefer-ids, fold nothing else",
    )
    args = ap.parse_args()

    # WHY THIS EXISTS. --rank-by is a design metric (H-bond pairs by default),
    # which is what refold-prepare ranks on. It has no relationship to the joint
    # score that decides what we submit: of the 20 optB designs we folded on
    # that ranking, not one was in the ranker's top four, so every pick's
    # epitope axis was still a prior while 20 folds sat on designs we were not
    # considering. Folding is the expensive step; spend it where the decision is.
    prefer: list[str] = []
    if args.prefer_ids:
        prefer = [
            l.strip() for l in args.prefer_ids.read_text().splitlines() if l.strip()
        ]

    by_example: dict[str, dict] = {}
    for line in args.designs.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            by_example[row["example_id"]] = row

    queries = json.loads(args.queries.read_text())["queries"]

    kept, dropped = [], []
    for q in queries:
        row = by_example.get(q["query_id"])
        if row is None:
            dropped.append((q["query_id"], "not in the export"))
            continue
        nov = row.get("novelty", {})
        muts = nov.get("mutations_from_parent")
        if nov.get("in_provided_data"):
            dropped.append((q["query_id"], f"CDRH3 {row['cdrh3']} is already in the provided data"))
            continue
        if not nov.get("passes_novelty"):
            dropped.append((q["query_id"], f"within 1 substitution of a provided sequence"))
            continue
        if not nov.get("passes_identity_ceiling"):
            if args.allow_borderline and muts == 3:
                kept.append((q, row, True))
                continue
            dropped.append((q["query_id"], f"only {muts} substitutions from the parent (need 4)"))
            continue
        kept.append((q, row, False))

    if prefer and args.only_ids:
        wanted = set(prefer)
        kept = [item for item in kept if item[0]["query_id"] in wanted]

    rank_of = {ex: i for i, ex in enumerate(prefer)}

    def sort_key(item):
        q, row, borderline = item
        metric = (row.get("design_metrics") or {}).get(args.rank_by)
        return (
            rank_of.get(q["query_id"], len(rank_of)),
            borderline,
            -(metric if isinstance(metric, (int, float)) else -1),
        )

    kept.sort(key=sort_key)
    capped = kept[: args.max]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"queries": [q for q, _, _ in capped]}))

    print(f"queries in:  {len(queries)}")
    print(f"submittable: {len(kept)}")
    print(f"folding:     {len(capped)} -> {args.out}")
    if len(kept) > len(capped):
        print(f"  (capped at --max {args.max}, ranked by {args.rank_by})")
    if prefer:
        hit = sum(1 for q, _, _ in capped if q["query_id"] in rank_of)
        missing = [ex for ex in prefer if ex not in {q["query_id"] for q, _, _ in kept}]
        print(f"  {hit} of {len(prefer)} --prefer-ids designs are in this fold set")
        if missing:
            print(f"  NOT foldable from this run ({len(missing)}): {' '.join(missing)}")
    n_border = sum(1 for _, _, b in capped if b)
    if n_border:
        print(f"  including {n_border} borderline 3-substitution designs (--allow-borderline)")
    if dropped:
        print(f"dropped {len(dropped)}:")
        counts: dict[str, int] = {}
        for _, why in dropped:
            key = why.split("(")[0].strip()
            if "substitutions from the parent" in key:
                key = "too few substitutions from the parent"
            counts[key] = counts.get(key, 0) + 1
        for why, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3}x {why}")
    if capped:
        print("folding these:")
        for q, row, border in capped[:30]:
            m = (row.get("design_metrics") or {}).get(args.rank_by)
            flag = "  [borderline]" if border else ""
            print(f"  {q['query_id']:<18} cdrh3={row['cdrh3']} "
                  f"muts={row['novelty'].get('mutations_from_parent')} "
                  f"{args.rank_by}={m}{flag}")


if __name__ == "__main__":
    main()
