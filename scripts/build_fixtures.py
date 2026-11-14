#!/usr/bin/env python3
"""Build tidy fixtures for the ranking engine from the provided datasets.

Outputs into ~/data/tidy/ :
  provided_cdrh3_universe.txt  every unique CDRH3 in the provided data (novelty gate set)
  iptm_calibration.csv         long-form ipTM, one row per (model, vhh, antigen, is_cognate)
  trastuzumab_parent.json      the authoritative parent row, taken from the SPR table

Run:  python3 -I scripts/build_fixtures.py
"""
import csv
import json
import os
import sys

HOME = os.path.expanduser("~")
TIDY = os.path.join(HOME, "data", "tidy")
FACS = os.path.join(TIDY, "tz_her2_facs_3classes_524346.csv")
SPR = os.path.join(TIDY, "trastuzumab_her2_spr_all_768.csv")
IPTM = os.path.join(TIDY, "iptm_confidence_scores")

TRAS_CDRH3 = "WGGDGFYAMD"  # 10-residue form used by the provided data and the challenge filter

CDRH3_NOTE = (
    "The provided data and the challenge novelty filter use this 10-residue form. Within the "
    "VH the loop reads YYCSR-WGGDGFYAMDY-WGQGT, so an 11-residue Kabat call (WGGDGFYAMDY) is "
    "also defensible. Compute the gate on the 10-mer, because that is what the provided "
    "tables hold and what the filter is defined against."
)


def main():
    # ---- CDRH3 universe: the novelty gate compares against every provided sequence ----
    facs_cdrh3, spr_cdrh3 = set(), set()
    facs_rows = 0
    with open(FACS, newline="") as fh:
        for r in csv.DictReader(fh):
            facs_rows += 1
            facs_cdrh3.add(r["cdrh3"].strip().upper())

    spr_rows = 0
    tras_row = None
    tras_kds = []
    with open(SPR, newline="") as fh:
        for r in csv.DictReader(fh):
            spr_rows += 1
            c = r["cdrh3"].strip().upper()
            spr_cdrh3.add(c)
            if c == TRAS_CDRH3:
                if tras_row is None:
                    tras_row = dict(r)
                if r["kd_nM"]:
                    tras_kds.append(float(r["kd_nM"]))

    universe = facs_cdrh3 | spr_cdrh3
    with open(os.path.join(TIDY, "provided_cdrh3_universe.txt"), "w") as out:
        for c in sorted(universe):
            out.write(c + "\n")

    print("FACS rows %d, unique CDRH3 %d" % (facs_rows, len(facs_cdrh3)))
    print("SPR  rows %d, unique CDRH3 %d" % (spr_rows, len(spr_cdrh3)))
    print("universe (gate reference set): %d unique CDRH3" % len(universe))
    print("trastuzumab CDRH3 in FACS table? %s" % (TRAS_CDRH3 in facs_cdrh3))
    print("overlap FACS and SPR: %d" % len(facs_cdrh3 & spr_cdrh3))
    lens = {}
    for c in universe:
        lens[len(c)] = lens.get(len(c), 0) + 1
    print("CDRH3 length histogram: %s" % dict(sorted(lens.items())))

    # ---- the parent row, straight from the provided data ----
    if tras_row is None:
        print("WARNING: trastuzumab parent row not found in the SPR table", file=sys.stderr)
    else:
        vh = tras_row["vh_sequence"].strip().upper()
        vl = tras_row["vl_sequence"].strip().upper()
        total = len(vh) + len(vl)
        parent = {
            "_source": "trastuzumab_her2_spr_all_768.csv, rows whose cdrh3 == WGGDGFYAMD",
            "_why": (
                "Every score in this challenge is relative to trastuzumab, and the novelty gate "
                "is computed against its CDRH3. These values come from the provided data, not "
                "from memory."
            ),
            "cdrh3_10mer": TRAS_CDRH3,
            "cdrh3_note": CDRH3_NOTE,
            "vh_sequence": vh,
            "vh_length": len(vh),
            "vl_sequence": vl,
            "vl_length": len(vl),
            "vh_plus_vl_length": total,
            "abguard_length_limit": 250,
            "length_ok": total <= 250,
            "reference_kd_nM": sorted(tras_kds),
            "reference_kd_n": len(tras_kds),
            "cysteines_vh": vh.count("C"),
            "cysteines_vl": vl.count("C"),
        }
        with open(os.path.join(TIDY, "trastuzumab_parent.json"), "w") as out:
            json.dump(parent, out, indent=2)
        verdict = "OK" if total <= 250 else "FAIL"
        print()
        print("--- trastuzumab parent row (authoritative) ---")
        print("  VH %d aa, VL %d aa, total %d aa (limit 250: %s)" % (len(vh), len(vl), total, verdict))
        print("  measured KD (nM): %s" % sorted(tras_kds))
        print("  cysteines: VH %d, VL %d" % (vh.count("C"), vl.count("C")))

    # ---- ipTM calibration set, long form ----
    out_path = os.path.join(TIDY, "iptm_calibration.csv")
    n = 0
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "vhh_pdb", "antigen_pdb", "iptm", "is_cognate"])
        for model in ("af3", "boltz2", "chai1"):
            path = os.path.join(IPTM, "%s_matrix_clean.csv" % model)
            with open(path, newline="") as mfh:
                rows = list(csv.reader(mfh))
            hdr = rows[0][1:]
            for r in rows[1:]:
                nb = r[0]
                for ag, v in zip(hdr, r[1:]):
                    try:
                        x = float(v)
                    except ValueError:
                        continue
                    w.writerow([model, nb, ag, x, int(nb == ag)])
                    n += 1
    print()
    print("iptm_calibration.csv: %d rows" % n)


if __name__ == "__main__":
    main()
