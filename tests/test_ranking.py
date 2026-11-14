"""Tests for the ranking engine — Layers 1 to 3. Stdlib unittest, no network.

    python3 -m unittest discover -s tests -v

These are not decoration. Three of them are regression tests for bugs that
would have put an unsubmittable or an untestable design in our four wells, and
each says which bug in its docstring. The rest pin down the properties the
pitch actually claims: that 0.5 means "ties trastuzumab", that the joint score
is a product, and that four slots go to four distinct hypotheses.
"""

from __future__ import annotations

import unittest

from fourwells import features
from fourwells.align import align, identity
from fourwells.calibrate import FOLKLORE_CUTOFF, ConfidencePolicy
from fourwells.schema import AXES, DesignRecord
from fourwells.stages import gates, portfolio, score
from fourwells.targets import Target, resolve_reference_ab

REF = resolve_reference_ab("trastuzumab")
TRAS_VH = REF.vh
TRAS_CDRH3 = REF.cdrh3  # WGGDGFYAMD, 10 aa — the convention both datasets use
TARGET = Target(identifier="P04626", kind="uniprot", epitope_residues=["557-561", "570-573"])


def make(design_id: str, cdrh3: str, track: str = "optimisation", **kw) -> DesignRecord:
    """A design record carrying `cdrh3` grafted into the trastuzumab heavy chain."""
    seq = kw.pop("sequence", None) or TRAS_VH.replace(TRAS_CDRH3, cdrh3)
    rec = DesignRecord(
        design_id=design_id,
        sequence=seq,
        track=track,
        format=kw.pop("format", "scfv"),
        parent=kw.pop("parent", "trastuzumab"),
        cdrh3=cdrh3,
        **kw,
    )
    return rec


class TestAlignment(unittest.TestCase):
    def test_identity_handles_indels(self):
        """REGRESSION. Identity used to be computed only for equal-length loops
        and returned None otherwise, and a None skipped the <70% ceiling
        entirely. RFD4 changes loop length freely, so this was the common case,
        not the edge case."""
        a, b = "WGGDGFYAMD", "WGGDGFYAMD"
        self.assertEqual(identity(a, b), 1.0)

        # One insertion: 11 of 12 residues still match trastuzumab.
        inserted = "WGGDGFYAMDK"
        self.assertIsNotNone(identity(inserted, b))
        self.assertGreater(identity(inserted, b), 0.70)

        # One deletion.
        deleted = "WGGDGFYAM"
        self.assertGreater(identity(deleted, b), 0.70)

    def test_identity_denominator_is_the_longer_sequence(self):
        """Gaps count against identity: a loop that keeps every trastuzumab
        residue and inserts four more is 11/15, not 11/11. Under a ceiling that
        rejects designs for being too SIMILAR, rounding identity down is the
        dangerous direction, so we round it up."""
        got = identity("WGGDGFYAMDKKKK", "WGGDGFYAMD")
        self.assertAlmostEqual(got, 10 / 14, places=6)

    def test_ref_position_map_tracks_deletions(self):
        aln = align("WGGDFYAMD", "WGGDGFYAMD")  # G deleted at position 4
        mapping = aln.ref_position_map()
        self.assertEqual(len(mapping), len("WGGDGFYAMD"))
        self.assertIn("-", mapping.values())


