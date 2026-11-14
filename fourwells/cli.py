"""fourwells — pick the four designs that go to the lab.

    fourwells run --target P04626 --budget 4 --out results/

Offline and deterministic by default. HER2 and trastuzumab are defaults, not
hard-coded: pass any UniProt accession, FASTA, PDB or raw sequence.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from .cache import Cache
from .report import render
from .runner import run_pipeline, write_outputs
from .schema import AXES, SCHEMA_VERSION
from .targets import resolve_reference_ab, resolve_target

DIM, B, R = "\033[2m", "\033[1m", "\033[0m"
YEL, GRN, RED = "\033[33m", "\033[32m", "\033[31m"


def _print_report(result, target, ref, paths, cache) -> None:
    print(f"\n{B}fourwells{R} {DIM}schema v{SCHEMA_VERSION}{R}")
    print(f"  target     {target.identifier} ({target.kind})")
    print(f"  reference  {ref.name}" + (f" · CDRH3 {ref.cdrh3}" if ref.cdrh3 else ""))
    if target.epitope_residues:
        print(f"  epitope    {', '.join(target.epitope_residues)}")

    print(f"\n{B}  stages{R}")
    for s in result.stages:
        print(f"    {s.name:<10} {s.seconds:6.2f}s  {s.n_in:>4} → {s.n_out:<4}")

    n_pass = len(result.passed)
    print(f"\n{B}  gates{R}  {n_pass}/{len(result.records)} passed")
    reasons: dict[str, int] = {}
    for rec in result.records:
        for rule in rec.gates.failed_rules:
            key = rule.split("(")[0].split("[")[0].strip()
            key = " ".join(key.split()[:3])
            reasons[key] = reasons.get(key, 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"    {DIM}{n:>3}× {reason}{R}")

    # The novelty-distance reading is a judgment call, not a measurement, so it
    # is printed on every run rather than left in a file someone has to open.
    from .stages.portfolio import audit as _audit

    rep = _audit(result.records, budget=len(result.selected) or 4)
    ok = rep["novelty_distance_verified"]
    print(
        f"\n{B}  novelty distance{R}  strict, >= {rep['submittable_distance']} substitutions  "
        + (f"{GRN}all picks verified{R}" if ok else f"{RED}NOT VERIFIED{R}")
        + f"  {DIM}cost {rep['designs_priced_out_by_strict_reading']} otherwise-passing designs{R}"
    )

    print(f"\n{B}  selected{R}")
    if not result.selected:
        print(f"    {RED}nothing selected{R}")
    for rec in result.selected:
        axes = " ".join(
            f"{a}={'—' if rec.axes.get(a) is None else f'{rec.axes[a]:.2f}'}"
            for a in AXES
        )
        js = "—" if rec.joint_score is None else f"{rec.joint_score:.3f}"
        print(f"    {rec.rank}. {rec.design_id:<12} joint={js:<6} {DIM}{axes}{R}")
        for line in rec.rationale:
            print(f"       {DIM}{line}{R}")

    if result.warnings:
        print(f"\n{B}{YEL}  warnings{R}")
        for w in result.warnings[:12]:
            print(f"    {YEL}! {w}{R}")
        if len(result.warnings) > 12:
            print(f"    {DIM}… {len(result.warnings) - 12} more{R}")

    print(f"\n{B}  output{R}")
    for name, p in paths.items():
        print(f"    {name:<10} {p}")
    print(f"    {DIM}{cache.stats()}{R}\n")


def cmd_run(args) -> int:
    random.seed(args.seed)
    try:
        target = resolve_target(args.target)
    except ValueError as e:
        print(f"{RED}error:{R} {e}", file=sys.stderr)
        return 2
    ref = resolve_reference_ab(args.reference)

    cache = Cache(offline=not args.online)
    result = run_pipeline(
        target=target,
        ref=ref,
        budget=args.budget,
        n_candidates=args.candidates,
        seed=args.seed,
        cache=cache,
        timebox=args.timebox,
    )
    paths = write_outputs(result, args.out)
    if not args.no_report:
        # Rendered on every run, so the committed example output is never stale
        # and nothing has to be generated live during the pitch.
        paths.update(render(result.records, args.out, budget=args.budget))
    _print_report(result, target, ref, paths, cache)

    if args.strict and result.warnings:
        print(f"{RED}strict: {len(result.warnings)} warning(s){R}", file=sys.stderr)
        return 1
    return 0


def cmd_schema(args) -> int:
    from dataclasses import fields

    from .schema import DesignRecord

    print(f"{B}DesignRecord{R} {DIM}schema v{SCHEMA_VERSION} — frozen{R}\n")
    for f in fields(DesignRecord):
        print(f"  {f.name:<28} {DIM}{f.type}{R}")
    print(f"\n  {DIM}axes: {', '.join(AXES)} — each relative to the reference,")
    print(f"  {DIM}None is valid while a predictor is being built.{R}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fourwells", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the pipeline end to end")
    r.add_argument("--target", default=None, help="UniProt, FASTA, PDB or sequence (default: HER2 P04626)")
    r.add_argument("--reference", default=None, help="antibody to beat (default: trastuzumab)")
    r.add_argument("--budget", type=int, default=4, help="lab slots to fill (default: 4)")
    r.add_argument("--candidates", type=int, default=24, help="candidates to generate")
    r.add_argument("--out", default="results/", help="output directory")
    r.add_argument("--seed", type=int, default=0, help="fixed seed (default: 0)")
    r.add_argument("--timebox", type=float, default=300.0, help="per-stage warn threshold, seconds")
    r.add_argument("--online", action="store_true", help="allow network/GPU calls (default: offline)")
    r.add_argument("--strict", action="store_true", help="exit non-zero if any warning")
    r.add_argument("--no-report", action="store_true", help="skip the rendered report and order sheet")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("schema", help="print the frozen design-record contract")
    s.set_defaults(func=cmd_schema)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
