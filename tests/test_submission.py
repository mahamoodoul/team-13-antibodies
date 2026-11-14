"""Phase 7 — the ranked list of up to 20 we actually submit.

What these defend, in order of what it costs to get wrong:

  1. **We submit 20, not 4.** Placing buys 16/12/8 extra wells and each judge
     may nominate one. A list that stops at the guaranteed four forfeits every
     slot we won on the day, silently, and nothing else in the pipeline would
     notice.
  2. **The four keep the portfolio's order at the top.** That order is a joint
     allocation across clusters; re-sorting it by score here would throw the
     diversity decision away.
  3. **Ranks 5-20 spread across hypotheses.** Sixteen slots filled straight
     down the score is one hypothesis tested sixteen times.
  4. **Nothing is invented to fill a cell.** An unscored axis exports empty,
     never zero.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from fourwells import submission
from fourwells.schema import AXES, DesignRecord, write_jsonl
from fourwells.targets import resolve_reference_ab

REF = resolve_reference_ab()
TRAS_VH = REF.vh
TRAS_CDRH3 = REF.cdrh3

LOOPS = [
    "WRGVTFYMAY", "WMFDWFYADF", "WTSVGIKWMD", "WIGDANYKMD", "WGFDIFWVMD",
    "EMGDGWYMMD", "PGEDGFYIKD", "SGGIGDWNNK", "WGHDGIMDMH", "EQGYGFNFDD",
    "HVVRGYYAIL", "YPGRYFYTYD", "WKSSYYYYFD", "SYSTSYYYFD", "YASLYNYYFD",
    "WGFTALYYYD", "WYQYGYYAYE", "WGAGGTYGYE", "WRSTTDYYFD", "WGNRGVYRYD",
    "FGAFGQYSYL", "YGYKHFYDYD", "WSDGYFYAMP", "WRNGSYGTFS", "WHSSYDYYFD",
]


def make(design_id: str, cdrh3: str, cluster: str, joint: float, **kw) -> DesignRecord:
    rec = DesignRecord(
        design_id=design_id,
        sequence=TRAS_VH.replace(TRAS_CDRH3, cdrh3),
        track=kw.pop("track", "optimisation"),
        format="scfv",
        parent="trastuzumab",
        cdrh3=cdrh3,
        **kw,
    )
    rec.axes = {a: 0.5 for a in AXES}
    rec.joint_score = joint
    rec.cluster = cluster
    rec.gates.passed = True
    rec.gates.checks = {"abguard": {"status": "pass"}}
    rec.rationale = [f"represents {cluster}"]
    rec.kill_criterion = "Fails if SPR K_D comes back above the parent's."
    return rec


def pool(n: int = 25, clusters: int = 25) -> tuple[list[DesignRecord], list[DesignRecord]]:
    recs = [
        make(f"d{i:02d}", LOOPS[i % len(LOOPS)], f"c{i % clusters}", 0.09 - i * 0.001)
        for i in range(n)
    ]
    selected = recs[:4]
    for i, r in enumerate(selected, start=1):
        r.selected = True
        r.rank = i
    return recs, selected


class TestRankedList(unittest.TestCase):
    def test_submits_twenty_not_four(self):
        recs, sel = pool(25)
        self.assertEqual(len(submission.build_ranked_list(recs, sel)), 20)

    def test_caps_at_twenty_even_with_a_large_pool(self):
        recs, sel = pool(120, clusters=60)
        self.assertEqual(len(submission.build_ranked_list(recs, sel)), 20)

    def test_short_pool_is_not_padded(self):
        recs, sel = pool(9)
        self.assertEqual(len(submission.build_ranked_list(recs, sel)), 9)

    def test_portfolio_four_lead_in_portfolio_order(self):
        """Not re-sorted by score — that order is a joint allocation."""
        recs, sel = pool(25)
        # Give pick 4 the best score in the pool. It must still rank 4th.
        sel[3].joint_score = 0.99
        ranked = submission.build_ranked_list(recs, sel)
        self.assertEqual([r.design_id for r in ranked[:4]],
                         [r.design_id for r in sel])

    def test_reserves_spread_across_clusters_before_repeating_one(self):
        """Two designs in one cluster, both high-scoring, must not take 5 and 6."""
        recs, sel = pool(25, clusters=25)
        for r in recs[4:]:
            r.cluster = "c_hot" if r.design_id in ("d04", "d05") else r.cluster
        recs[4].joint_score = recs[5].joint_score = 0.088
        ranked = submission.build_ranked_list(recs, sel)
        tail = [r.cluster for r in ranked[4:]]
        self.assertEqual(tail.count("c_hot"), 1, "one cluster took two early slots")

    def test_priority_splits_lab_from_reserve(self):
        self.assertEqual(submission.priority_of(4), "lab")
        self.assertEqual(submission.priority_of(5), "reserve")


class TestExclusions(unittest.TestCase):
    def test_stub_records_never_enter_the_submission(self):
        recs, sel = pool(25)
        recs[10].is_stub = True
        ranked = submission.build_ranked_list(recs, sel)
        self.assertNotIn(recs[10].design_id, [r.design_id for r in ranked])

    def test_gate_failures_never_enter_the_submission(self):
        recs, sel = pool(25)
        recs[11].gates.passed = False
        recs[11].gates.failed_rules = ["length 260 > 250"]
        ranked = submission.build_ranked_list(recs, sel)
        self.assertNotIn(recs[11].design_id, [r.design_id for r in ranked])

    def test_unscored_design_cannot_be_placed_in_a_ranked_list(self):
        recs, sel = pool(25)
        recs[12].joint_score = None
        ranked = submission.build_ranked_list(recs, sel)
        self.assertNotIn(recs[12].design_id, [r.design_id for r in ranked])


class TestReadiness(unittest.TestCase):
    def test_missing_abguard_blocks(self):
        recs, sel = pool(25)
        recs[0].gates.checks = {"abguard": {"status": "NOT RUN"}}
        ranked = submission.build_ranked_list(recs, sel)
        self.assertTrue(any("abguard" in b for b in submission.readiness(recs, ranked)))

    def test_single_track_is_named_as_an_empty_entry(self):
        recs, sel = pool(25)
        ranked = submission.build_ranked_list(recs, sel)
        self.assertTrue(any("judged" in b for b in submission.readiness(recs, ranked)))

    def test_empty_slots_are_counted(self):
        recs, sel = pool(9)
        ranked = submission.build_ranked_list(recs, sel)
        self.assertTrue(any("slots left empty" in b
                            for b in submission.readiness(recs, ranked)))

    def test_two_tracks_and_a_full_list_clears_the_track_blocker(self):
        recs, sel = pool(25)
        for r in recs[12:]:
            r.track = "de_novo"
        ranked = submission.build_ranked_list(recs, sel)
        self.assertFalse(any("judged" in b
                             for b in submission.readiness(recs, ranked)))

    def test_duplicate_constructs_never_take_two_slots(self):
        """The generator emitted the same heavy/light pair twice under different
        seeds. The organisers rank molecules, so the second copy is a wasted
        slot and a false claim of breadth -- and the list must still refill."""
        recs, sel = pool(25)
        # d05 becomes a byte-identical copy of d01 (same loop, same construct).
        recs[5].cdrh3 = recs[1].cdrh3
        recs[5].sequence = recs[1].sequence
        ranked = submission.build_ranked_list(recs, sel)
        seqs = [submission.construct_of(r)[0] for r in ranked]
        self.assertEqual(len(seqs), len(set(seqs)), "no repeated molecule")
        self.assertEqual(len(ranked), 20, "and the cap is still filled")

    def test_a_recorded_decision_clears_only_the_track_blocker(self):
        """A deliberate single-track entry must be recordable, with its reason,
        rather than silently deleted -- and it must never clear an evidence
        blocker."""
        recs, sel = pool(25)
        ranked = submission.build_ranked_list(recs, sel)
        decision = [{"kind": "single_track", "track": "optimisation",
                     "reason": "no de novo construct fits the cap"}]
        self.assertFalse(any("judged" in b for b in
                             submission.readiness(recs, ranked, decision)))
        # No reason, no clearance.
        self.assertTrue(any("judged" in b for b in submission.readiness(
            recs, ranked, [{"kind": "single_track"}])))
        # And a real evidence blocker survives the decision.
        recs[0].gates.checks = {"abguard": {"status": "NOT RUN"}}
        ranked = submission.build_ranked_list(recs, sel)
        self.assertTrue(any("abguard" in b for b in
                            submission.readiness(recs, ranked, decision)))


class TestExports(unittest.TestCase):
    def _write(self, recs, sel):
        d = Path(tempfile.mkdtemp())
        submission.write_all(recs, d, sel)
        return d

    def test_unscored_axis_exports_empty_not_zero(self):
        recs, sel = pool(25)
        sel[0].axes = {"binding": None, "epitope": 0.5, "stability": 0.5}
        d = self._write(recs, sel)
        with open(d / "final_ranked_designs.csv") as fh:
            row = next(csv.DictReader(fh))
        self.assertEqual(row["binding"], "")
        self.assertNotEqual(row["binding"], "0")

    def test_every_candidate_appears_in_candidate_scores(self):
        recs, sel = pool(25)
        d = self._write(recs, sel)
        with open(d / "candidate_scores.csv") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), len(recs))
        self.assertTrue(all(r["excluded_because"] or r["submitted"] == "yes"
                            for r in rows))

    def test_fasta_carries_rank_and_priority(self):
        recs, sel = pool(25)
        d = self._write(recs, sel)
        head = (d / "final_sequences.fasta").read_text().splitlines()[0]
        self.assertIn("rank=1", head)
        self.assertIn("priority=lab", head)

    def test_json_states_readiness_and_never_claims_ready_while_blocked(self):
        recs, sel = pool(25)
        recs[0].gates.checks = {"abguard": {"status": "NOT RUN"}}
        d = self._write(recs, sel)
        blob = json.loads((d / "submission.json").read_text())
        self.assertFalse(blob["submission_ready"])
        self.assertTrue(blob["blockers"])
        self.assertEqual(blob["submitted"], len(blob["designs"]))

    def test_csv_injection_is_neutralised(self):
        recs, sel = pool(25)
        sel[0].design_id = "=cmd|'/c calc'!A1"
        d = self._write(recs, sel)
        with open(d / "final_ranked_designs.csv") as fh:
            row = next(csv.DictReader(fh))
        self.assertTrue(row["design_id"].startswith("'="))


class TestEntryPoint(unittest.TestCase):
    def test_round_trips_from_a_run_directory(self):
        recs, sel = pool(25)
        d = Path(tempfile.mkdtemp())
        write_jsonl(recs, d / "designs.jsonl")
        write_jsonl(sel, d / "selected.jsonl")
        self.assertEqual(submission.main([str(d)]), 0)
        for name in ("final_ranked_designs.csv", "candidate_scores.csv",
                     "final_sequences.fasta", "submission.json"):
            self.assertTrue((d / name).exists(), name)

    def test_missing_run_directory_errors_rather_than_writing_a_blank_list(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(submission.main([str(d)]), 1)
        self.assertFalse((d / "final_ranked_designs.csv").exists())


if __name__ == "__main__":
    unittest.main()
