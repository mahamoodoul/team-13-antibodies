"""Build the visualiser's data file from a pipeline run — OWNER: Rizve.

    python3 -I viz/build_data.py                  # whole committed pool
    python3 -I viz/build_data.py --candidates 200 --seed 0

Writes viz/designs.json: one record per design, carrying what the page draws
and nothing else. Deterministic for a fixed pool and seed, so the committed
JSON can be regenerated and diffed rather than taken on trust.

The page reads this file and never recomputes a score. Every number it shows
comes from the same pipeline that picks the four, so the visualiser cannot
drift from the ranking — if they disagree, the JSON is stale and this script
is how you fix it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fourwells.cache import Cache  # noqa: E402
from fourwells.runner import run_pipeline  # noqa: E402
from fourwells.schema import AXES  # noqa: E402
from fourwells.stages import portfolio as portfolio_stage  # noqa: E402
from fourwells.targets import resolve_reference_ab, resolve_target  # noqa: E402


def record_to_row(r) -> dict:
    nov = (r.gates.checks or {}).get("novelty") or {}
    conf = (r.axis_evidence or {}).get("confidence") or {}
    ep = (r.axis_evidence or {}).get("epitope") or {}
    metrics = (r.axis_evidence or {}).get("design_metrics") or {}
    return {
        "id": r.design_id,
        "cdrh3": r.cdrh3,
        "batch": r.design_id.split("-")[0] if "-" in r.design_id else "baseline",
        "generator": r.generator,
        "track": r.track,
        "format": r.format,
        "is_baseline": r.is_baseline,
        "vh_len": len(r.sequence or ""),
        # the three axes, each P(beats trastuzumab); 0.5 ties it exactly
        "axes": {a: r.axes.get(a) for a in AXES},
        "joint": r.joint_score,
        "cluster": r.cluster,
        "selected": r.selected,
        "rank": r.rank,
        # gates
        "passed": r.gates.passed,
        "fails": [f.split("(")[0].strip() for f in r.gates.failed_rules],
        # identity / novelty
        "parent_subs": r.cdrh3_mutations_from_tras,
        "identity": r.cdrh3_identity_to_tras,
        "novelty_dist": nov.get("min_substitutions_from_any_provided"),
        "novelty_borderline": bool(nov.get("borderline")),
        # structure evidence, where a refold exists
        "iptm": conf.get("iptm"),
        "min_ipae": conf.get("min_ipae"),
        "binder_plddt": conf.get("binder_plddt"),
        "refold_model": conf.get("model"),
        "epitope_basis": ep.get("basis"),
        "epitope_overlap": ep.get("epitope_overlap"),
        "hotspot_obedience": metrics.get("hotspot_obedience"),
        # the dossier
        "rationale": r.rationale,
        "kill_criterion": r.kill_criterion,
        "reasons": {a: ((r.axis_evidence or {}).get(a) or {}).get("reason") for a in AXES},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", type=int, default=400)
    ap.add_argument("--budget", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "designs.json")
    args = ap.parse_args(argv)

    target = resolve_target(None)
    ref = resolve_reference_ab(None)
    result = run_pipeline(
        target=target,
        ref=ref,
        budget=args.budget,
        n_candidates=args.candidates,
        seed=args.seed,
        cache=Cache(offline=True),
    )

    rows = [record_to_row(r) for r in result.records]
    audit = portfolio_stage.audit(result.records, budget=args.budget)

    blob = {
        "meta": {
            "target": target.identifier,
            "reference": ref.name,
            "reference_cdrh3": ref.cdrh3,
            "baseline_axis_value": 0.5,
            # The median of the parent's 8 SPR replicates, not a single row.
            # Those 8 span 6.24x on the identical molecule, which is why
            # "beats the baseline" is reported against the median and why the
            # page shows the spread beside it.
            "baseline_kd_nM": (ref.meta.get("baseline_measurements") or {}).get("median_kd_nM"),
            "baseline_kd_spread": (ref.meta.get("baseline_measurements") or {}).get("fold_spread"),
            "baseline_kd_n": (ref.meta.get("baseline_measurements") or {}).get("n"),
            "epitope_residues": target.epitope_residues,
            "budget": args.budget,
            "seed": args.seed,
            "n_pool": len(rows),
            "n_passed": sum(1 for r in rows if r["passed"]),
            "n_selected": sum(1 for r in rows if r["selected"]),
        },
        "audit": audit,
        "designs": rows,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, separators=(",", ":"), sort_keys=True) + "\n")

    m = blob["meta"]
    print(f"wrote {args.out}")
    print(f"  pool {m['n_pool']} · passed {m['n_passed']} · selected {m['n_selected']}")
    print(f"  submission_ready: {audit['submission_ready']}")
    for b in audit["blockers"]:
        print(f"  blocker: {b[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
