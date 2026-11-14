#!/usr/bin/env python3
"""Is the sequence in the order sheet the molecule we think we designed?

Everything else we measure today is a prediction. This is the one thing that is
not: the order sheet carries the literal amino-acid string a CRO would
synthesise, and if that string is wrong then every score attached to it
describes a different molecule. It is also the last place an error can hide,
because it is downstream of generation, the gates, the axes and the renderer.

So this re-derives each submitted construct from the committed design record and
compares it character by character. It reads only committed files -- no VM, no
network, no GPU -- so a judge can run it on a fresh clone.

Checks, per submitted design:

  construct == vh + (G4S)3 + vl     byte for byte, not merely the right length
  length                            242 aa, and equal to the declared length_aa
  cdrh3                             present, and present exactly ONCE (a loop
                                    appearing twice means the splice duplicated
                                    rather than replaced)
  linker                            the (G4S)3 we claim, not a near-miss
  cysteines                         even, and even within each chain, so the
                                    construct carries no unpaired cysteine
  framework                         identical to trastuzumab outside CDRH3, for
                                    an optimisation-track design

Usage:
  python3 -I scripts/verify_submission.py
  python3 -I scripts/verify_submission.py --order-sheet results/order_sheet.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINKER = "GGGGSGGGGSGGGGS"
EXPECTED_LENGTH = 242
BATCHES = (
    "optA-her2-novel-seed1",
    "optB-her2-exploratory-seed2",
    "multicdr-antibody-seed3",
    "denovo-adalimumab-fw-seed1",
)


def load_records() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in BATCHES:
        f = ROOT / "data/generated" / f"{name}.jsonl"
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["design_id"]] = r
    return out


def check(row: dict, rec: dict, parent: dict) -> list[str]:
    """Every way this construct could be wrong. Empty list means it is right."""
    bad: list[str] = []
    seq = (row.get("sequence") or "").strip().upper()
    vh, vl = rec["vh"], rec["vl"]
    cdrh3 = rec["cdrh3"]

    built = vh + LINKER + vl
    if seq != built:
        # Name the first differing position. A same-length mismatch is the
        # dangerous case -- a single substituted residue passes every length
        # check and changes the molecule -- so "242 aa vs 242 aa" is useless
        # and the position is what someone can act on.
        i = next(
            (k for k in range(min(len(seq), len(built))) if seq[k] != built[k]),
            min(len(seq), len(built)),
        )
        if len(seq) != len(built):
            detail = f"order sheet is {len(seq)} aa, the record rebuilds to {len(built)} aa"
        else:
            detail = (
                f"same length but differs at residue {i + 1}: "
                f"order sheet has {seq[i]!r}, the record gives {built[i]!r}"
            )
        bad.append(f"sequence is not vh+(G4S)3+vl -- {detail}")
    if len(seq) != EXPECTED_LENGTH:
        bad.append(f"length {len(seq)} aa, expected {EXPECTED_LENGTH}")
    declared = row.get("length_aa")
    if declared and str(declared).strip() not in ("", str(len(seq))):
        bad.append(f"declared length_aa {declared} but the sequence is {len(seq)} aa")

    n = seq.count(cdrh3)
    if n == 0:
        bad.append(f"CDRH3 {cdrh3} does not appear in the construct")
    elif n > 1:
        # a splice that appended instead of replacing leaves two copies
        bad.append(f"CDRH3 {cdrh3} appears {n} times; the splice duplicated it")

    if LINKER not in seq:
        bad.append("the (G4S)3 linker is not present")

    # Unpaired cysteine, per chain -- two chains each carrying one free
    # cysteine look paired if you count the joined construct in one go.
    for label, chain in (("VH", vh), ("VL", vl)):
        c = chain.count("C")
        if c % 2:
            bad.append(f"{label} carries {c} cysteines, an odd number")

    # Optimisation-track designs keep trastuzumab's framework. "Framework" means
    # everything outside the CDRs -- ALL of them, not just CDRH3.
    #
    # Masking only CDRH3 was right for the optA/optB batches, which redesign
    # that loop alone. It is wrong for multicdr: `antibody-2026-10-30` exists to
    # redesign any CDR on a fixed framework, so those designs legitimately vary
    # in CDRH1 and CDRH2 and this check read every one of them as a corrupted
    # framework. multicdr-her2_multicdr_98 failed here with 13 substitutions, all
    # 13 inside CDRs (H1 2, H2 4, H3 7) and none in framework.
    #
    # That false positive is expensive in both directions: it prints "do not
    # submit this sheet" over a correct molecule, and multicdr is the batch kept
    # specifically so the shortlist is not four variants of one loop -- so the
    # design most likely to be dropped on a bad verdict is the one carrying our
    # diversity.
    if (rec.get("track") or "") == "optimisation" and rec.get("parent") == "trastuzumab":
        pk = parent["cdrs_kabat"]
        design_cdrs = [cdrh3]
        parent_cdrs = [pk["cdr_h3"]]
        # H1 and H2 are masked positionally: a redesigned loop is not in the
        # record, so mask by the parent's loop where it is still present and
        # otherwise fall back to length-matched masking at the same offset.
        vh_masked, parent_masked = vh, parent["vh"]["sequence"]
        for key in ("cdr_h1", "cdr_h2"):
            ploop = pk.get(key)
            if not ploop:
                continue
            at = parent_masked.find(ploop)
            if at < 0:
                continue
            parent_masked = parent_masked[:at] + "." * len(ploop) + parent_masked[at + len(ploop):]
            vh_masked = vh_masked[:at] + "." * len(ploop) + vh_masked[at + len(ploop):]
        for dloop, ploop in zip(design_cdrs, parent_cdrs):
            vh_masked = vh_masked.replace(dloop, "", 1)
            parent_masked = parent_masked.replace(ploop, "", 1)

        if vh_masked != parent_masked:
            bad.append("VH framework differs from trastuzumab outside the CDRs")
        if vl != parent["vl"]["sequence"]:
            bad.append("VL differs from trastuzumab")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--order-sheet", type=Path, default=ROOT / "results/order_sheet.csv")
    args = ap.parse_args()

    if not args.order_sheet.exists():
        print(f"no order sheet at {args.order_sheet} -- run `make submission` first")
        return 1

    parent = json.loads((ROOT / "data/reference/trastuzumab.json").read_text())
    records = load_records()
    rows = list(csv.DictReader(args.order_sheet.open()))
    if not rows:
        print("order sheet is empty")
        return 1

    print(f"verifying {len(rows)} submitted constructs against the committed records")
    print(f"  {'design':<28} {'aa':>4}  verdict")
    failures = 0
    for row in rows:
        did = row.get("design_id", "?")
        rec = records.get(did)
        if rec is None:
            print(f"  {did:<28} {'?':>4}  NO RECORD -- not in data/generated/")
            failures += 1
            continue
        bad = check(row, rec, parent)
        seq = (row.get("sequence") or "").strip()
        if bad:
            failures += 1
            print(f"  {did:<28} {len(seq):>4}  FAIL")
            for b in bad:
                print(f"       - {b}")
        else:
            print(f"  {did:<28} {len(seq):>4}  ok")

    print()
    if failures:
        print(f"{failures} of {len(rows)} constructs are WRONG -- do not submit this sheet")
        return 1
    print(f"all {len(rows)} constructs re-derive exactly from their design records.")
    print("The sequence on the order sheet is the molecule the scores describe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
