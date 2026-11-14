"""Build the results page's data: rewrites the JSON block inside viz/results.html.

    python3 -I viz/build_results.py                  # results/designs.jsonl -> viz/results.html
    python3 -I viz/build_results.py --results DIR    # another run's output directory
    python3 -I viz/build_results.py --check          # exit 1 if the page is out of date

viz/results.html is one self-contained file: its code is hand-written, its data is not.
This script replaces only the block between the two DATA markers and leaves everything
else alone. The page recomputes nothing, so every number on it comes from the records the
ranker wrote, and it cannot drift from them. If the page and results/ disagree, the page
is stale and this is how you fix it.

The data is inlined rather than fetched, so the page opens straight from disk. The older
viz/index.html needs a local server for that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fourwells.report import BASELINE, axis_cell  # noqa: E402
from fourwells.schema import AXES, distance_is_capped, read_jsonl  # noqa: E402
from fourwells.stages import portfolio as portfolio_stage  # noqa: E402
from fourwells.stages.gates import (  # noqa: E402
    MAX_CDRH3_IDENTITY,
    MAX_LENGTH,
    SUBMITTABLE_DISTANCE,
)
from fourwells.targets import resolve_target  # noqa: E402

PAGE = Path(__file__).parent / "results.html"
START, END = "<!--DATA:START-->", "<!--DATA:END-->"
TREND = {"▲": "up", "≈": "eq", "▼": "down"}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def parse_spans(spans) -> list[tuple[int, int]]:
    out = []
    for s in spans or []:
        lo, _, hi = str(s).partition("-")
        out.append((int(lo), int(hi or lo)))
    return out


def trend(rec, axis: str) -> str | None:
    """up / eq / down, using the report's own arrow rule so page and report agree."""
    return TREND.get(axis_cell(rec, axis).split()[-1])


def fail_kind(text: str) -> str:
    t = text.lower()
    if t.startswith("length"):
        return "length"
    if t.startswith("novelty"):
        return "novelty"
    if "identity" in t:
        return "identity"
    if "cysteine" in t:
        return "cysteine"
    return "other"


def tier_counts(axes: list[float]) -> list[float]:
    """P(exactly k of these axes beat the baseline), k = 0..n, axes taken as independent.

    Independence is the same assumption the joint score makes: it is a product.
    """
    dist = [1.0]
    for p in axes:
        nxt = [0.0] * (len(dist) + 1)
        for k, mass in enumerate(dist):
            nxt[k] += mass * (1 - p)
            nxt[k + 1] += mass * p
        dist = nxt
    return dist


def counter(items) -> dict:
    return dict(Counter(items))


def median(values: list[float]) -> float | None:
    v = sorted(values)
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


# --------------------------------------------------------------------------- #
# one record -> one row the page draws
# --------------------------------------------------------------------------- #

def construct_parts(rec) -> dict | None:
    """The orderable scFv split into VH / linker / VL, only if the pieces add up."""
    c = (rec.axis_evidence or {}).get("construct") or {}
    seq, linker = c.get("sequence"), c.get("linker")
    vl = (rec.axis_evidence or {}).get("vl")
    if seq and linker and vl and seq == rec.sequence + linker + vl:
        return {"vh": rec.sequence, "linker": linker, "vl": vl}
    return {"seq": seq} if seq else None


def epitope_footprint(rec, annotated: set[int]) -> dict | None:
    """Which annotated epitope residues the refold contacts, if the record carries one.

    Returned only when it reproduces the overlap the scorer wrote. A footprint that
    disagrees with the number beside it would be worse than none.
    """
    ev = rec.axis_evidence or {}
    contacts = ev.get("epitope_contacts")
    ep = ev.get("epitope") or {}
    if not contacts or ep.get("basis") != "structural" or not annotated:
        return None
    hit = sorted({int(c) for c in contacts if str(c).lstrip("-").isdigit()} & annotated)
    if abs(len(hit) / len(annotated) - float(ep.get("epitope_overlap", -1))) > 0.005:
        print(f"  note: {rec.design_id}: footprint does not reproduce its overlap; omitted")
        return None
    meta = ev.get("epitope_contacts_meta") or {}
    return {
        "hit": hit,
        "overlap": ep.get("epitope_overlap"),
        "n_contacts": ep.get("n_contacts"),
        "model": meta.get("source_model"),
        "cutoff": meta.get("cutoff_angstrom"),
    }


