#!/usr/bin/env python3
"""Export one Foundry design run into the batch format the pipeline replays.

Reads a run directory produced by scripts/design_batch.sh (plus refold-prepare /
fold / refold-score if those ran) and writes one JSON object per design:

  design_id, vh, vl, cdrh3, generator, track, format, seed,
  novelty {...}, design_metrics {...}, refold {...}

Sequences come from the generated CIFs, so every design is exported whether or
not it was selected for refolding. Novelty is checked against every CDRH3 in the
provided data, which is the actual challenge filter.

Usage:
  python3 -I scripts/export_batch.py runs/optA --weight her2-novel-2026-11-09 \
      --seed 1 --out runs/optA/designs.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}

CDRH3_PREFIX = "YYCSR"
CDRH3_SUFFIX = "YWGQGT"
PARENT_CDRH3 = "WGGDGFYAMD"
UNIVERSE = Path.home() / "data" / "tidy" / "provided_cdrh3_universe.txt"

# Keep the per-design metrics that say something about the design, and drop the
# ~70 config columns that just echo the run settings.
WANTED_METRICS = {
    "hotspot_obedience.hotspot_obedience": "hotspot_obedience",
    "clash_metrics.frac_atoms_clashing_1p5A": "clash_fraction",
    "interchain_interactions.hbond_atom_pair_count_coi": "interface_hbond_pairs",
    "interchain_interactions.saltbridge_residue_pair_count_coi": "interface_saltbridges",
    "interchain_interactions.hydrophobic_atom_pair_count_coi": "interface_hydrophobic_pairs",
    "interchain_interactions.pistack_residue_pair_count_coi": "interface_pistack",
    "sequence_adherence.sequence_adherence": "sequence_adherence",
    "sequence_adherence.n_violations": "sequence_violations",
    "amino_acid_composition.n_generated_unknown_residues": "unknown_residues",
    "bond_length_metrics.bond_length.frac_unreasonable": "bond_length_unreasonable",
}

WANTED_REFOLD = {
    "model": "model", "min_ipae": "min_ipae", "iptm": "iptm", "ptm": "ptm",
    "binder_plddt": "binder_plddt", "plddt": "plddt", "binder_ptm": "binder_ptm",
    "backbone_rmsd": "backbone_rmsd", "pass": "pass", "pass_note": "pass_note",
}


def parse_cif_chains(path: Path) -> dict[str, str]:
    """Return {chain_id: one-letter sequence} from an mmCIF atom_site loop."""
    cols: list[str] = []
    in_loop = False
    seen: dict[str, dict] = {}
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
                resnum = rec.get("auth_seq_id") or rec.get("label_seq_id")
                comp = (rec.get("label_comp_id") or rec.get("auth_comp_id") or "").upper()
                if chain is None or resnum is None or not comp:
                    continue
                seen.setdefault(chain, {})
                # keyed by residue number so each residue is counted once
                if resnum not in seen[chain]:
                    seen[chain][resnum] = comp
            elif in_loop and s.startswith("#"):
                in_loop = False
    out = {}
    for chain, residues in seen.items():
        ordered = sorted(residues.items(), key=lambda kv: int(kv[0]) if kv[0].lstrip("-").isdigit() else 0)
        out[chain] = "".join(THREE_TO_ONE.get(c, "X") for _, c in ordered)
    return out


def extract_cdrh3(vh: str) -> str | None:
    i = vh.find(CDRH3_PREFIX)
    if i < 0:
        return None
    start = i + len(CDRH3_PREFIX)
    j = vh.rfind(CDRH3_SUFFIX)
    if j <= start:
        return None
    return vh[start:j]


def load_universe() -> set[str]:
    if not UNIVERSE.exists():
        print(f"WARNING: {UNIVERSE} missing — novelty not checked", file=sys.stderr)
        return set()
    return {l.strip().upper() for l in UNIVERSE.read_text().splitlines() if l.strip()}


AA_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"


def min_substitutions_capped(loop: str, universe: set[str]) -> int | None:
    """How far `loop` is from the nearest provided sequence, capped at 2.

    Returns 0 (the loop is in the provided data), 1 (a single substitution from a
    provided sequence), or 2 (meaning "2 or more" — the filter is satisfied).

    The filter only asks whether a design differs at 2+ positions from every
    provided sequence, so the exact distance beyond 2 is not needed. Testing it
    by generating the loop's own 1-neighbourhood is ~190 set lookups instead of
    525,063 string comparisons, and is exact rather than approximate.
    """
    if not universe:
        return None
    if loop in universe:
        return 0
    chars = list(loop)
    for i, original in enumerate(chars):
        for sub in AA_ALPHABET:
            if sub == original:
                continue
            chars[i] = sub
            if "".join(chars) in universe:
                chars[i] = original
                return 1
        chars[i] = original
    return 2


def read_metrics(run: Path) -> dict[str, dict]:
    path = run / "design" / "generation" / "inference_metrics" / "per_example_metrics.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            ex = row.get("example_id")
            if not ex:
                continue
            d = {}
            for src, dst in WANTED_METRICS.items():
                v = row.get(src)
                if v in (None, ""):
                    continue
                try:
                    f = float(v)
                    d[dst] = int(f) if f.is_integer() else round(f, 5)
                except ValueError:
                    d[dst] = v
            out[ex] = d
    return out


def read_refold(run: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for scored in sorted(run.glob("scored-*")):
        path = scored / "refold_metrics.csv"
        if not path.exists():
            continue
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                qid = row.get("query_id")
                if not qid:
                    continue
                d = {}
                for src, dst in WANTED_REFOLD.items():
                    v = row.get(src)
                    if v in (None, ""):
                        continue
                    try:
                        f = float(v)
                        d[dst] = int(f) if f.is_integer() else round(f, 5)
                    except ValueError:
                        d[dst] = v
                out[qid] = d
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--weight", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--prefix", default=None, help="design_id prefix (default: run dir name)")
    ap.add_argument("--track", default="optimisation")
    ap.add_argument("--format", dest="fmt", default="scfv")
    ap.add_argument("--skip-novelty", action="store_true")
    args = ap.parse_args()

    run = args.run
    prefix = args.prefix or run.name
    samples = run / "design" / "generation" / "inference_samples"
    if not samples.is_dir():
        raise SystemExit(f"no designs found under {samples}")

    universe = set() if args.skip_novelty else load_universe()
    metrics = read_metrics(run)
    refold = read_refold(run)

    cifs = sorted(samples.glob("*/*_generated.cif"))
    rows = []
    skipped = []
    for cif in cifs:
        example_id = cif.parent.name
        chains = parse_cif_chains(cif)
        vh = chains.get("B", "")
        vl = chains.get("A", "")
        cdrh3 = extract_cdrh3(vh) if vh else None
        if not vh or not cdrh3:
            skipped.append((example_id, "could not parse VH or locate CDRH3"))
            continue
        muts = (
            sum(1 for a, b in zip(cdrh3, PARENT_CDRH3) if a != b)
            if len(cdrh3) == len(PARENT_CDRH3) else None
        )
        row = {
            "design_id": f"{prefix}-{example_id}",
            "batch": prefix,
            "example_id": example_id,
            "vh": vh,
            "vl": vl,
            "cdrh3": cdrh3,
            "generator": f"rfd4-proteina:{args.weight}",
            "track": args.track,
            "format": args.fmt,
            "seed": args.seed,
            "parent": "trastuzumab",
        }
        nov = {
            "cdrh3_length": len(cdrh3),
            "mutations_from_parent": muts,
            "identity_to_parent": (
                round(1 - muts / len(cdrh3), 4) if muts is not None else None
            ),
        }
        if universe:
            mh = min_substitutions_capped(cdrh3, universe)
            nov["min_substitutions_from_any_provided"] = mh
            nov["min_substitutions_is_capped_at_2"] = True
            nov["in_provided_data"] = (mh == 0)
            # The filter: >=2 differences from every provided sequence, and at
            # least 4 of 10 changed from the parent (the strict <70% reading).
            nov["passes_novelty"] = bool(mh is not None and mh >= 2)
            nov["passes_identity_ceiling"] = bool(muts is not None and muts >= 4)
            nov["passes_challenge_filter"] = bool(
                nov["passes_novelty"] and nov["passes_identity_ceiling"]
            )
        row["novelty"] = nov
        if example_id in metrics:
            row["design_metrics"] = metrics[example_id]
        if example_id in refold:
            row["refold"] = refold[example_id]
        rows.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    # ---- summary, so the log says what we actually got ----
    n = len(rows)
    print(f"exported {n} designs -> {args.out}")
    if skipped:
        print(f"skipped {len(skipped)}:")
        for ex, why in skipped[:5]:
            print(f"  {ex}: {why}")
    if not n:
        return
    uniq = len({r["cdrh3"] for r in rows})
    print(f"distinct CDRH3: {uniq}/{n} ({100*uniq/n:.0f}%)")
    with_refold = sum(1 for r in rows if "refold" in r)
    print(f"refolded: {with_refold}/{n}")
    if universe:
        known = sum(1 for r in rows if r["novelty"].get("in_provided_data"))
        nov_ok = sum(1 for r in rows if r["novelty"].get("passes_novelty"))
        id_ok = sum(1 for r in rows if r["novelty"].get("passes_identity_ceiling"))
        both = sum(1 for r in rows if r["novelty"].get("passes_challenge_filter"))
        print(f"already in the provided data (known): {known}/{n} ({100*known/n:.0f}%)")
        print(f"passes novelty (>=2 from all provided): {nov_ok}/{n} ({100*nov_ok/n:.0f}%)")
        print(f"passes identity ceiling (>=4 from parent): {id_ok}/{n} ({100*id_ok/n:.0f}%)")
        print(f"PASSES THE CHALLENGE FILTER: {both}/{n} ({100*both/n:.0f}%)")
        muts = [r["novelty"]["mutations_from_parent"] for r in rows
                if r["novelty"].get("mutations_from_parent") is not None]
        if muts:
            hist = {}
            for m in muts:
                hist[m] = hist.get(m, 0) + 1
            print(f"substitutions from parent: {dict(sorted(hist.items()))}")


if __name__ == "__main__":
    main()
