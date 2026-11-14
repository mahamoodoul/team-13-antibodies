"""Local PDB inspection and target-residue contact comparison, without a model.

Residue IDs must use the same target numbering in reference and prediction.
Contact recovery measures a predicted interface, never experimental competition.
"""
from __future__ import annotations

import math
from pathlib import Path


def atoms(path):
    out = []
    for line in Path(path).read_text().splitlines():
        if line.startswith("ENDMDL"):
            break  # first model only
        if line[:6].strip() != "ATOM" or line[16:17] not in (" ", "A"):
            continue
        try:
            atom = {"name": line[12:16].strip(), "chain": line[21:22].strip() or "_",
                    "residue": line[22:27].strip(), "resname": line[17:20].strip(),
                    "xyz": [float(line[30:38]), float(line[38:46]), float(line[46:54])]}
        except ValueError:
            continue
        if all(math.isfinite(v) for v in atom["xyz"]) and not atom["name"].startswith("H"):
            out.append(atom)
    if not out:
        raise ValueError("No PDB ATOM coordinates found; convert mmCIF to PDB before importing")
    return out


def target_contacts(points, target_chains, binder_chains, cutoff=5.0):
    if not target_chains or not binder_chains or set(target_chains) & set(binder_chains):
        raise ValueError("Specify separate target and antibody chains")
    present = {p["chain"] for p in points}
    if not set(target_chains + binder_chains) <= present:
        raise ValueError("Requested target or antibody chain is missing")
    residue_chains = {}
    for p in points:
        if p["chain"] in target_chains:
            prior = residue_chains.setdefault(p["residue"], p["chain"])
            if prior != p["chain"]:
                raise ValueError("Target residue numbering overlaps between chains; provide unique HER2 numbering")
    # Spatial bins keep complex comparisons linear for ordinary PDB files.
    cells = {}
    for p in points:
        if p["chain"] in binder_chains:
            key = tuple(math.floor(v / cutoff) for v in p["xyz"])
            cells.setdefault(key, []).append(p["xyz"])
    contacts = set()
    for p in points:
        if p["chain"] not in target_chains:
            continue
        x, y, z = (math.floor(v / cutoff) for v in p["xyz"])
        for i in range(x - 1, x + 2):
            for j in range(y - 1, y + 2):
                for k in range(z - 1, z + 2):
                    if any(sum((a - b) ** 2 for a, b in zip(p["xyz"], q)) <= cutoff ** 2
                           for q in cells.get((i, j, k), [])):
                        contacts.add(p["residue"])
    return contacts


def compare_interface(candidate, reference, target_chains, binder_chains,
                      reference_target_chains, reference_binder_chains):
    c = target_contacts(atoms(candidate), target_chains, binder_chains)
    r = target_contacts(atoms(reference), reference_target_chains, reference_binder_chains)
    if not r:
        raise ValueError("Reference has no target contacts at 5 angstrom")
    return {"method": "target-contact-recall-5A", "version": "1", "unit": "fraction",
            "direction": "max", "kind": "prediction", "value": len(c & r) / len(r),
            "reference_value": 1.0, "source": f"structures/{Path(reference).name} + structures/{Path(candidate).name}",
            "candidate_contacts": sorted(c), "reference_contacts": sorted(r),
            "lost_contacts": sorted(r - c), "new_contacts": sorted(c - r),
            "limitations": "Requires identical target residue numbering. Contact recovery is not a competitive binding assay."}