def design_row(rec, annotated: set[int]) -> dict:
    ev = rec.axis_evidence or {}
    chk = rec.gates.checks or {}
    nov = chk.get("novelty") or {}
    batch = rec.design_id.split("-")[0]
    num = re.search(r"(\d+)$", rec.design_id)
    row = {
        "id": rec.design_id,
        "batch": batch,
        "short": f"{batch} {num.group(1)}" if num else rec.design_id,
        "generator": rec.generator,
        "parent": rec.parent,
        "track": rec.track,
        "format": rec.format,
        "cdrh3": rec.cdrh3,
        "subs": rec.cdrh3_mutations_from_tras,
        "identity": rec.cdrh3_identity_to_tras,
        "dist": nov.get("min_substitutions_from_any_provided"),
        "dist_capped": distance_is_capped(nov),
        "length": chk.get("construct_length", chk.get("length_measured")),
        "axes": {a: rec.axes.get(a) for a in AXES},
        "trend": {a: trend(rec, a) for a in AXES},
        "basis": {a: (ev.get(a) or {}).get("basis") for a in AXES},
        "reason": {a: (ev.get(a) or {}).get("reason") for a in AXES},
        "joint": rec.joint_score,
        "cluster": rec.cluster,
        "selected": bool(rec.selected),
        "rank": rec.rank,
        "passed": bool(rec.gates.passed),
        "fails": [
            {"kind": fail_kind(f), "text": f.split(". ", 1)[0].rstrip(".")}
            for f in rec.gates.failed_rules
        ],
        "abguard": (chk.get("abguard") or {}).get("status"),
    }
    fp = epitope_footprint(rec, annotated)
    if fp:
        row["epitope"] = fp
    if rec.selected:
        rationale = rec.rationale or []
        row["dossier"] = {
            "cluster_note": next((s for s in rationale if s.startswith("Represents cluster")), None),
            "why_listed": next((s for s in rationale if s.startswith("On the list")), None),
            "kill": rec.kill_criterion,
            "construct": construct_parts(rec),
            "construct_length": (ev.get("construct") or {}).get("length"),
            "orientation": (ev.get("construct") or {}).get("orientation"),
        }
    return row


# --------------------------------------------------------------------------- #
# facts the page words its headlines from
# --------------------------------------------------------------------------- #

def batch_facts(rows: list[dict], records: list) -> list[dict]:
    """One row per generator batch: how many survived, and what took the rest.

    Rejections are counted by each design's FIRST failed rule, so the reasons sum
    to the number rejected instead of double-counting the 12 that fail two rules.
    """
    ev = {r.design_id: (r.axis_evidence or {}) for r in records}
    out = []
    for batch in sorted({r["batch"] for r in rows}):
        group = [r for r in rows if r["batch"] == batch]
        reasons = []
        for kind, kgroup in sorted(
            Counter(r["fails"][0]["kind"] for r in group if r["fails"]).items(),
            key=lambda kv: -kv[1],
        ):
            hit = [r for r in group if r["fails"] and r["fails"][0]["kind"] == kind]
            vals = [v for v in ({"length": [r["length"] for r in hit],
                                 "novelty": [r["dist"] for r in hit],
                                 "identity": [r["identity"] for r in hit]}.get(kind) or [])
                    if v is not None]
            reasons.append(
                {
                    "kind": kind,
                    "n": kgroup,
                    "min": min(vals) if vals else None,
                    "max": max(vals) if vals else None,
                    "also_failed_another": sum(1 for r in hit if len(r["fails"]) > 1),
                }
            )
        overlaps = [
            (ev[r["id"]].get("epitope") or {}).get("epitope_overlap")
            for r in group
            if r["basis"]["epitope"] == "structural"
        ]
        overlaps = [o for o in overlaps if o is not None]
        out.append(
            {
                "batch": batch,
                "n": len(group),
                "eligible": sum(1 for r in group if r["passed"]),
                "chosen": sum(1 for r in group if r["selected"]),
                "generator": group[0]["generator"],
                "parent": group[0]["parent"],
                "reasons": reasons,
                "folded": len(overlaps),
                "median_overlap": median(overlaps),
            }
        )
    return out


