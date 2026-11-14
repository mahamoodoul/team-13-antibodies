"""Tests for the web app — OWNER: Mahamoodoul.

    python3 -m unittest discover -s tests -v

The app is a server with a JSON API, so these pin the API's shape (the front
end is written against it) and the two things a local server can get wrong:

  - serving a file outside the directories it is supposed to expose
  - 404-ing a deep link, so /runs/<id> only works if you click your way there

The front end itself is driven in headless Chrome at the bottom, skipped where
Chrome is absent, because a sort that silently does nothing looks exactly like
one that works — which is a bug this project has now shipped twice.
"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from fourwells.calllog import CallLog
from fourwells.runner import RunResult, write_outputs
from fourwells.schema import AXES, DesignRecord
from fourwells.web import app as webapp

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def make(design_id: str, joint: float, selected: bool = False, rank=None,
         passed: bool = True, failed=None) -> DesignRecord:
    rec = DesignRecord(design_id=design_id, sequence="QVQLVQSGAEVKKPGAS" * 2)
    rec.track = "optimisation"
    rec.format = "scfv"
    rec.cdrh3 = "WGSQGFYAYD"
    rec.cdrh3_identity_to_tras = 0.6
    rec.cluster = "c" + design_id[-1]
    rec.gates.passed = passed
    rec.gates.failed_rules = list(failed or [])
    per = joint ** (1 / 3)
    rec.axes = {a: per for a in AXES}
    rec.joint_score = joint
    rec.selected = selected
    rec.rank = rank
    rec.rationale = ["because the test said so"]
    rec.kill_criterion = "loses the epitope competition"
    return rec


def build_project(root: Path, n_pass: int = 8, budget: int = 3) -> str:
    records = [make(f"d{i:03d}", 0.5 - i * 0.02) for i in range(n_pass)]
    records += [make(f"x{i:03d}", 0.9, passed=False,
                     failed=[f"CDRH3 identity 0.{90 - i} >= 0.7"]) for i in range(3)]
    for rank, rec in enumerate(records[:budget], 1):
        rec.selected, rec.rank = True, rank
    result = RunResult(records=records)
    result.warnings.append("this is a test run, not designs")
    paths = write_outputs(result, root / "results",
                          config={"budget": budget, "seed": 0, "target": "HER2 P04626",
                                  "reference": "trastuzumab"},
                          run_id="20260101-000000-testtest")
    log = CallLog(path=root / "logs" / "calls.jsonl", run_id="20260101-000000-testtest")
    with log.call("foundry", "design", stage="generate", request={"n": 8}) as s:
        s["response"] = {"designs": 8}
    return paths["all"].parent.name


class ServerCase(unittest.TestCase):
    """One server for the class, on a port the OS says is free."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.run_id = build_project(cls.root)

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        cls.port = probe.getsockname()[1]
        probe.close()

        handler = type("T", (webapp.App,), {"root": cls.root})
        cls.srv, cls.port = webapp.bind("127.0.0.1", cls.port, handler)
        assert cls.srv is not None, "could not bind a port"
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(cls.base + "/api/runs", timeout=2).read()
                break
            except OSError:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.read()

    def json(self, path):
        code, body = self.get(path)
        return code, json.loads(body)

    def raw(self, path):
        """Send a path verbatim — clients normalise ../ before it reaches us."""
        s = socket.create_connection(("127.0.0.1", self.port), 5)
        s.sendall(f"GET {path} HTTP/1.0\r\nHost: x\r\n\r\n".encode())
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
        s.close()
        head, _, body = data.partition(b"\r\n\r\n")
        return head.split(b"\r\n")[0].decode(), body


