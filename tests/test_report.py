"""Tests for the report and the run directory — OWNER: Mahamoodoul.

    python3 -m unittest discover -s tests -v

The report is the artefact the judges are guaranteed to see, so these pin the
properties the pitch actually claims about it rather than that it merely
renders. Four of them are the claims most likely to be challenged:

  - the submission is a ranked list of up to 20, not just the four lab slots
  - a prediction is never printed without being labelled a prediction
  - runs never overwrite each other and carry the commit they came from
  - a rendering failure cannot lose the records

The HTML must also open with no network, so one test asserts there is no
external reference and no script in it at all.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from fourwells import report
from fourwells.runner import RunResult, make_run_id, write_outputs
from fourwells.schema import AXES, DesignRecord

VOID = {"meta", "br", "hr", "img", "input", "link", "source", "col",
        "area", "base", "wbr", "embed", "track", "param"}


def make(design_id: str, joint: float, *, selected: bool = False, rank=None,
         passed: bool = True, failed=None, **kw) -> DesignRecord:
    rec = DesignRecord(design_id=design_id, sequence="QVQLVQSGAEVKKPGAS" * 2)
    rec.track = kw.get("track", "optimisation")
    rec.format = "scfv"
    rec.cdrh3 = kw.get("cdrh3", "WGSQGFYAYD")
    rec.cdrh3_identity_to_tras = kw.get("identity", 0.6)
    rec.cluster = kw.get("cluster", "c1")
    rec.gates.passed = passed
    rec.gates.failed_rules = list(failed or [])
    # A plausible decomposition whose product is the joint score.
    per = joint ** (1 / 3)
    rec.axes = {a: per for a in AXES}
    rec.joint_score = joint
    rec.selected = selected
    rec.rank = rank
    rec.rationale = [f"{design_id} is here because the test put it here"]
    rec.kill_criterion = "loses the epitope competition"
    return rec


def a_run(n_pass: int = 30, n_fail: int = 5, budget: int = 4):
    """A pool of gate-passing designs plus some rejects, with `budget` selected."""
    records = []
    for i in range(n_pass):
        # descending joint score, so rank order is unambiguous
        records.append(make(f"d{i:03d}", 0.5 - i * 0.01, cluster=f"c{i}"))
    for i in range(n_fail):
        records.append(make(f"x{i:03d}", 0.9, passed=False,
                            failed=[f"CDRH3 identity 0.{90 - i} >= 0.7"]))
    for rank, rec in enumerate(records[:budget], 1):
        rec.selected, rec.rank = True, rank
    result = RunResult(records=records)
    result.warnings.append("this is a test run, not designs")
    return result


class TestRuleGrouping(unittest.TestCase):
    """REGRESSION: the funnel tallied one rule as several.

    Gate messages embed the measurement that tripped them, so
    "CDRH3 identity 0.90 >= 0.7" and "CDRH3 identity 0.80 >= 0.7" are one rule
    failing twice. The first fix truncated at the first token containing a
    digit, which broke on the very first token of every rule — "CDRH3" has a
    digit in it — and silently relabelled every rule to its full raw string.
    """

    def test_identity_rules_collapse_to_one(self):
        names = {report._rule_name(f"CDRH3 identity 0.{v} >= 0.7 (2 muts; needs >= 4)")
                 for v in (90, 80, 75)}
        self.assertEqual(names, {"CDRH3 identity"})

    def test_cdrh3_survives_its_own_digit(self):
        self.assertEqual(report._rule_name("CDRH3 identity 0.9 >= 0.7"), "CDRH3 identity")

    def test_message_starting_with_a_number(self):
        # Real gate message; truncating at the first numeric token would yield "".
        self.assertEqual(
            report._rule_name("3 CDRH3 mutations from reference, needs >= 2"),
            "CDRH3 mutations from reference",
        )

    def test_non_numeric_rules_pass_through(self):
        for msg in ("empty sequence", "CDRH3 not locatable from sequence anchors"):
            self.assertEqual(report._rule_name(msg), msg)

    def test_funnel_counts_rejections_once_per_rule(self):
        result = a_run(n_pass=3, n_fail=4)
        f = report._funnel(result.records)
        self.assertEqual(f["rejected"], 4)
        self.assertEqual(f["failed_rules"], {"CDRH3 identity": 4})


class TestShortlist(unittest.TestCase):
    """The submission is a ranked list of up to 20, not the four lab slots.

    Placing on the day buys 16/12/8 further slots and each judge may nominate a
    favourite, so a list that stops at four discards every slot we might win.
    """

    def test_caps_at_twenty(self):
        result = a_run(n_pass=40)
        sl = report.build_shortlist(result.records, result.selected)
        self.assertEqual(len(sl), report.SUBMISSION_CAP)

    def test_selected_come_first_in_portfolio_order(self):
        result = a_run()
        sl = report.build_shortlist(result.records, result.selected)
        self.assertEqual([r.design_id for r in sl[:4]],
                         [r.design_id for r in result.selected])
        self.assertTrue(all(r.selected for r in sl[:4]))

    def test_rejected_designs_never_reach_the_submission(self):
        result = a_run(n_pass=10, n_fail=8)
        sl = report.build_shortlist(result.records, result.selected)
        self.assertTrue(all(r.gates.passed for r in sl))
        self.assertEqual(len(sl), 10)

    def test_remainder_is_ordered_by_joint_score(self):
        result = a_run()
        tail = report.build_shortlist(result.records, result.selected)[4:]
        scores = [r.joint_score for r in tail]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unscored_designs_are_not_submitted(self):
        """An unscored axis is missing evidence, not a zero."""
        result = a_run(n_pass=5)
        result.records[-1].joint_score = None
        sl = report.build_shortlist(result.records, result.selected)
        self.assertNotIn(result.records[-1].design_id, [r.design_id for r in sl])


class TestTierVerdict(unittest.TestCase):
    """S beats all three axes, A two, B one — counted against 0.500, not 0."""

    def test_tiers(self):
        for axes, want in (
            ({"binding": 0.9, "epitope": 0.9, "stability": 0.9}, "S"),
            ({"binding": 0.9, "epitope": 0.9, "stability": 0.4}, "A"),
            ({"binding": 0.9, "epitope": 0.1, "stability": 0.4}, "B"),
            ({"binding": 0.4, "epitope": 0.1, "stability": 0.4}, "—"),
        ):
            rec = make("d", 0.1)
            rec.axes = axes
            self.assertEqual(report._verdict(rec), want, axes)

    def test_exactly_the_baseline_does_not_count_as_beating_it(self):
        rec = make("d", 0.1)
        rec.axes = {a: report.BASELINE for a in AXES}
        self.assertEqual(report._verdict(rec), "—")


class TestHonesty(unittest.TestCase):
    """Predictions are never presented as measurements. This is the 40%."""

    def setUp(self):
        self.result = a_run()
        self.cfg = {"target": "HER2 P04626", "reference": "trastuzumab", "budget": 4,
                    "seed": 0, "run_id": "t", "git_sha": "deadbeef" * 5}
        self.md = report.render_markdown(self.result.records, self.result.selected,
                                         self.cfg, self.result.warnings)
        self.hl = report.render_html(self.result.records, self.result.selected,
                                     self.cfg, self.result.warnings)

    def test_says_every_number_is_a_prediction(self):
        for text in (self.md, self.hl):
            self.assertIn("prediction", text.lower())

    def test_every_axis_is_labelled_predicted(self):
        self.assertEqual(self.hl.count('class="chip pred"'), 4 * len(AXES))
        self.assertNotIn('class="chip meas"', self.hl)

    def test_states_the_baseline_meaning(self):
        for text in (self.md, self.hl):
            self.assertIn("0.500", text)

    def test_carries_the_null_result(self):
        """The enrichment null goes above the picks, not in an appendix."""
        for text in (self.md, self.hl):
            self.assertIn("0.508", text)
            self.assertIn("0.879", text)
            body = text.lower()
            self.assertLess(body.index("0.508"), body.index("dossier"))

    def test_carries_the_replicate_spread(self):
        for text in (self.md, self.hl):
            self.assertIn("6.2", text)

    def test_warnings_are_surfaced(self):
        for text in (self.md, self.hl):
            self.assertIn("not designs", text)

    def test_rejections_are_shown_not_hidden(self):
        self.assertIn("CDRH3 identity", self.md)

    def test_joint_score_is_always_decomposed(self):
        """A single number hides 'excellent on two axes, hopeless on the third'."""
        for axis in AXES:
            self.assertIn(report.AXIS_META[axis][0], self.md)
            self.assertIn(report.AXIS_META[axis][0], self.hl)


class TestHtmlIsSelfContained(unittest.TestCase):
    """It has to open from a file:// URL with no network. Tonight it will."""

    def setUp(self):
        result = a_run()
        self.hl = report.render_html(result.records, result.selected,
                                     {"budget": 4, "run_id": "t"}, [])

    def test_no_external_references(self):
        self.assertEqual(re.findall(r'(?:src|href)="(?!#)([^"]+)"', self.hl), [])

    def test_no_script(self):
        self.assertNotIn("<script", self.hl.lower())

    def test_well_formed(self):
        stack, errors = [], []

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag not in VOID:
                    stack.append(tag)

            def handle_endtag(self, tag):
                if not stack:
                    errors.append(f"stray </{tag}>")
                elif stack[-1] == tag:
                    stack.pop()
                else:
                    errors.append(f"</{tag}> while {stack[-1]} open")

        p = P(convert_charrefs=True)
        p.feed(self.hl)
        self.assertEqual(errors, [])
        self.assertEqual(stack, [])

    def test_escapes_hostile_content(self):
        """A generator name is data. It must not be able to inject markup."""
        result = a_run(n_pass=5)
        result.selected[0].generator = '<script>alert(1)</script>'
        hl = report.render_html(result.records, result.selected,
                                {"budget": 4, "run_id": "t"}, [])
        self.assertNotIn("<script>alert", hl)
        self.assertIn("&lt;script&gt;", hl)


