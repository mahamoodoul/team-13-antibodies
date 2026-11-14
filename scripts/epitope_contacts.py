#!/usr/bin/env python3
"""Which HER2 residues does a refolded design actually touch?

score.py caps the epitope axis without structural evidence and says the contacts
should come from the refold. This reads them off the refolded complex: any target
residue with a heavy atom within the cutoff of any binder heavy atom.

That is the real measurement behind "it binds where trastuzumab binds". The
annotated trastuzumab epitope is in data/reference/trastuzumab.json; the overlap
between that and these contacts is what the epitope axis scores.

Usage:
  python3 -I scripts/epitope_contacts.py <model.cif> [--cutoff 4.5]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

BINDER_CHAINS = ("A", "B", "H", "L")
TARGET_CHAINS = ("C", "D")
DEFAULT_CUTOFF = 4.5  # Angstrom, heavy-atom contact


def read_coords(path: Path) -> list[tuple[str, int, str, float, float, float]]:
    """(chain, resnum, element, x, y, z) for every heavy atom."""
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
                el = (rec.get("type_symbol") or "").upper()
                if el == "H" or el == "D":
                    continue  # heavy atoms only
                chain = rec.get("auth_asym_id") or rec.get("label_asym_id")
                try:
                    resnum = int(rec.get("auth_seq_id") or rec.get("label_seq_id"))
                    x = float(rec["Cartn_x"]); y = float(rec["Cartn_y"]); z = float(rec["Cartn_z"])
                except (TypeError, ValueError, KeyError):
                    continue
                if chain:
                    out.append((chain, resnum, el, x, y, z))
            elif in_loop and s.startswith("#"):
                in_loop = False
    return out


def contacts(
    path: Path,
    binder_chains=BINDER_CHAINS,
    target_chains=TARGET_CHAINS,
    cutoff: float = DEFAULT_CUTOFF,
) -> dict:
    atoms = read_coords(path)
    binder = [a for a in atoms if a[0] in binder_chains]
    target = [a for a in atoms if a[0] in target_chains]
    if not binder or not target:
        return {"contacts": [], "n_binder_atoms": len(binder), "n_target_atoms": len(target),
                "_why": "a chain was missing from the refolded model"}

    # Bucket the binder atoms into cutoff-sized cells so each target atom only
    # compares against its own neighbourhood. Brute force is ~2000x800 = 1.6M
    # distance checks per design, which is slow across hundreds of designs.
    cell = cutoff
    grid: dict[tuple[int, int, int], list] = {}
    for a in binder:
        key = (int(a[3] // cell), int(a[4] // cell), int(a[5] // cell))
        grid.setdefault(key, []).append(a)

    c2 = cutoff * cutoff
    hit: dict[int, float] = {}
    for _, resnum, _, x, y, z in target:
        bx, by, bz = int(x // cell), int(y // cell), int(z // cell)
        best = hit.get(resnum)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for _, _, _, px, py, pz in grid.get((bx + dx, by + dy, bz + dz), ()):
                        d2 = (x - px) ** 2 + (y - py) ** 2 + (z - pz) ** 2
                        if d2 <= c2 and (best is None or d2 < best):
                            best = d2
        if best is not None:
            prev = hit.get(resnum)
            if prev is None or best < prev:
                hit[resnum] = best

    return {
        "contacts": sorted(hit),
        "min_distance_by_residue": {str(k): round(math.sqrt(v), 2) for k, v in sorted(hit.items())},
        "cutoff_angstrom": cutoff,
        "n_contacts": len(hit),
        "binder_chains": list(binder_chains),
        "target_chains": list(target_chains),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cif", type=Path)
    ap.add_argument("--cutoff", type=float, default=DEFAULT_CUTOFF)
    args = ap.parse_args()
    res = contacts(args.cif, cutoff=args.cutoff)
    print(f"{res['n_contacts']} target residues within {args.cutoff} A of the binder")
    print("contacts:", res["contacts"])


if __name__ == "__main__":
    main()
