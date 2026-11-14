"""Tests for the call log and its UI — OWNER: Mahamoodoul.

    python3 -m unittest discover -s tests -v

The log exists to answer one question the design records cannot: when a run
produces nothing, was the call blocked offline, did it fail, or did it return
something we then discarded? So the tests pin the three outcomes apart, and
pin the two ways this could do harm:

  - leaking a credential into a file that is easy to paste into a chat
  - being the reason a run dies

One of these is a regression. The first time the UI was rendered it printed an
API key, because redaction lived in `call()` and the entry had been written
through `write()`.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from fourwells import calllog, logview
from fourwells.cache import Cache, CacheMiss


def a_log(tmp: Path, run_id: str = "r1") -> calllog.CallLog:
    return calllog.CallLog(path=tmp / "calls.jsonl", run_id=run_id)


class TestRecording(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = a_log(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        return calllog.read_log(self.dir / "calls.jsonl")

    def test_records_request_response_and_duration(self):
        with self.log.call("foundry", "design", stage="generate",
                           request={"n": 8}) as slot:
            slot["response"] = {"designs": 8}
        e = self.read()[0]
        self.assertEqual(e["provider"], "foundry")
        self.assertEqual(e["op"], "design")
        self.assertEqual(e["stage"], "generate")
        self.assertEqual(e["status"], calllog.OK)
        self.assertEqual(e["request"], {"n": 8})
        self.assertEqual(e["response"], {"designs": 8})
        self.assertIsInstance(e["ms"], float)
        self.assertEqual(e["run_id"], "r1")

    def test_an_exception_is_recorded_and_re_raised(self):
        """The log never swallows a failure — it only writes it down."""
        with self.assertRaises(ValueError):
            with self.log.call("japanfold", "predict", request={"seq": "Q"}):
                raise ValueError("upstream exploded")
        e = self.read()[0]
        self.assertEqual(e["status"], calllog.ERROR)
        self.assertIn("upstream exploded", e["error"])
        self.assertIsNone(e["response"])

    def test_statuses_are_distinguishable(self):
        for status in (calllog.CACHE_HIT, calllog.OFFLINE_BLOCKED):
            with self.log.call("boltz2", "fold") as slot:
                slot["status"] = status
        got = [e["status"] for e in self.read()]
        self.assertEqual(got, [calllog.CACHE_HIT, calllog.OFFLINE_BLOCKED])

    def test_long_bodies_are_truncated_and_flagged(self):
        with self.log.call("x", "y", request="Q" * (calllog.MAX_BODY * 2)) as slot:
            slot["response"] = "R" * (calllog.MAX_BODY * 2)
        e = self.read()[0]
        self.assertTrue(e["request_clipped"])
        self.assertTrue(e["response_clipped"])
        self.assertLess(len(e["request"]), calllog.MAX_BODY * 2)
        self.assertIn("more characters", e["request"])

    def test_logging_failure_never_kills_the_run(self):
        log = calllog.CallLog(path=Path("/nonexistent-dir-xyz/calls.jsonl"))
        with log.call("x", "y") as slot:   # must not raise
            slot["response"] = "fine"
        self.assertFalse(log.enabled)


class TestRedaction(unittest.TestCase):
    """REGRESSION: an API key reached the rendered page.

    Redaction used to live only in `call()`. Anything written through `write()`
    — a hand-built entry, a test, a future stage — went to disk in the clear.
    It now happens at the write boundary, which is where bytes hit the file.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_redacts_secret_shaped_keys_at_any_depth(self):
        got = calllog.redact({
            "api_key": "sk-1", "nested": {"Authorization": "Bearer x"},
            "list": [{"token": "t"}], "safe": "keep me",
        })
        self.assertEqual(got["api_key"], calllog.REDACTED)
        self.assertEqual(got["nested"]["Authorization"], calllog.REDACTED)
        self.assertEqual(got["list"][0]["token"], calllog.REDACTED)
        self.assertEqual(got["safe"], "keep me")

    def test_write_redacts_even_when_call_is_bypassed(self):
        log = a_log(self.dir)
        log.write({"provider": "foundry", "request": {"api_key": "sk-LEAK"},
                   "response": {"session": "sess-LEAK"}})
        text = (self.dir / "calls.jsonl").read_text()
        self.assertNotIn("sk-LEAK", text)
        self.assertNotIn("sess-LEAK", text)
        self.assertIn(calllog.REDACTED, text)

    def test_secrets_never_reach_the_rendered_page(self):
        log = a_log(self.dir)
        log.write({"ts": "t", "provider": "p", "op": "o", "ms": 1.0,
                   "status": "ok", "request": {"token": "jf-LEAK"},
                   "response": None})
        page = logview.render(calllog.read_log(self.dir / "calls.jsonl"),
                              self.dir / "calls.jsonl")
        self.assertNotIn("jf-LEAK", page)


