#!/usr/bin/env python3
"""Keep only named chains in an mmCIF, so a target file holds the target alone.

The HER2 example ships the antigen and the trastuzumab Fv in one file. The de novo
design spec references only the HER2 chains, and RFD4 rejected the input with
"Invalid RFD4-Proteina design input" -- most likely because chains present in the
file appear in no condition and no contig entry. This writes a file holding just
the chains asked for.

Only the atom_site loop is filtered. Other categories are copied through, except
that single-row categories keyed by chain are left alone -- they are metadata the
design path does not read. If the validator turns out to read them, the fix is to
build the target file from the PDB entry instead.

Usage: python3 -I cif_subset.py in.cif out.cif C D
"""
from __future__ import annotations

import sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    keep = set(sys.argv[3:])
    if not keep:
        raise SystemExit("name at least one chain to keep")

    out_lines: list[str] = []
    cols: list[str] = []
    in_loop = False
    kept = dropped = 0

    with open(src) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("_atom_site."):
                cols.append(s.split(".", 1)[1].split()[0])
                in_loop = True
                out_lines.append(line)
                continue
            if in_loop and (s.startswith("ATOM") or s.startswith("HETATM")):
                parts = s.split()
                if len(parts) >= len(cols):
                    rec = dict(zip(cols, parts))
                    chain = rec.get("auth_asym_id") or rec.get("label_asym_id")
                    if chain not in keep:
                        dropped += 1
                        continue
                    kept += 1
                out_lines.append(line)
                continue
            if in_loop and s.startswith("#"):
                in_loop = False
            out_lines.append(line)

    with open(dst, "w") as out:
        out.writelines(out_lines)

    print(f"wrote {dst}: kept {kept} atoms in chains {sorted(keep)}, dropped {dropped}")


if __name__ == "__main__":
    main()
