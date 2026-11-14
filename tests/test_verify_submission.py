"""The construct verifier, against designs that change more than one CDR.

`scripts/verify_submission.py` re-derives each submitted construct from its
design record. Its framework check used to mask only CDRH3, which is correct
for the optA/optB batches — those redesign that loop alone — and wrong for
multicdr, whose whole purpose (`antibody-2026-10-30`, "redesign any CDR on a
fixed framework") is to vary CDRH1 and CDRH2 as well.

So every multicdr design read as a corrupted framework. On the 20-design
submission, `multicdr-her2_multicdr_98` failed with 13 substitutions, all 13
inside CDRs (H1 2, H2 4, H3 7) and none in framework.

That false positive is expensive in both directions: it prints "do not submit
this sheet" over a correct molecule, and multicdr is the batch kept
specifically so the shortlist is not four variants of one loop — so the design
most likely to be dropped on a bad verdict is the one carrying the diversity.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "verify_submission", ROOT / "scripts" / "verify_submission.py"
)
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)

PARENT = json.loads((ROOT / "data/reference/trastuzumab.json").read_text())
VH = PARENT["vh"]["sequence"]
VL = PARENT["vl"]["sequence"]
CDRS = PARENT["cdrs_kabat"]


def swap(seq: str, old: str, new: str) -> str:
    assert old in seq, f"{old!r} not found"
    assert len(old) == len(new), "same-length swap keeps every offset stable"
    return seq.replace(old, new, 1)


def case(vh: str, cdrh3: str, track: str = "optimisation") -> list[str]:
    """Run the verifier over a construct built from `vh`."""
    rec = {
        "design_id": "t",
        "vh": vh,
        "vl": VL,
        "cdrh3": cdrh3,
        "track": track,
        "parent": "trastuzumab",
    }
    row = {"design_id": "t", "sequence": vh + vs.LINKER + VL, "length_aa": ""}
    return vs.check(row, rec, PARENT)


class TestMultiCDRIsNotAFrameworkChange(unittest.TestCase):
    def test_cdrh1_and_cdrh2_changes_are_not_framework_changes(self):
        h3 = "WKSSYYYYFD"
        vh = swap(VH, CDRS["cdr_h1"], "GFNIKDTYIY")
        vh = swap(vh, CDRS["cdr_h2"], "RIYPTNGYTRYADSVKA")
        vh = swap(vh, CDRS["cdr_h3"], h3)
        bad = case(vh, h3)
        self.assertEqual(
            [b for b in bad if "framework" in b], [],
            f"CDR changes read as framework damage: {bad}",
        )

    def test_a_real_framework_change_is_still_caught(self):
        """The check must not have been loosened into uselessness."""
        h3 = "WKSSYYYYFD"
        vh = swap(VH, CDRS["cdr_h3"], h3)
        i = 5  # well outside every CDR
        vh = vh[:i] + ("A" if vh[i] != "A" else "G") + vh[i + 1:]
        bad = case(vh, h3)
        self.assertTrue(
            any("framework" in b for b in bad),
            f"a real framework change slipped through: {bad}",
        )

    def test_cdrh3_only_design_still_passes(self):
        h3 = "WKSSYYYYFD"
        vh = swap(VH, CDRS["cdr_h3"], h3)
        self.assertEqual(case(vh, h3), [])

    def test_an_altered_light_chain_is_still_caught(self):
        h3 = "WKSSYYYYFD"
        vh = swap(VH, CDRS["cdr_h3"], h3)
        rec = {
            "design_id": "t", "vh": vh, "vl": "A" + VL[1:], "cdrh3": h3,
            "track": "optimisation", "parent": "trastuzumab",
        }
        row = {"design_id": "t", "sequence": vh + vs.LINKER + rec["vl"], "length_aa": ""}
        self.assertTrue(any("VL" in b for b in vs.check(row, rec, PARENT)))


if __name__ == "__main__":
    unittest.main()