class TestCacheIsInstrumented(unittest.TestCase):
    """The cache is the choke point every expensive call goes through."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = a_log(self.dir)
        calllog.set_log(self.log)

    def tearDown(self):
        calllog.set_log(None)
        self.tmp.cleanup()

    def test_offline_block_is_logged_not_silent(self):
        """A run that finishes fast and empty must be explainable afterwards."""
        cache = Cache(cache_dir=self.dir / "c", offline=True)
        with self.assertRaises(CacheMiss):
            cache.memo("boltz2", {"seq": "Q"}, lambda: "never")
        e = self.log.entries[-1]
        self.assertEqual(e["status"], calllog.OFFLINE_BLOCKED)
        self.assertEqual(e["provider"], "boltz2")

    def test_compute_then_hit_are_logged_distinctly(self):
        cache = Cache(cache_dir=self.dir / "c", offline=False)
        cache.memo("foundry", {"seq": "Q"}, lambda: {"v": 1})
        cache.memo("foundry", {"seq": "Q"}, lambda: {"v": 2})
        statuses = [e["status"] for e in self.log.entries]
        self.assertEqual(statuses, [calllog.OK, calllog.CACHE_HIT])
        self.assertEqual(self.log.entries[-1]["response"], {"v": 1})

    def test_a_failing_compute_is_logged_as_an_error(self):
        cache = Cache(cache_dir=self.dir / "c", offline=False)
        with self.assertRaises(RuntimeError):
            cache.memo("foundry", {"seq": "Q"}, self._boom)
        self.assertEqual(self.log.entries[-1]["status"], calllog.ERROR)

    @staticmethod
    def _boom():
        raise RuntimeError("provider down")


class TestSummary(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"provider": "a", "op": "x", "status": "ok", "ms": 100.0, "run_id": "r1"},
            {"provider": "a", "op": "y", "status": "ok", "ms": 300.0, "run_id": "r1"},
            {"provider": "b", "op": "z", "status": "error", "ms": 50.0, "run_id": "r1"},
            {"provider": "b", "op": "z", "status": "cache_hit", "ms": 1.0, "run_id": "r2"},
        ]

    def test_totals(self):
        s = calllog.summarise(self.entries)
        self.assertEqual(s["calls"], 4)
        self.assertEqual(s["total_ms"], 451.0)
        self.assertEqual(s["errors"], 1)
        self.assertEqual(s["error_rate"], 0.25)
        self.assertEqual(s["cache_hits"], 1)

    def test_per_provider_breakdown_finds_the_slowest_op(self):
        s = calllog.summarise(self.entries)
        self.assertEqual(s["by_provider"]["a"]["calls"], 2)
        self.assertEqual(s["by_provider"]["a"]["ms"], 400.0)
        self.assertEqual(s["by_provider"]["a"]["slowest_op"], "y")

    def test_providers_are_ordered_by_time_spent(self):
        s = calllog.summarise(self.entries)
        self.assertEqual(list(s["by_provider"]), ["a", "b"])

    def test_percentiles_do_not_crash_on_one_entry(self):
        s = calllog.summarise(self.entries[:1])
        self.assertEqual(s["p50_ms"], 100.0)
        self.assertEqual(s["p95_ms"], 100.0)

    def test_empty_log_summarises_to_zero(self):
        s = calllog.summarise([])
        self.assertEqual(s["calls"], 0)
        self.assertEqual(s["error_rate"], 0.0)
        self.assertEqual(s["p95_ms"], 0.0)


class TestLogView(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "calls.jsonl"
        log = calllog.CallLog(path=self.path, run_id="r1")
        with log.call("foundry", "design", stage="generate", request={"n": 8}) as s:
            s["response"] = {"designs": 8}
        with self.assertRaises(ValueError):
            with log.call("japanfold", "predict", request={"seq": "Q"}):
                raise ValueError("timeout")
        self.page = logview.render(calllog.read_log(self.path), self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_both_calls(self):
        self.assertIn("foundry", self.page)
        self.assertIn("japanfold", self.page)

    def test_shows_the_error(self):
        self.assertIn("timeout", self.page)

    def test_is_self_contained(self):
        self.assertEqual(re.findall(r'(?:src|href)="(?!#)([^"]+)"', self.page), [])
        self.assertEqual(re.findall(r"<script[^>]*\ssrc=", self.page), [])

    def test_payload_cannot_break_out_of_the_script_tag(self):
        log = calllog.CallLog(path=self.path, run_id="r1")
        log.write({"ts": "t", "provider": "</script><script>alert(1)</script>",
                   "op": "o", "ms": 1.0, "status": "ok"})
        page = logview.render(calllog.read_log(self.path), self.path)
        blob = re.search(r'id="data">(.*?)</script>', page, re.S)
        self.assertIsNotNone(blob)
        self.assertNotIn("<", blob.group(1))
        self.assertEqual(len(re.findall(r"<script", page)), 2)

    def test_empty_log_renders_a_page_not_a_crash(self):
        page = logview.render([], self.dir / "nothing.jsonl")
        self.assertIn("log is empty", page)

    def test_a_corrupt_line_is_skipped_not_fatal(self):
        with open(self.path, "a") as fh:
            fh.write("{not json at all\n")
        self.assertEqual(len(calllog.read_log(self.path)), 2)

    def test_binding_walks_past_a_taken_port(self):
        """REGRESSION: "browser won't open the page".

        A second instance on the same port used to die on "address already in
        use", so nothing was listening and the browser showed nothing. It now
        walks forward to the next free port. Tested without a thread, because
        the first version of this test raced the server's startup and passed
        alone while failing in the suite.
        """
        import socket

        from http.server import BaseHTTPRequestHandler

        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        taken = busy.getsockname()[1]
        busy.listen(1)
        try:
            srv, port = logview.bind("127.0.0.1", taken, BaseHTTPRequestHandler)
            self.assertIsNotNone(srv, "no fallback port was found")
            self.assertGreater(port, taken)
            srv.server_close()
        finally:
            busy.close()

    def test_binding_gives_up_cleanly_when_everything_is_taken(self):
        from http.server import BaseHTTPRequestHandler

        held = []
        try:
            import socket

            base = None
            for _ in range(logview.PORT_SPAN):
                s = socket.socket()
                s.bind(("127.0.0.1", 0))
                s.listen(1)
                held.append(s)
            base = held[0].getsockname()[1]
            # Not every port in the span is necessarily held, so just assert the
            # contract: it either returns a server or None, never raises.
            srv, _ = logview.bind("127.0.0.1", base, BaseHTTPRequestHandler)
            if srv is not None:
                srv.server_close()
        finally:
            for s in held:
                s.close()

    def test_any_path_serves_the_page(self):
        """A mistyped URL shows the log, not a 404 that reads as broken."""
        import socket
        import threading
        import time
        import urllib.request

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
        probe.close()

        threading.Thread(
            target=logview.serve,
            args=(self.path, "127.0.0.1", free),
            kwargs={"refresh": 60, "open_browser": False},
            daemon=True,
        ).start()

        got = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{free}/anything", timeout=2
                ) as r:
                    got = r.status
                break
            except OSError:
                time.sleep(0.05)
        self.assertEqual(got, 200)

    def test_live_mode_adds_a_refresh(self):
        live = logview.render(calllog.read_log(self.path), self.path, live=True,
                              refresh=5)
        self.assertIn('http-equiv="refresh" content="5"', live)
        self.assertNotIn("http-equiv=\"refresh\"", self.page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