class TestApi(ServerCase):
    def test_overview(self):
        code, d = self.json("/api/overview")
        self.assertEqual(code, 200)
        self.assertEqual(d["runs"], 1)
        self.assertEqual(d["latest"]["run_id"], self.run_id)
        self.assertEqual(d["calls"]["calls"], 1)

    def test_runs_list(self):
        _, d = self.json("/api/runs")
        self.assertEqual(len(d["runs"]), 1)
        r = d["runs"][0]
        self.assertEqual(r["target"], "HER2 P04626")
        self.assertIn("git_sha", r)

    def test_run_detail_shape(self):
        """The front end is written against this shape."""
        _, d = self.json(f"/api/runs/{self.run_id}")
        for key in ("run_id", "config", "counts", "failed_rules", "axes",
                    "shortlist", "rejected"):
            self.assertIn(key, d, key)
        self.assertEqual(d["axes"], list(AXES))
        self.assertEqual(d["counts"]["generated"], 11)
        self.assertEqual(d["counts"]["passed"], 8)
        self.assertEqual(d["counts"]["lab_slots"], 3)

    def test_rejections_are_grouped_by_rule_not_by_value(self):
        _, d = self.json(f"/api/runs/{self.run_id}")
        self.assertEqual(d["failed_rules"], {"CDRH3 identity": 3})

    def test_shortlist_puts_lab_slots_first(self):
        _, d = self.json(f"/api/runs/{self.run_id}")
        top = d["shortlist"][:3]
        self.assertTrue(all(r["lab"] for r in top))
        self.assertFalse(any(r["lab"] for r in d["shortlist"][3:]))

    def test_designs_carry_what_a_dossier_needs(self):
        _, d = self.json(f"/api/runs/{self.run_id}")
        r = d["shortlist"][0]
        for key in ("design_id", "tier", "joint", "axes", "sequence", "rationale",
                    "kill_criterion", "gates_passed", "cluster"):
            self.assertIn(key, r, key)

    def test_calls_endpoint_supports_incremental_polling(self):
        _, d = self.json("/api/calls?since=0")
        self.assertEqual(d["total"], 1)
        self.assertEqual(len(d["entries"]), 1)
        _, d2 = self.json("/api/calls?since=1")
        self.assertEqual(d2["total"], 1)
        self.assertEqual(d2["entries"], [])

    def test_bad_since_does_not_crash(self):
        code, d = self.json("/api/calls?since=banana")
        self.assertEqual(code, 200)
        self.assertEqual(d["since"], 0)

    def test_unknown_api_endpoint_is_404_json(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/nope")
        self.assertEqual(cm.exception.code, 404)

    def test_unknown_run_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/runs/nosuchrun")
        self.assertEqual(cm.exception.code, 404)


class TestRouting(ServerCase):
    def test_deep_link_serves_the_app_shell(self):
        """/runs/<id> typed straight into the bar must work, not 404."""
        for path in ("/", "/runs", f"/runs/{self.run_id}", "/logs", "/anything"):
            code, body = self.get(path)
            self.assertEqual(code, 200, path)
            self.assertIn(b'id="view"', body, path)

    def test_static_assets_are_served_with_types(self):
        for path, ctype in (("/static/app.css", "text/css"),
                            ("/static/app.js", "javascript")):
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertIn(ctype, r.headers["Content-Type"])

    def test_favicon_is_not_an_error(self):
        code, _ = self.get("/favicon.ico")
        self.assertEqual(code, 204)


class TestNoFileEscape(ServerCase):
    """A local server still must not hand out files outside what it exposes."""

    def test_static_cannot_escape_its_directory(self):
        for path in ("/static/../app.py", "/static/../../cache/x",
                     "/static/..%2fapp.py"):
            status, body = self.raw(path)
            self.assertIn("404", status, path)
            self.assertNotIn(b"def ", body, path)

    def test_run_id_cannot_escape_results(self):
        for path in ("/api/runs/../../../etc/passwd",
                     "/api/report/../../../etc/passwd"):
            status, body = self.raw(path)
            self.assertIn("404", status, path)
            self.assertNotIn(b"root:", body, path)

    def test_run_id_pattern_rejects_separators(self):
        self.assertIsNone(webapp.load_run(self.root, "../etc"))
        self.assertIsNone(webapp.load_run(self.root, "a/b"))


@unittest.skipUnless(CHROME.exists(), "headless Chrome not available")
class TestInBrowser(ServerCase):
    """The front end, driven for real.

    The probe page is served from the app's own origin — a file:// harness
    cannot reach into an http:// frame, and that is how the first attempt at
    this test silently measured nothing.
    """

    def _probe(self, script: str, path: str) -> dict:
        import re
        import subprocess

        static = Path(webapp.STATIC)
        shell = (static / "index.html").read_text()
        pre = (f'<script>history.replaceState({{}},"","{path}");</script>\n'
               f'<script src="/static/app.js"></script>')
        page = shell.replace('<script src="/static/app.js"></script>', pre + script)
        probe = static / "__test_probe.html"
        probe.write_text(page)
        try:
            out = subprocess.run(
                [str(CHROME), "--headless", "--disable-gpu", "--no-sandbox",
                 "--virtual-time-budget=9000", "--dump-dom",
                 f"{self.base}/static/__test_probe.html"],
                capture_output=True, text=True, timeout=120,
            )
            m = re.search(r"<title>R ([^<]*)</title>", out.stdout)
            return dict(kv.split("=", 1) for kv in m.group(1).split("|")) if m else {}
        finally:
            probe.unlink(missing_ok=True)

    def test_run_page_renders_and_filters(self):
        res = self._probe("""
<script>
setTimeout(function(){
 var out=[];
 function rows(){return document.querySelectorAll('#dtable tr[data-id]').length}
 out.push('rows='+rows());
 document.getElementById('dlab').click(); out.push('labonly='+rows());
 document.getElementById('dlab').click();
 var q=document.getElementById('dq'); q.value='d000'; q.dispatchEvent(new Event('input'));
 out.push('search='+rows());
 q.value='zzzz'; q.dispatchEvent(new Event('input'));
 out.push('nomatch='+rows());
 document.title='R '+out.join('|');
},2000);
</script>""", f"/runs/{self.run_id}")
        self.assertTrue(res, "the probe never ran")
        self.assertEqual(res.get("rows"), "8")
        self.assertEqual(res.get("labonly"), "3")
        self.assertEqual(res.get("search"), "1")
        self.assertEqual(res.get("nomatch"), "0")

    def test_sorting_an_axis_column_really_sorts(self):
        """REGRESSION: axis columns are nested, and a naive r[k] is a no-op."""
        res = self._probe("""
<script>
setTimeout(function(){
 var out=[];
 function vals(){return Array.prototype.map.call(
   document.querySelectorAll('#dtable tr[data-id]'),
   function(tr){return parseFloat(tr.children[5].textContent)})}
 var th=document.querySelector('#dtable th[data-k="axes.binding"]');
 th.click(); var desc=vals(); th.click(); var asc=vals();
 function mono(a,d){for(var i=1;i<a.length;i++){if(d>0?a[i]<a[i-1]:a[i]>a[i-1])return false}return true}
 out.push('desc='+mono(desc,-1));
 out.push('asc='+mono(asc,1));
 out.push('reversed='+(desc[0]!==asc[0]));
 document.title='R '+out.join('|');
},2000);
</script>""", f"/runs/{self.run_id}")
        self.assertEqual(res.get("desc"), "true")
        self.assertEqual(res.get("asc"), "true")
        self.assertEqual(res.get("reversed"), "true")

    def test_clicking_a_row_opens_a_dossier(self):
        res = self._probe("""
<script>
setTimeout(function(){
 document.querySelector('#dtable tr[data-id]').click();
 document.title='R dossier='+(document.querySelectorAll('#dtable pre').length>0);
},2000);
</script>""", f"/runs/{self.run_id}")
        self.assertEqual(res.get("dossier"), "true")

    def test_overview_renders_from_the_api(self):
        res = self._probe("""
<script>
setTimeout(function(){
 var t=document.getElementById('view').textContent;
 document.title='R cards='+document.querySelectorAll('.card').length
   +'|latest='+(t.indexOf('Latest run')>=0);
},2000);
</script>""", "/")
        self.assertEqual(res.get("latest"), "true")
        self.assertGreaterEqual(int(res.get("cards", "0")), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
