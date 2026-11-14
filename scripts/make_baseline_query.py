#!/usr/bin/env python3
"""Build a Boltz-2 query for trastuzumab itself, for use as the baseline row.

Takes the holo queries.json that refold-prepare wrote for a design batch, keeps the HER2
chains and the parent light chain exactly as they are, and swaps the heavy chain back to
the parent VH. The result folds the parent complex through the identical path as every
design, so its confidence metrics are directly comparable.

Usage: python3 -I make_baseline_query.py <prepared/holo/queries.json> <out/queries.json>
"""
import json
import sys

# Verified against trastuzumab_her2_spr_all_768.csv (the 8 reference rows).
PARENT_VH = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNT"
    "AYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
)
PARENT_VL = (
    "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSL"
    "QPEDFATYYCQQHYTTPPTFGQGTKVEIK"
)
CDRH3_10MER = "WGGDGFYAMD"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as fh:
        data = json.load(fh)

    q = json.loads(json.dumps(data["queries"][0]))  # deep copy of the first design query
    q["query_id"] = "trastuzumab_parent"

    seen = {}
    for ch in q["chains"]:
        seen[ch["chain_id"]] = len(ch["sequence"])
        if ch["chain_id"] == "B":
            ch["sequence"] = PARENT_VH
        elif ch["chain_id"] == "A":
            ch["sequence"] = PARENT_VL

    # Fail loudly rather than silently fold the wrong thing.
    if seen.get("B") != len(PARENT_VH):
        raise SystemExit(
            "heavy chain length changed: design B was %s aa, parent VH is %s aa. The design "
            "spec may have altered CDRH3 length; check before trusting this baseline."
            % (seen.get("B"), len(PARENT_VH))
        )
    if seen.get("A") != len(PARENT_VL):
        raise SystemExit(
            "light chain length mismatch: design A was %s aa, parent VL is %s aa"
            % (seen.get("A"), len(PARENT_VL))
        )
    if CDRH3_10MER not in PARENT_VH:
        raise SystemExit("parent CDRH3 not found in parent VH")

    with open(dst, "w") as out:
        json.dump({"queries": [q]}, out)

    chains = ", ".join("%s:%s aa" % (c["chain_id"], len(c["sequence"])) for c in q["chains"])
    print("wrote %s" % dst)
    print("  query_id: %s" % q["query_id"])
    print("  chains:   %s" % chains)
    print("  CDRH3:    %s (the 10-mer the gate is computed against)" % CDRH3_10MER)


if __name__ == "__main__":
    main()