def build_facts(cands: list, rows: list[dict], picks: list[dict], records: list, budget: int) -> dict:
    by_joint = sorted(rows, key=lambda r: -(r["joint"] or 0))
    eligible = [r for r in rows if r["passed"]]
    n = len(picks)
    top_raw = by_joint[:n]
    top_eligible = sorted(eligible, key=lambda r: -(r["joint"] or 0))[:n]

    def trend_counts(group):
        return {a: counter(r["trend"][a] for r in group) for a in AXES}

    tiers = [0.0] * 4
    p_none_s = 1.0
    for r in picks:
        dist = tier_counts([r["axes"][a] for a in AXES])
        for k in range(4):
            tiers[k] += dist[k]
        p_none_s *= 1 - dist[3]

    # How far down the raw ranking the first submittable design sits. The gates
    # take the whole top of the list, and that is the shortlist's central fact.
    above_best_eligible = next((i for i, r in enumerate(by_joint) if r["passed"]), None)

    # Eligible designs that outscore the lowest-ranked pick and still did not get a
    # well: the cluster rule at work. Each is named with the pick already testing its
    # hypothesis, so "allocate across clusters, not down the list" is visible rather
    # than asserted.
    floor = min((r["joint"] or 0) for r in picks) if picks else 0
    by_cluster = {r["cluster"]: r for r in sorted(picks, key=lambda r: r["rank"] or 99)}
    passed_over = [
        {
            "id": r["id"],
            "joint": r["joint"],
            "cluster": r["cluster"],
            "represented_by": (by_cluster.get(r["cluster"]) or {}).get("id"),
        }
        for r in sorted(eligible, key=lambda r: -(r["joint"] or 0))
        if not r["selected"] and (r["joint"] or 0) > floor
    ]

    # Per axis, over the whole pool: does anything actually beat the parent?
    per_axis = {}
    for a in AXES:
        vals = [r["axes"][a] for r in rows if r["axes"][a] is not None]
        per_axis[a] = {
            "n": len(vals),
            "above": sum(1 for v in vals if v > BASELINE),
            "max": max(vals) if vals else None,
            "median": median(vals),
        }
    beats = [sum(1 for a in AXES if (r["axes"][a] or 0) > BASELINE) for r in rows]

    chosen_rec = [r for r in records if r.selected]
    first = chosen_rec[0] if chosen_rec else None
    fev = (first.axis_evidence or {}) if first else {}
    all_ev = [(r.axis_evidence or {}) for r in records if not r.is_baseline]

    tools_missing = sorted({t for e in all_ev for t in ((e.get("stability") or {}).get("developability") or {}).get("tools_not_called", [])})
    policy = fev.get("confidence_policy") or {}
    # abguard's reason is read from the picks. A design that failed an earlier gate
    # never reaches it and carries a different note, which says nothing about the four.
    ab_picks = [((r.gates.checks or {}).get("abguard") or {}) for r in chosen_rec]
    ab_pool = [((r.gates.checks or {}).get("abguard") or {}) for r in records if not r.is_baseline]

    audit = portfolio_stage.audit(records, budget=budget)
    return {
        "n_candidates": len(rows),
        "n_eligible": len(eligible),
        "n_selected": n,
        "budget": budget,
        "n_clusters": len({r["cluster"] for r in rows if r["cluster"]}),
        "joint_sum": sum(r["joint"] for r in picks),
        "p_any_s": 1 - p_none_s,
        "tiers": {"S": tiers[3], "A": tiers[2], "B": tiers[1], "none": tiers[0]},
        "picks_are_top_eligible": {r["id"] for r in picks} == {r["id"] for r in top_eligible},
        "clusters_distinct": len({r["cluster"] for r in picks}) == n,
        "top_raw": {"n": n, "rejected": sum(1 for r in top_raw if not r["passed"]), "ids": [r["id"] for r in top_raw]},
        "above_best_eligible": above_best_eligible,
        "passed_over": passed_over,
        "per_axis": per_axis,
        "multi_axis": {"two_or_more": sum(1 for b in beats if b >= 2), "all_three": sum(1 for b in beats if b == 3)},
        "batches": batch_facts(rows, records),
        "audit": {
            "submission_ready": audit["submission_ready"],
            "blockers": audit["blockers"],
            "priced_out_by_strict_reading": audit["designs_priced_out_by_strict_reading"],
            "submittable_distance": audit["submittable_distance"],
            "novelty_distance_verified": audit["novelty_distance_verified"],
            "tracks": audit["tracks"],
        },
        "trends": {"picks": trend_counts(picks), "pool": trend_counts(rows)},
        "basis": {
            a: {
                "picks": counter(r["basis"][a] for r in picks),
                "pool": counter(r["basis"][a] for r in rows),
            }
            for a in AXES
        },
        "evidence": {
            "stability_tools_missing": tools_missing,
            "confidence": {
                "calibrated": policy.get("calibrated"),
                "policy": policy.get("policy"),
                "cutoff": policy.get("cutoff"),
            },
            "abguard": {
                "picks": counter(a.get("status") for a in ab_picks),
                "pool": counter(a.get("status") for a in ab_pool),
                "why": next((a.get("why") for a in ab_picks if a.get("why")), None),
            },
        },
    }