class TestRunDirectory(unittest.TestCase):
    """Runs never overwrite each other, and each carries its provenance."""

    def test_writes_into_a_run_subdirectory(self):
        result = a_run()
        with tempfile.TemporaryDirectory() as td:
            paths = write_outputs(result, Path(td), config={"budget": 4}, run_id="r1")
            self.assertEqual(paths["all"].parent.name, "r1")
            for key in ("config", "all", "selected", "report_md", "report_html"):
                self.assertTrue(paths[key].exists(), key)

    def test_two_runs_do_not_collide(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = write_outputs(a_run(), Path(td), config={"budget": 4}, run_id="r1")
            p2 = write_outputs(a_run(), Path(td), config={"budget": 4}, run_id="r2")
            self.assertNotEqual(p1["all"], p2["all"])
            self.assertTrue(p1["all"].exists() and p2["all"].exists())

    def test_config_records_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_outputs(a_run(), Path(td),
                                  config={"budget": 4, "seed": 7}, run_id="r1")
            cfg = json.loads(paths["config"].read_text())
            for key in ("git_sha", "schema_version", "run_id", "seed", "warnings", "stages"):
                self.assertIn(key, cfg)
            self.assertEqual(cfg["seed"], 7)

    def test_run_id_is_stable_for_identical_inputs(self):
        cfg = {"target": "P04626", "reference": "trastuzumab", "budget": 4,
               "candidates": 24, "seed": 0}
        a, b = make_run_id(dict(cfg)), make_run_id(dict(cfg))
        self.assertEqual(a.split("-")[-1], b.split("-")[-1])

    def test_run_id_changes_with_the_seed(self):
        base = {"target": "P04626", "budget": 4, "candidates": 24, "seed": 0}
        other = dict(base, seed=1)
        self.assertNotEqual(make_run_id(base).split("-")[-1],
                            make_run_id(other).split("-")[-1])

    def test_a_broken_renderer_does_not_lose_the_records(self):
        """The JSONL is the evidence; the report is only a view of it."""
        result = a_run()
        original = report.render_markdown

        def boom(*_a, **_k):
            raise RuntimeError("renderer exploded")

        report.render_markdown = boom
        try:
            with tempfile.TemporaryDirectory() as td:
                paths = write_outputs(result, Path(td), config={"budget": 4}, run_id="r1")
                self.assertTrue(paths["all"].exists())
                self.assertNotIn("report_md", paths)
                self.assertTrue(any("report rendering failed" in w
                                    for w in result.warnings))
        finally:
            report.render_markdown = original


class TestRerender(unittest.TestCase):
    """`fourwells report RUNDIR` rebuilds the pitch without re-running a model."""

    def test_round_trip_from_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            paths = write_outputs(a_run(), Path(td), config={"budget": 4, "seed": 0},
                                  run_id="r1", report=False)
            rundir = paths["all"].parent
            self.assertEqual(report.main([str(rundir)]), 0)
            md = (rundir / "report.md").read_text()
            self.assertIn("The submission — ranked", md)
            self.assertIn("d000", md)

    def test_missing_rundir_is_an_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(report.main([td]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
