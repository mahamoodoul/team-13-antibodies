"""The abguard wrapper, against an interface we have never verified.

abguard is not on the VM, not in pip, not in the organisers' bucket. The
invocation in `gates.abguard_check` — subcommand `check`, flag `--json`,
payload on stdin, JSON back with `passed`/`track`/`numbering_confidence` — is
an assumption. Nobody has run the tool.

That makes one failure mode much likelier than any other on submission night:
the binary turns up, we call it with the wrong arguments, it exits non-zero
with a usage message, and the wrapper records that as the design being
rejected. Every molecule in the pool fails at once, for a reason that has
nothing to do with any molecule.

These tests pin the distinction the wrapper has to make:

    the tool refused this design    -> fail   (a verdict)
    we called the tool wrong        -> ERROR  (not a verdict)

A fake `abguard` on PATH stands in for the real one, so the behaviour is
exercised rather than asserted about.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from fourwells.stages import gates
from fourwells.schema import DesignRecord
from fourwells.targets import resolve_reference_ab

REF = resolve_reference_ab()


def make(design_id: str, cdrh3: str) -> DesignRecord:
    return DesignRecord(
        design_id=design_id,
        sequence=REF.vh.replace(REF.cdrh3, cdrh3),
        track="optimisation",
        format="scfv",
        parent="trastuzumab",
        cdrh3=cdrh3,
    )


class FakeAbguard:
    """Puts an executable named `abguard` on PATH for the duration."""

    def __init__(self, script: str):
        self.script = script

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        p = Path(self.dir) / "abguard"
        p.write_text(self.script)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self._old = os.environ["PATH"]
        os.environ["PATH"] = f"{self.dir}{os.pathsep}{self._old}"
        return self

    def __exit__(self, *exc):
        os.environ["PATH"] = self._old


def run_one(script: str) -> DesignRecord:
    rec = make("d1", "WEGDKFYMMH")
    with FakeAbguard(script):
        gates.check(rec, REF, provided=[], use_abguard=True)
    return rec


USAGE_ERROR = """#!/bin/sh
echo "usage: abguard [-h] {validate,version} ..." >&2
echo "abguard: error: argument command: invalid choice: 'check'" >&2
exit 2
"""

REAL_REJECTION = """#!/bin/sh
cat > /dev/null
echo '{"passed": false, "failed_rules": ["unpaired cysteine at H22"], "track": "optimisation"}'
exit 0
"""

REAL_PASS = """#!/bin/sh
cat > /dev/null
echo '{"passed": true, "track": "optimisation", "numbering_confidence": 0.94}'
exit 0
"""

NON_JSON_PASS = """#!/bin/sh
cat > /dev/null
echo "OK"
exit 0
"""


class TestUsageErrorIsNotAVerdict(unittest.TestCase):
    def test_wrong_invocation_is_error_not_fail(self):
        """The regression that would fail the whole pool at 17:50."""
        rec = run_one(USAGE_ERROR)
        self.assertEqual(rec.gates.checks["abguard"]["status"], "ERROR")
        self.assertNotEqual(rec.gates.checks["abguard"]["status"], "fail")

    def test_wrong_invocation_does_not_claim_the_design_was_rejected(self):
        rec = run_one(USAGE_ERROR)
        joined = " ".join(rec.gates.failed_rules).lower()
        self.assertNotIn("rejected", joined)
        self.assertIn("not a verdict", joined)

    def test_wrong_invocation_still_blocks_the_design(self):
        """ERROR is not permission to proceed — the authority has not seen it."""
        rec = run_one(USAGE_ERROR)
        self.assertFalse(rec.gates.passed)

    def test_the_raw_output_is_kept_for_diagnosis(self):
        rec = run_one(USAGE_ERROR)
        self.assertIn("invalid choice", rec.gates.checks["abguard"]["raw"])
        self.assertEqual(rec.gates.checks["abguard"]["returncode"], 2)


class TestRealVerdictsStillWork(unittest.TestCase):
    def test_a_genuine_rejection_is_recorded_as_fail(self):
        rec = run_one(REAL_REJECTION)
        self.assertEqual(rec.gates.checks["abguard"]["status"], "fail")
        self.assertFalse(rec.gates.passed)
        self.assertTrue(
            any("unpaired cysteine" in r for r in rec.gates.failed_rules),
            rec.gates.failed_rules,
        )

    def test_a_genuine_pass_is_recorded_as_pass(self):
        rec = run_one(REAL_PASS)
        self.assertEqual(rec.gates.checks["abguard"]["status"], "pass")
        self.assertEqual(rec.gates.checks.get("numbering_confidence"), 0.94)

    def test_zero_exit_without_json_is_still_a_pass(self):
        """A build that does not speak JSON, but did not complain."""
        rec = run_one(NON_JSON_PASS)
        self.assertEqual(rec.gates.checks["abguard"]["status"], "pass")

    def test_low_numbering_confidence_fails(self):
        rec = run_one("""#!/bin/sh
cat > /dev/null
echo '{"passed": true, "track": "optimisation", "numbering_confidence": 0.05}'
exit 0
""")
        self.assertFalse(rec.gates.passed)
        self.assertTrue(any("numbering confidence" in r for r in rec.gates.failed_rules))


class TestAbsence(unittest.TestCase):
    def test_absence_is_recorded_not_assumed(self):
        rec = make("unseen", "WEGDKFYMMH")
        gates.check(rec, REF, provided=[], use_abguard=True)
        self.assertEqual(rec.gates.checks["abguard"]["status"], "NOT RUN")


if __name__ == "__main__":
    unittest.main()