# --------------------------------------------------------------------------- #
# assemble, inject, check
# --------------------------------------------------------------------------- #

def run_stamp(results_dir: Path) -> str | None:
    """When the run was made, as the pipeline itself printed it atop report.md."""
    md = results_dir / "report.md"
    if not md.exists():
        return None
    m = re.search(r"^\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", md.read_text(), re.M)
    return m.group(1) if m else None


def build(results_dir: Path, budget: int = 4) -> dict:
    src = results_dir / "designs.jsonl"
    records = read_jsonl(src)
    target = resolve_target(None)
    spans = parse_spans(target.epitope_residues)
    annotated = {n for lo, hi in spans for n in range(lo, hi + 1)}

    ref = next((r for r in records if r.is_baseline), None)
    cands = [r for r in records if not r.is_baseline]
    rows = sorted((design_row(r, annotated) for r in cands), key=lambda r: (-(r["joint"] or 0), r["id"]))
    picks = sorted((r for r in rows if r["selected"]), key=lambda r: r["rank"] or 99)

    try:
        shown = str(src.resolve().relative_to(ROOT))
    except ValueError:
        shown = str(src)

    first_struct = next((r["epitope"] for r in rows if r.get("epitope")), None) or {}
    return {
        "meta": {
            "source": shown,
            "sha256": hashlib.sha256(src.read_bytes()).hexdigest()[:12],
            "n_records": len(records),
            "run_at": run_stamp(results_dir),
            "baseline": BASELINE,
            "reference": (
                {
                    "id": ref.design_id,
                    "cdrh3": ref.cdrh3,
                    "axes": {a: ref.axes.get(a) for a in AXES},
                    "joint": ref.joint_score,
                }
                if ref
                else None
            ),
            "rules": {
                "max_length": MAX_LENGTH,
                "max_identity": MAX_CDRH3_IDENTITY,
                "min_distance": SUBMITTABLE_DISTANCE,
            },
            "epitope": {
                "spans": [list(s) for s in spans],
                "n": len(annotated),
                "model": first_struct.get("model"),
                "cutoff": first_struct.get("cutoff"),
            },
        },
        "facts": build_facts(cands, rows, picks, records, budget),
        "designs": rows,
    }


def render_block(blob: dict) -> str:
    payload = json.dumps(blob, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    # "<" can never appear in a script body then, so no string can close it early.
    payload = payload.replace("<", "\\u003c")
    return f'{START}<script id="results-data" type="application/json">{payload}</script>{END}'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, default=ROOT / "results", help="run directory holding designs.jsonl")
    ap.add_argument("--page", type=Path, default=PAGE, help="page to update")
    ap.add_argument("--budget", type=int, default=4, help="lab slots the run filled (default: 4)")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if the page is out of date")
    args = ap.parse_args(argv)

    blob = build(args.results, budget=args.budget)
    text = args.page.read_text()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        print(f"error: {args.page} has no {START} ... {END} block to replace", file=sys.stderr)
        return 2
    updated = pattern.sub(lambda _m: render_block(blob), text, count=1)

    f = blob["facts"]
    if args.check:
        stale = updated != text
        print(f"{args.page.name}: {'OUT OF DATE, rerun without --check' if stale else 'up to date'}"
              f" (data {blob['meta']['sha256']})")
        return 1 if stale else 0

    args.page.write_text(updated)
    print(f"wrote {args.page}")
    print(f"  {blob['meta']['source']} · {blob['meta']['n_records']} records · sha256 {blob['meta']['sha256']}")
    print(f"  candidates {f['n_candidates']} · eligible {f['n_eligible']} · chosen {f['n_selected']}")
    print(f"  expected S-tier {f['joint_sum']:.3f} · P(at least one) {f['p_any_s']:.3f}")
    print(f"  submission_ready: {f['audit']['submission_ready']}")
    for b in f["audit"]["blockers"]:
        print(f"  blocker: {b[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
