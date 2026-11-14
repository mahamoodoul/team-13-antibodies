"""The order sheet — the one artefact that turns into molecules.

What these tests defend, in priority order:

  1. A sheet for a run that is not submission-ready cannot look clean. Every
     other test here is secondary to that one, because a report that overstates
     costs us points and an order sheet that overstates costs us the wells.
  2. The affinity bar is the parent's geometric mean over its own replicates,
     and the 6.24x spread is stated next to it.
  3. Priority is not rank: ranks 1-4 are guaranteed wells, the rest reserves.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fourwells import ordersheet
from fourwells.schema import AXES, DesignRecord, write_jsonl

TRAS_VH = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKG"
    "RFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
)
TRAS_CDRH3 = "WGGDGFYAMD"


def make(design_id: str, cdrh3: str, **kw) -> DesignRecord:
    rec = DesignRecord(
        design_id=design_id,
        sequence=TRAS_VH.replace(TRAS_CDRH3, cdrh3),
        track=kw.pop("track", "optimisation"),
        format=kw.pop("format", "scfv"),
        parent="trastuzumab",
        cdrh3=cdrh3,
        **kw,
    )
    rec.axes = {a: 0.55 for a in AXES}
    rec.joint_score = 0.166
    rec.gates.passed = True
    rec.gates.checks = {"abguard": {"status": "pass"}}
    rec.cdrh3_identity_to_tras = 0.4
    return rec


def clean_shortlist(n: int = 5) -> tuple[list[DesignRecord], list[DesignRecord]]:
    """n designs that pass everything, so only the thing under test can block."""
    loops = [
        "WRGVTFYMAY", "WMFDWFYADF", "WTSVGIKWMD", "WIGDANYKMD",
        "WGFDIFWVMD", "EMGDGWYMMD", "PGEDGFYIKD", "SGGIGDWNNK",
    ]
    recs = []
    for i in range(n):
        r = make(f"d{i}", loops[i % len(loops)])
        r.cluster = f"c{i}"
        r.rationale = [
            f"Joint P(S-tier) 0.166 = binding 0.55 x epitope 0.55 x stability 0.55.",
            "Binding: 6 of 10 CDRH3 positions changed",
            f"Represents cluster c{i} — a hypothesis no other design tests.",
            f"On the list because its strongest axis is stability and it clears every gate.",
        ]
        r.kill_criterion = "Fails if SPR K_D comes back above the parent's."
        r.joint_score = 0.166 - i * 0.01
        recs.append(r)
    # Two tracks, so the single-track blocker does not fire on a "clean" fixture.
    recs[-1].track = "de_novo"
    selected = recs[:4]
    for i, r in enumerate(selected, start=1):
        r.selected = True
        r.rank = i
    return recs, selected


class TestReadiness(unittest.TestCase):
    def test_stub_rows_block_the_sheet(self):
        recs, sel = clean_shortlist()
        recs[0].is_stub = True
        blockers = ordersheet.readiness(recs, recs)
        self.assertTrue(any("STUB" in b for b in blockers))

    def test_missing_abguard_blocks_the_sheet(self):
        recs, sel = clean_shortlist()
        recs[0].gates.checks = {"abguard": {"status": "NOT RUN"}}
        blockers = ordersheet.readiness(recs, recs)
        self.assertTrue(any("abguard" in b for b in blockers))

    def test_absent_provided_set_blocks_the_sheet(self):
        recs, sel = clean_shortlist()
        recs[0].gates.checks["provided_note"] = "provided-antibody set absent"
        blockers = ordersheet.readiness(recs, recs)
        self.assertTrue(any("novelty" in b for b in blockers))

    def test_single_track_is_named_as_an_empty_entry(self):
        recs, sel = clean_shortlist()
        for r in recs:
            r.track = "optimisation"
        blockers = ordersheet.readiness(recs, recs)
        self.assertTrue(any("judged" in b for b in blockers))

    def test_short_list_names_the_empty_slots(self):
        recs, sel = clean_shortlist(5)
        blockers = ordersheet.readiness(recs, recs)
        self.assertTrue(any("cap of 20" in b for b in blockers))


class TestRendering(unittest.TestCase):
    def test_blocked_sheet_says_so_before_any_sequence(self):
        """The banner has to precede the table, not sit under it."""
        recs, sel = clean_shortlist()
        for r in recs:
            r.is_stub = True
        md = ordersheet.render_markdown(recs, sel, {"run_id": "t"})
        self.assertIn("NOT READY TO ORDER", md)
        self.assertLess(md.index("NOT READY TO ORDER"), md.index("## Sequences"))

    def test_the_bar_is_the_geometric_mean_with_its_spread(self):
        recs, sel = clean_shortlist()
        md = ordersheet.render_markdown(recs, sel, {})
        self.assertIn("0.0954 nM", md)
        self.assertIn("6.24", md)

    def test_first_four_are_lab_and_the_rest_reserves(self):
        recs, sel = clean_shortlist(6)
        table = ordersheet.rows(
            ordersheet.build_shortlist(recs, sel), 6.24
        )
        self.assertEqual([r["priority"] for r in table][:4], ["LAB"] * 4)
        self.assertTrue(all(r["priority"] == "reserve" for r in table[4:]))

    def test_why_is_not_the_joint_arithmetic(self):
        """The joint score is already a column; the reason must say more."""
        recs, sel = clean_shortlist()
        table = ordersheet.rows(ordersheet.build_shortlist(recs, sel), 6.24)
        for r in table:
            self.assertNotIn("Joint P(S-tier)", r["why"])
            self.assertIn("On the list because", r["why"])

    def test_a_design_with_no_rationale_says_do_not_order(self):
        recs, sel = clean_shortlist()
        recs[0].rationale = []
        recs[0].cluster = None
        self.assertIn("do not order", ordersheet._why(recs[0]).lower())

    def test_near_coin_flip_binding_is_marked_inside_the_noise(self):
        rec = make("borderline", "WRGVTFYMAY")
        rec.axes = {"binding": 0.5, "epitope": 0.6, "stability": 0.6}
        self.assertIn("inside the noise", ordersheet._noise_note(rec, 6.24))

    def test_unscored_binding_is_not_silently_passed(self):
        rec = make("unscored", "WRGVTFYMAY")
        rec.axes = {"binding": None, "epitope": 0.6, "stability": 0.6}
        self.assertIn("unscored", ordersheet._noise_note(rec, 6.24))

    def test_html_is_self_contained_and_escapes_its_content(self):
        recs, sel = clean_shortlist()
        recs[0].design_id = "<script>alert(1)</script>"
        htm = ordersheet.render_html(recs, sel, {})
        self.assertNotIn("<script>alert", htm)
        self.assertNotIn("http://", htm)
        self.assertNotIn("https://", htm)
        self.assertIn("<!DOCTYPE html>", htm)

    def test_sequences_are_printed_in_full(self):
        recs, sel = clean_shortlist()
        md = ordersheet.render_markdown(recs, sel, {})
        for r in recs[:4]:
            self.assertIn(r.sequence, md)


class TestEntryPoint(unittest.TestCase):
    def test_round_trips_from_a_run_directory(self):
        recs, sel = clean_shortlist()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write_jsonl(recs, d / "designs.jsonl")
            write_jsonl(sel, d / "selected.jsonl")
            (d / "config.json").write_text(json.dumps({"run_id": "rt", "target": "HER2"}))
            self.assertEqual(ordersheet.main([str(d)]), 0)
            self.assertIn("HER2", (d / "order-sheet.md").read_text())
            self.assertTrue((d / "order-sheet.html").exists())

    def test_missing_run_directory_is_an_error_not_a_blank_sheet(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(ordersheet.main([td]), 1)
            self.assertFalse((Path(td) / "order-sheet.md").exists())


if __name__ == "__main__":
    unittest.main()