class TestLoopConvention(unittest.TestCase):
    """REGRESSION. The reference CDRH3 was corrected from an 11-mer to the
    10-mer both challenge datasets actually use, moving the trailing Y into the
    framework. Our extractor was still cutting Kabat-style, so the parent
    scored 10/11 identity against ITSELF and every identity gate was shifted by
    a position. The convention is now read off the reference, not assumed."""

    def test_extractor_agrees_with_the_reference(self):
        offset = features.detect_fr4_offset(TRAS_VH, TRAS_CDRH3)
        got = features.extract_cdrh3(TRAS_VH, offset)
        self.assertEqual(got, TRAS_CDRH3)

    def test_parent_scores_full_identity_against_itself(self):
        offset = features.detect_fr4_offset(TRAS_VH, TRAS_CDRH3)
        got = features.extract_cdrh3(TRAS_VH, offset)
        self.assertEqual(identity(got, TRAS_CDRH3), 1.0)

    def test_offset_is_detected_not_hardcoded(self):
        """Both readings are recognised, so a future correction to the loop
        boundary does not need a code change."""
        self.assertEqual(features.detect_fr4_offset(TRAS_VH, "WGGDGFYAMD"), 1)
        self.assertEqual(features.detect_fr4_offset(TRAS_VH, "WGGDGFYAMDY"), 0)

    def test_dataset_rows_extract_to_their_stated_loop(self):
        """The real contract: every row of the provided files must extract to
        the loop that row declares."""
        import csv

        offset = features.detect_fr4_offset(TRAS_VH, TRAS_CDRH3)
        with open("proof/tidy/spr_measured.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))[:50]
        self.assertTrue(rows, "spr_measured.csv missing")
        for row in rows:
            got = features.extract_cdrh3(row["vh_sequence"], offset)
            self.assertEqual(got, row["cdrh3"], f"row {row['cdrh3']}")


class TestGates(unittest.TestCase):
    def test_indel_design_is_still_gated(self):
        """REGRESSION, and the one that mattered. A near-copy of trastuzumab
        with a single inserted residue must be REJECTED for being too similar.
        Before the alignment fix it passed, because identity came back None and
        the rule was never evaluated."""
        rec = make("indel-near-copy", "WGGDGFYAMDK")
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertFalse(rec.gates.passed)
        self.assertTrue(
            any("identity" in f for f in rec.gates.failed_rules),
            f"expected an identity rejection, got {rec.gates.failed_rules}",
        )

    def test_conservative_mutant_is_rejected_as_too_similar(self):
        """The inversion worth remembering: the <70% rule is a FLOOR on how
        much we must change. A two-point mutant is not conservative-and-safe,
        it is unsubmittable."""
        rec = make("two-point", "WGGDGFYAEE")
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertFalse(rec.gates.passed)

    def test_four_of_eleven_changed_passes(self):
        rec = make("four-changed", "WEGDKFYMMH")
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertLess(rec.cdrh3_identity_to_tras, 0.70)
        self.assertTrue(rec.gates.passed, rec.gates.failed_rules)

    def test_cysteine_parity_is_per_chain(self):
        """REGRESSION. Two chains each carrying one free cysteine sum to an
        even count and read as paired if you check the joined construct in one
        go. The lab sees two chains."""
        # TRAS_VH carries 2 cysteines, so one extra makes the heavy chain odd,
        # and a light chain with a single cysteine is odd too — 4 in total,
        # which a construct-level parity check reads as perfectly paired.
        heavy = "C" + TRAS_VH.replace(TRAS_CDRH3, "WEGDKFYMMH")
        light = "DIQMTQSPSSLSASVGDRVTITC"
        joined = heavy + "GGGGSGGGGSGGGGS" + light
        self.assertEqual(heavy.count("C") % 2, 1, "heavy chain should be odd")
        self.assertEqual(light.count("C") % 2, 1, "light chain should be odd")
        self.assertEqual(joined.count("C") % 2, 0, "fixture should look paired overall")
        rec = make("split-cys", "WEGDKFYMMH", sequence=joined)
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertTrue(any("cysteine" in f for f in rec.gates.failed_rules), rec.gates.failed_rules)

    def test_unlocatable_cdrh3_is_rejected_not_waved_through(self):
        rec = DesignRecord(
            design_id="no-anchors",
            sequence="MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ",
            track="optimisation",
            format="vhh",
        )
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertFalse(rec.gates.passed)
        self.assertTrue(any("CDRH3" in f for f in rec.gates.failed_rules))

    def test_length_ceiling(self):
        rec = make("too-long", "WEGDKFYMMH", sequence="A" * 251)
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertTrue(any("length" in f for f in rec.gates.failed_rules))

    def test_abguard_absence_is_recorded_not_assumed(self):
        """A design the authority never saw must not read as fully passed."""
        rec = make("unseen-by-abguard", "WEGDKFYMMH")
        gates.check(rec, REF, provided=[], use_abguard=True)
        self.assertEqual(rec.gates.checks["abguard"]["status"], "NOT RUN")

    def test_novelty_is_decided_from_the_committed_universe(self):
        """With no provided set, the rule still runs off the committed 525k."""
        rec = make("no-provided", "WEGDKFYMMH")
        gates.check(rec, REF, provided=[], use_abguard=False)
        novelty = rec.gates.checks.get("novelty") or {}
        self.assertIn(novelty.get("verdict"), ("pass", "fail"))

    def test_novelty_fails_closed_when_nothing_can_decide_it(self):
        """No provided set and no universe must reject, never silently pass.

        This used to write a note and append nothing, so a rule that had never
        run read as a pass on every design.
        """
        saved = gates._UNIVERSE
        gates._UNIVERSE = set()
        try:
            rec = make("undecidable", "WEGDKFYMMH")
            gates.check(rec, REF, provided=[], use_abguard=False)
            self.assertFalse(rec.gates.passed)
            self.assertTrue(
                any("novelty" in f for f in rec.gates.failed_rules),
                rec.gates.failed_rules,
            )
        finally:
            gates._UNIVERSE = saved

    def test_parent_loop_is_rejected_as_unnovel(self):
        """Sanity anchor: trastuzumab's own loop is in the provided data."""
        verdict = gates.novelty_from_universe(REF.cdrh3)
        self.assertEqual(verdict.get("verdict"), "fail")


class TestExpressionScreen(unittest.TestCase):
    def test_developability_reports_the_tools_it_did_not_call(self):
        dev = features.developability(TRAS_VH)
        self.assertIn("aggrescan3d", dev.tools_not_called)
        self.assertGreater(dev.pi, 0)

    def test_hydrophobic_patch_detection(self):
        self.assertTrue(features.hydrophobic_patches("AAIIVVLLFF"))
        self.assertFalse(features.hydrophobic_patches("DEDEKRKRDE"))


class TestAxes(unittest.TestCase):
    def setUp(self):
        self.rf = score.ReferenceFeatures.build(REF)
        self.policy = ConfidencePolicy(cutoff=None, calibrated=False, meta={})

    def test_baseline_scores_exactly_half_on_every_axis(self):
        """The property the whole report rests on: the reference travels the
        identical path and lands on 0.500, so '0.5 ties trastuzumab' is true by
        construction rather than by assertion."""
        base = DesignRecord(
            design_id="trastuzumab",
            sequence=TRAS_VH,
            track="optimisation",
            format="scfv",
            parent="trastuzumab",
            cdrh3=TRAS_CDRH3,
        )
        score.run([base], TARGET, REF)
        for axis in AXES:
            self.assertAlmostEqual(base.axes[axis], 0.5, places=6, msg=axis)

    def test_de_novo_without_structure_is_capped_not_guessed(self):
        """A de novo binder with no evidence it hits domain IV cannot be
        S-tier at any affinity, so the axis is capped rather than defaulted to
        a coin flip."""
        rec = make("denovo-blind", "QRTDWYFDVL", track="de_novo")
        score.run([rec], TARGET, REF)
        self.assertLessEqual(rec.axes["epitope"], 0.15)
        self.assertEqual(rec.axis_evidence["epitope"]["basis"], "capped")

    def test_de_novo_with_domain_iv_contacts_scores_on_evidence(self):
        rec = make("denovo-evidenced", "QRTDWYFDVL", track="de_novo")
        rec.axis_evidence["epitope_contacts"] = list(range(557, 562)) + list(range(570, 574))
        score.run([rec], TARGET, REF)
        self.assertGreater(rec.axes["epitope"], 0.4)
        self.assertEqual(rec.axis_evidence["epitope"]["basis"], "structural")

    def test_optimisation_epitope_is_near_free(self):
        """The strategic read, as a test: a trastuzumab variant binds where
        trastuzumab binds, so the epitope axis should not be what kills it."""
        rec = make("opt-variant", "WEGDKFYMMH")
        score.run([rec], TARGET, REF)
        self.assertGreater(rec.axes["epitope"], 0.3)

    def test_every_axis_carries_a_human_reason(self):
        rec = make("reasons", "WEGDKFYMMH")
        score.run([rec], TARGET, REF)
        for axis in AXES:
            self.assertTrue(rec.axis_evidence[axis].get("reason"), axis)

    def test_high_confidence_cannot_raise_a_score_while_uncalibrated(self):
        """The 21 measured non-binders at ipTM >= 0.7 are why. High confidence
        is not evidence of binding; low confidence is still weak evidence
        against it, so the adjustment is clamped at zero from above."""
        adj, note = self.policy.adjustment(0.95)
        self.assertEqual(adj, 0.0)
        self.assertIn("not allowed to raise", note)

        adj_low, _ = self.policy.adjustment(0.30)
        self.assertLess(adj_low, 0.0)

    def test_calibrated_policy_lets_confidence_help(self):
        calibrated = ConfidencePolicy(
            cutoff=0.82, calibrated=True, meta={}, basis="measured"
        )
        adj, _ = calibrated.adjustment(0.95)
        self.assertGreater(adj, 0.0)

    def test_a_decoy_calibration_does_not_unlock_confidence(self):
        """A cutoff fitted against shuffled pairs is weaker evidence than one
        fitted against molecules measured not to bind. Separating decoys is an
        easier problem than ours, so it may still lower a score and may not
        raise one."""
        decoys = ConfidencePolicy(
            cutoff=0.69, calibrated=True, meta={}, basis="computational"
        )
        self.assertFalse(decoys.trusted)
        adj, note = decoys.adjustment(0.95)
        self.assertEqual(adj, 0.0)
        self.assertIn("computational", note)
        # ...but a low value still counts against the design.
        self.assertLess(decoys.adjustment(0.30)[0], 0.0)

    def test_confidence_is_a_feature_not_the_score(self):
        """Two designs identical but for structure confidence must not differ
        wildly: confidence carries a small weight by design."""
        lo = make("conf-lo", "WEGDKFYMMH")
        hi = make("conf-hi", "WEGDKFYMMH")
        lo.axis_evidence["confidence"] = {"iptm": 0.20}
        hi.axis_evidence["confidence"] = {"iptm": 0.99}
        score.run([lo, hi], TARGET, REF)
        self.assertLess(abs(hi.axes["binding"] - lo.axes["binding"]), 0.15)


class TestPortfolio(unittest.TestCase):
    def test_joint_score_is_a_product(self):
        rec = make("prod", "WEGDKFYMMH")
        rec.axes = {"binding": 0.5, "epitope": 0.4, "stability": 0.2}
        self.assertAlmostEqual(portfolio.joint_score(rec), 0.04, places=6)

    def test_joint_score_is_none_while_any_axis_is_unscored(self):
        rec = make("partial", "WEGDKFYMMH")
        rec.axes = {"binding": 0.9, "epitope": 0.9, "stability": None}
        self.assertIsNone(portfolio.joint_score(rec))

    def test_product_punishes_the_two_good_axes_one_dead_axis_design(self):
        """A weighted sum ranks (0.95, 0.95, 0.05) near the top. It cannot be
        S-tier. The product is what encodes that."""
        lopsided = make("lopsided", "WEGDKFYMMH")
        lopsided.axes = {"binding": 0.95, "epitope": 0.95, "stability": 0.05}
        balanced = make("balanced", "WEGDKFYMMH")
        balanced.axes = {"binding": 0.55, "epitope": 0.55, "stability": 0.55}
        self.assertGreater(portfolio.joint_score(balanced), portfolio.joint_score(lopsided))

    def test_slots_are_allocated_across_clusters_not_down_the_list(self):
        """The 40%. Given four near-identical variants of one loop that score
        highest, plus three genuinely different loops that score lower, the
        shortlist must still test more than one hypothesis — four variants of
        one parent share a failure mode and die together."""
        recs = []
        # One tight family of four, all scoring well.
        for i, cdrh3 in enumerate(["WEGDKFYMMH", "WEGDKFYMMY", "WEGDKFYMMF", "WEGDKFYMMW"]):
            r = make(f"family-{i}", cdrh3)
            r.axes = {"binding": 0.60, "epitope": 0.60, "stability": 0.60}
            r.gates.passed = True
            recs.append(r)
        # Three distinct loops, each scoring lower.
        for i, cdrh3 in enumerate(["QRTDWYFDVL", "HHPLNNSTWG", "ADGKIRTEPQ"]):
            r = make(f"distinct-{i}", cdrh3)
            r.axes = {"binding": 0.50, "epitope": 0.50, "stability": 0.50}
            r.gates.passed = True
            recs.append(r)

        portfolio.run(recs, budget=4)
        picked = [r for r in recs if r.selected]
        self.assertEqual(len(picked), 4)
        clusters = {r.cluster for r in picked}
        self.assertGreaterEqual(
            len(clusters), 3, f"only {len(clusters)} hypotheses in 4 wells: {clusters}"
        )
        n_family = sum(1 for r in picked if r.design_id.startswith("family-"))
        self.assertLessEqual(n_family, 2, "the tight family swallowed the shortlist")

    def test_borderline_designs_lose_ties_to_unambiguous_ones(self):
        """At the same joint score, send the design that is unambiguously
        submittable. Costs nothing when both are available; costs a well if the
        organisers read the novelty rule the strict way."""
        safe = make("safe", "WEGDKFYMMH")
        bord = make("borderline", "WEGDKFYMMY")
        for r in (safe, bord):
            r.axes = {a: 0.5 for a in AXES}
            r.gates.passed = True
        safe.gates.checks = {"novelty": {"verdict": "pass", "borderline": False}}
        bord.gates.checks = {"novelty": {"verdict": "pass", "borderline": True}}

        portfolio.run([safe, bord], budget=1)
        self.assertTrue(safe.selected, "the unambiguous design should take the slot")
        self.assertFalse(bord.selected)

    def test_a_borderline_pick_says_so_in_its_dossier(self):
        bord = make("borderline", "WEGDKFYMMY")
        bord.axes = {a: 0.5 for a in AXES}
        bord.gates.passed = True
        bord.gates.checks = {"novelty": {"verdict": "pass", "borderline": True}}
        portfolio.run([bord], budget=4)
        self.assertTrue(any("borderline" in line.lower() for line in bord.rationale))

    def test_every_selected_design_has_a_kill_criterion_and_reasons(self):
        recs = []
        for i, cdrh3 in enumerate(["WEGDKFYMMH", "QRTDWYFDVL", "HHPLNNSTWG", "ADGKIRTEPQ"]):
            r = make(f"d{i}", cdrh3)
            r.axes = {"binding": 0.4, "epitope": 0.5, "stability": 0.6}
            r.gates.passed = True
            recs.append(r)
        portfolio.run(recs, budget=4)
        for r in [x for x in recs if x.selected]:
            self.assertTrue(r.rationale, r.design_id)
            self.assertTrue(r.kill_criterion, r.design_id)
            self.assertNotIn("UNSET", r.kill_criterion)

    def test_baseline_is_never_selected(self):
        base = DesignRecord(
            design_id="trastuzumab", sequence=TRAS_VH, track="optimisation",
            format="scfv", parent="trastuzumab", cdrh3=TRAS_CDRH3,
        )
        base.axes = {a: 0.5 for a in AXES}
        base.gates.passed = True
        other = make("real", "WEGDKFYMMH")
        other.axes = {"binding": 0.3, "epitope": 0.3, "stability": 0.3}
        other.gates.passed = True
        portfolio.run([base, other], budget=4)
        self.assertFalse(base.selected)
        self.assertTrue(other.selected)

    def test_gate_failures_are_never_selected(self):
        bad = make("gated-out", "WGGDGFYAMD")
        bad.axes = {a: 0.99 for a in AXES}
        bad.gates.passed = False
        bad.gates.failed_rules = ["CDRH3 identity 1.00 >= 0.7"]
        portfolio.run([bad], budget=4)
        self.assertFalse(bad.selected)

    def test_audit_blocks_submission_without_an_abguard_pass(self):
        r = make("no-abguard", "WEGDKFYMMH")
        r.axes = {a: 0.5 for a in AXES}
        r.gates.passed = True
        r.gates.checks = {"abguard": {"status": "NOT RUN"}}
        portfolio.run([r], budget=4)
        report = portfolio.audit([r], budget=4)
        self.assertFalse(report["submission_ready"])
        self.assertTrue(any("abguard" in b for b in report["blockers"]))

    def test_audit_flags_single_track_concentration(self):
        recs = []
        for i, cdrh3 in enumerate(["WEGDKFYMMH", "QRTDWYFDVL", "HHPLNNSTWG", "ADGKIRTEPQ"]):
            r = make(f"t{i}", cdrh3)
            r.axes = {a: 0.5 for a in AXES}
            r.gates.passed = True
            r.gates.checks = {"abguard": {"status": "pass"}}
            recs.append(r)
        portfolio.run(recs, budget=4)
        report = portfolio.audit(recs, budget=4)
        self.assertTrue(any("optimisation track" in b for b in report["blockers"]))


class TestIngest(unittest.TestCase):
    """The seam between generation and the ranker.

    DesignRecord.from_dict filters to known fields, so loading the generation
    export directly drops its novelty, refold and design-metrics blocks on the
    floor. These pin down that they land where the stages look for them.
    """

    def _row(self, dist, capped=True, in_provided=False, muts=4):
        return {
            "design_id": "d", "vh": TRAS_VH.replace(TRAS_CDRH3, "WEGDKFYMMH"),
            "vl": REF.vl or "", "cdrh3": "WEGDKFYMMH",
            "track": "optimisation", "format": "scfv", "parent": "trastuzumab",
            "novelty": {
                "mutations_from_parent": muts,
                "min_substitutions_from_any_provided": dist,
                "min_substitutions_is_capped_at_2": capped,
                "in_provided_data": in_provided,
            },
            "refold": {"model": "boltz2", "iptm": 0.9, "binder_plddt": 80.0,
                       "backbone_rmsd": 1.5},
            "design_metrics": {"hotspot_obedience": 0.8},
        }

    def test_refold_and_metrics_survive_the_crossing(self):
        from fourwells.ingest import to_record

        rec = to_record(self._row(4))
        self.assertEqual(rec.axis_evidence["confidence"]["iptm"], 0.9)
        self.assertEqual(rec.axis_evidence["confidence"]["binder_plddt"], 80.0)
        self.assertIn("design_metrics", rec.axis_evidence)
        self.assertEqual(rec.axis_evidence["hotspot_obedience"], 0.8)

    def test_a_clean_distance_passes(self):
        from fourwells.ingest import novelty_verdict

        passes, _ = novelty_verdict(self._row(4)["novelty"])
        self.assertTrue(passes)

    def test_distance_two_is_rejected_under_the_strict_reading(self):
        """Switched 12:43 by team decision, and it is a judgment call not a
        measurement. The real filter rejected nothing at distance 2 over 201
        designs, so the lenient reading has evidence behind it. The wording --
        "more than 2 point mutations from any provided antibody" -- plainly
        reads as 3, and nobody could get a mentor to settle it.

        The asymmetry decided it. Being wrong about the lenient reading does
        not cost the ~2% of joint score Rizve priced; it costs the whole
        submission, after the pitch. 3 satisfies both readings.
        """
        from fourwells.ingest import novelty_verdict, MIN_DISTANCE_FROM_PROVIDED

        passes, reason = novelty_verdict(self._row(2, capped=False)["novelty"])
        self.assertEqual(MIN_DISTANCE_FROM_PROVIDED, 3, "the agreed reading")
        self.assertFalse(passes, reason)

    def test_the_threshold_itself_passes_but_is_flagged_borderline(self):
        """Whatever the threshold is, a design sitting exactly on it is the one
        we are least sure of, so it passes and the portfolio step breaks ties
        against it rather than refusing it outright.
        """
        from fourwells.ingest import (
            novelty_verdict, to_record, MIN_DISTANCE_FROM_PROVIDED as D,
        )

        passes, reason = novelty_verdict(self._row(D, capped=True)["novelty"])
        self.assertTrue(passes)
        self.assertIn("Borderline", reason)

        rec = to_record(self._row(D, capped=True))
        self.assertTrue(rec.gates.checks["novelty"]["borderline"])
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertTrue(rec.gates.passed, rec.gates.failed_rules)

    def test_comfortably_past_the_threshold_is_not_borderline(self):
        from fourwells.ingest import to_record, MIN_DISTANCE_FROM_PROVIDED as D

        rec = to_record(self._row(D + 1, capped=False))
        self.assertFalse(rec.gates.checks["novelty"]["borderline"])

    def test_a_known_binder_fails_novelty(self):
        from fourwells.ingest import to_record

        rec = to_record(self._row(0, in_provided=True))
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertFalse(rec.gates.passed)
        self.assertTrue(any("already in the provided data" in f for f in rec.gates.failed_rules))

    def test_one_substitution_fails(self):
        from fourwells.ingest import novelty_verdict

        from fourwells.ingest import MIN_DISTANCE_FROM_PROVIDED as D

        passes, reason = novelty_verdict(self._row(1)["novelty"])
        self.assertFalse(passes)
        self.assertIn(f">= {D}", reason)

    def test_missing_universe_is_undecidable_not_a_pass(self):
        from fourwells.ingest import novelty_verdict

        passes, reason = novelty_verdict({"mutations_from_parent": 4})
        self.assertIsNone(passes)
        self.assertIn("not computed", reason)

    def test_refold_divergence_becomes_a_feature(self):
        from fourwells.ingest import refold_confidence

        clean = refold_confidence({"backbone_rmsd": 1.2})
        broken = refold_confidence({"backbone_rmsd": 9.0})
        self.assertEqual(clean["refold_disagreement"], 0.0)
        self.assertGreater(broken["refold_disagreement"], 0.8)


class TestTransferGuard(unittest.TestCase):
    """The guard that kept a bad model out of the ranker.

    The fitted FACS model reached a held-out AUC of 0.873 against its own label
    and still ranked measured binders the wrong way round. Without this check a
    good AUC would have been enough to ship it.
    """

    def _fake(self, direction):
        """A model whose score is +/- the identity to the parent, so we know the
        true sign of its correlation with K_D."""
        from fourwells.fit_binding import _index

        idx = _index(len(TRAS_CDRH3))
        w = [0.0] * (len(TRAS_CDRH3) * 20)
        for i, aa in enumerate(TRAS_CDRH3):
            w[idx[(i, aa)]] = direction
        return w, 0.0, idx

    def test_a_correctly_signed_model_passes(self):
        from fourwells.fit_binding import transfer_check

        # Closer to parent -> higher score, and closer to parent really does
        # mean lower K_D in the measured data, so this must pass.
        w, b, idx = self._fake(+1.0)
        spr = [("WGGDGFYAMD", 0.15), ("WGGQGFYAMD", 0.3), ("WGGSGPYLFD", 1.0),
               ("QRTDWYFDVL", 90.0), ("ADGKIRTEPQ", 160.0), ("HHPLNNSTWG", 200.0)]
        got = transfer_check(spr, w, b, idx, TRAS_CDRH3)
        self.assertLess(got["spearman_vs_logkd_submittable"], 0)
        self.assertTrue(got["passes"], got["verdict"])

    def test_an_anticorrelated_model_is_rejected(self):
        from fourwells.fit_binding import transfer_check

        w, b, idx = self._fake(-1.0)
        spr = [("WGGDGFYAMD", 0.15), ("WGGQGFYAMD", 0.3), ("WGGSGPYLFD", 1.0),
               ("QRTDWYFDVL", 90.0), ("ADGKIRTEPQ", 160.0), ("HHPLNNSTWG", 200.0)]
        got = transfer_check(spr, w, b, idx, TRAS_CDRH3)
        self.assertFalse(got["passes"])
        self.assertIn("DOES NOT TRANSFER", got["verdict"])

    def test_the_real_fit_is_still_rejected(self):
        """If someone retunes the fit and this starts passing, that is good news
        — but it must be a deliberate change, not a silent one."""
        from fourwells.fit_binding import fit, read_variants, read_spr, transfer_check

        train = read_variants("proof/tidy/fixtures/facs_train_sample.csv")
        w, b, idx, _ = fit(train, len(TRAS_CDRH3), iterations=60)
        spr = read_spr("proof/tidy/spr_measured.csv")
        got = transfer_check(spr, w, b, idx, TRAS_CDRH3)
        self.assertFalse(
            got["passes"],
            "the FACS fit now transfers to K_D — update docs/binding-axis-validation.md "
            f"and the pitch, do not just delete this test. rho={got['spearman_vs_logkd_submittable']}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ConstructLengthGate(unittest.TestCase):
    """The 250 limit applies to the molecule we order, not to one chain."""

    def _rec(self, construct):
        rec = make("construct-len", "WEGDKFYMMH")
        rec.axis_evidence["construct"] = construct
        return rec

    def test_construct_length_is_what_gets_measured(self):
        rec = self._rec({"length": 242, "vh_plus_vl_length": 227})
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertEqual(rec.gates.checks["length_measured"], 242)
        self.assertEqual(rec.gates.checks["length_basis"], "construct")

    def test_an_over_long_construct_is_rejected(self):
        """A 120 aa VH would pass on its own; the real construct must not."""
        rec = self._rec({"length": 262, "vh_plus_vl_length": 247})
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertFalse(rec.gates.passed)
        self.assertTrue(
            any("262" in f for f in rec.gates.failed_rules), rec.gates.failed_rules
        )

    def test_falls_back_to_the_sequence_when_no_construct(self):
        rec = make("no-construct", "WEGDKFYMMH")
        gates.check(rec, REF, provided=[], use_abguard=False)
        self.assertEqual(rec.gates.checks["length_basis"], "sequence")


class ScfvLinkerFeasibility(unittest.TestCase):
    """A construct can be too long AND have no legal way to be shortened.

    This is the seam the denovo batch fell through. Its VH+VL is 242-244, which
    passes the lenient reading of the 250 aa limit, so `length_ok` is True --
    but the scFv we would actually order is 257-259 and the only linkers short
    enough to fit are too short to fold as an scFv at all. The record has to say
    that, or it reports `max_linker_for_limit: 6` and invites the fix that
    cannot work.
    """

    def test_our_optimisation_batches_have_room_for_a_real_linker(self):
        from fourwells.stages.generate import _scfv_construct, MIN_SCFV_LINKER

        c = _scfv_construct("A" * 120, "B" * 107)  # optA, optB, multicdr
        self.assertEqual(c["vh_plus_vl_length"], 227)
        self.assertEqual(c["length"], 242)
        self.assertTrue(c["construct_within_limit"])
        self.assertTrue(c["linker_feasible"])
        self.assertGreaterEqual(c["max_linker_for_limit"], MIN_SCFV_LINKER)

    def test_denovo_shape_has_no_legal_linker_at_all(self):
        from fourwells.stages.generate import _scfv_construct

        c = _scfv_construct("A" * 131, "B" * 113)  # the longest denovo design
        self.assertEqual(c["length"], 259)
        self.assertTrue(c["length_ok"], "passes the lenient VH+VL reading")
        self.assertFalse(c["construct_within_limit"], "fails on the real construct")
        self.assertEqual(c["max_linker_for_limit"], 6)
        self.assertFalse(
            c["linker_feasible"],
            "6 aa fits the limit but cannot fold as an scFv -- it would be a diabody",
        )

    def test_a_g4s2_linker_does_not_rescue_the_denovo_batch(self):
        """The proposed fix, measured: (G4S)2 buys 5 residues and needs 7-9."""
        from fourwells.stages.generate import MIN_SCFV_LINKER

        for vh_plus_vl in (242, 243, 244):
            self.assertGreater(vh_plus_vl + 10, 250, "(G4S)2 still over the limit")
            self.assertLess(
                250 - vh_plus_vl, MIN_SCFV_LINKER, "and no legal linker exists"
            )


class ScorableEpitopeRegions(unittest.TestCase):
    """The epitope axis must not score against residues the input cannot hold.

    HER2 reaches the folding models as chains C 489-580 and D 591-607, because
    input validation rejects a numbering gap inside one chain. 581-590 is that
    gap. It is a real annotated contact region (8PWH, lower confidence) and no
    refold we run can touch it, so counting it caps overlap at 20/30 for every
    design and for trastuzumab alike -- the parent's own refold scores 0.467
    overlap with it counted and 0.700 without.
    """

    def test_the_unreachable_loop_is_excluded_from_scoring(self):
        from fourwells.targets import resolve_target

        t = resolve_target("P04626")
        self.assertIn("557-561", t.epitope_residues)
        self.assertIn("570-573", t.epitope_residues)
        self.assertIn("593-603", t.epitope_residues)
        self.assertNotIn(
            "581-590",
            t.epitope_residues,
            "absent from the folded input, so it cannot be contacted or scored",
        )

    def test_the_scorable_epitope_is_twenty_residues(self):
        from fourwells.targets import resolve_target

        t = resolve_target("P04626")
        n = 0
        for span in t.epitope_residues:
            lo, hi = span.split("-")
            n += int(hi) - int(lo) + 1
        self.assertEqual(n, 20, "557-561 (5) + 570-573 (4) + 593-603 (11)")

    def test_the_region_is_still_annotated_just_not_scored(self):
        """Dropping it from scoring must not drop it from the record."""
        import json
        from pathlib import Path

        blob = json.loads(
            (Path(__file__).resolve().parent.parent
             / "data/reference/trastuzumab.json").read_text()
        )
        regions = blob["her2"]["contact_regions"]
        gap = [c for c in regions if c["residues"] == "581-590"]
        self.assertEqual(len(gap), 1, "still carried as annotation")
        self.assertFalse(gap[0]["scorable"])
        self.assertIn("_not_scorable_why", gap[0], "and it says why")
