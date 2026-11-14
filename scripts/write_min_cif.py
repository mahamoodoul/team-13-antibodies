#!/usr/bin/env python3
"""Write a clean minimal mmCIF holding only the chains asked for.

cif_subset.py filtered the atom_site loop but left every other category intact,
so the file still declared entities and asym units for chains whose atoms were
gone. The shipped Fv example's target file holds its target alone, with matching
metadata. This writes a file from scratch: a data_ block, a minimal entity and
struct_asym description that matches what is actually present, and the atom_site
loop. Nothing stale.

Optionally renumbers each chain from 1, since the shipped example's target is
numbered 1-76 and HER2's own numbering starts at 489 -- the one difference the
bisect never varied.

Usage:
  python3 -I write_min_cif.py in.cif out.cif --chains C D [--renumber]
"""
from __future__ import annotations

import argparse

# Exactly the columns the shipped example files carry, in their order. RFD4
# rejects a multi-input design with "Annotation mismatch across inputs: 1D
# annotations ['b_factor']" when the inputs disagree on per-atom annotations, so
# the target file must not carry occupancy or B_iso_or_equiv that the framework
# file lacks.
FIELDS = [
    "group_PDB", "type_symbol", "label_atom_id", "label_alt_id", "label_comp_id",
    "label_asym_id", "label_entity_id", "label_seq_id", "pdbx_PDB_ins_code",
    "auth_seq_id", "auth_comp_id", "auth_asym_id", "auth_atom_id",
    "Cartn_x", "Cartn_y", "Cartn_z", "pdbx_PDB_model_num", "id",
]


def read_atoms(path: str, keep: set[str]) -> list[dict]:
    cols: list[str] = []
    in_loop = False
    out = []
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
                if chain in keep:
                    out.append(rec)
            elif in_loop and s.startswith("#"):
                in_loop = False
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--chains", nargs="+", required=True)
    ap.add_argument("--renumber", action="store_true")
    ap.add_argument("--name", default="target")
    args = ap.parse_args()

    keep = set(args.chains)
    atoms = read_atoms(args.src, keep)
    if not atoms:
        raise SystemExit("no atoms kept")

    # chain -> ordered unique residue numbers, for optional renumbering
    order: dict[str, list[str]] = {}
    for a in atoms:
        ch = a.get("auth_asym_id") or a.get("label_asym_id")
        rn = a.get("auth_seq_id")
        order.setdefault(ch, [])
        if not order[ch] or order[ch][-1] != rn:
            if rn not in order[ch]:
                order[ch].append(rn)
    remap = {
        ch: {old: str(i + 1) for i, old in enumerate(nums)} for ch, nums in order.items()
    }

    chains = sorted(order)
    entity_of = {ch: str(i + 1) for i, ch in enumerate(chains)}

    lines = [f"data_{args.name}", "#"]
    # entity: one polymer entity per chain, so nothing is declared that is absent
    lines += ["loop_", "_entity.id", "_entity.type"]
    for ch in chains:
        lines.append(f"{entity_of[ch]} polymer")
    lines.append("#")
    lines += ["loop_", "_struct_asym.id", "_struct_asym.entity_id"]
    for ch in chains:
        lines.append(f"{ch} {entity_of[ch]}")
    lines.append("#")
    lines += ["loop_"] + [f"_atom_site.{f}" for f in FIELDS]

    for i, a in enumerate(atoms, start=1):
        ch = a.get("auth_asym_id") or a.get("label_asym_id")
        rn = a.get("auth_seq_id")
        new_rn = remap[ch][rn] if args.renumber else rn
        row = {
            "group_PDB": a.get("group_PDB", "ATOM"),
            "id": str(i),
            "type_symbol": a.get("type_symbol", "C"),
            "label_atom_id": a.get("label_atom_id", "CA"),
            "label_alt_id": ".",
            "label_comp_id": a.get("label_comp_id", "UNK"),
            "label_asym_id": ch,
            "label_entity_id": entity_of[ch],
            "label_seq_id": new_rn,
            "pdbx_PDB_ins_code": "?",
            "Cartn_x": a.get("Cartn_x", "0.000"),
            "Cartn_y": a.get("Cartn_y", "0.000"),
            "Cartn_z": a.get("Cartn_z", "0.000"),
            "auth_seq_id": new_rn,
            "auth_comp_id": a.get("auth_comp_id", a.get("label_comp_id", "UNK")),
            "auth_asym_id": ch,
            "auth_atom_id": a.get("auth_atom_id", a.get("label_atom_id", "CA")),
            "pdbx_PDB_model_num": "1",
        }
        lines.append(" ".join(row[f] for f in FIELDS))
    lines.append("#")

    with open(args.dst, "w") as out:
        out.write("\n".join(lines) + "\n")

    print(f"wrote {args.dst}: {len(atoms)} atoms, chains {chains}")
    for ch in chains:
        nums = order[ch]
        if args.renumber:
            print(f"  {ch}: {len(nums)} residues renumbered 1-{len(nums)} (was {nums[0]}-{nums[-1]})")
        else:
            print(f"  {ch}: {len(nums)} residues, {nums[0]}-{nums[-1]}")


if __name__ == "__main__":
    main()
