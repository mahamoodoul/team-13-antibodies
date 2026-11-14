"""The web app — a server, routes, and a JSON API over the runs and the call log.

    python3 -m fourwells.web            # http://127.0.0.1:4173
    make local                          # demo, then this

An ordinary small web application, deliberately with no build step: the server
is the standard library, the front end is three real files in `static/`, and
the data comes from a JSON API rather than being baked into the page. Start it,
leave it open, and it keeps up with runs as they land — no regenerating a file
and reloading it by hand, which is what made the earlier static pages annoying.

Why no framework: the whole project's demo property is that it runs on a
judge's laptop with no network and no install. A React build would trade that
for a `node_modules` directory and a toolchain. The API below is plain JSON, so
a framework can be put in front of it later without touching the server.

Routes
    /                     the app shell (overview, runs, a run, the log)
    /static/*             css and js
    /api/overview         totals across runs and calls
    /api/runs             every run, newest first
    /api/runs/<id>        one run: config, stages, designs, shortlist
    /api/calls            the call log, with ?since= for incremental polling
    /api/report/<id>      the generated report.html for a run, if present
"""

from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..calllog import read_log, summarise
from ..report import SUBMISSION_CAP, build_shortlist, _verdict
from ..schema import AXES, read_jsonl
from ..experiments import Store, start, export_bundle, resource_status

STATIC = Path(__file__).resolve().parent / "static"
PORT_SPAN = 20
# A run id is a timestamp plus a hash; anything else is not ours and must not
# reach the filesystem.
RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


# ---------------------------------------------------------------- data access

def _runs_dir(root: Path) -> Path:
    return root / "results"


def list_runs(root: Path) -> list[dict]:
    d = _runs_dir(root)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir(), reverse=True):
        if not p.is_dir() or not (p / "designs.jsonl").exists():
            continue
        cfg = {}
        cp = p / "config.json"
        if cp.exists():
            try:
                cfg = json.loads(cp.read_text())
            except ValueError:
                cfg = {}
        out.append({
            "run_id": p.name,
            "target": cfg.get("target"),
            "reference": cfg.get("reference"),
            "seed": cfg.get("seed"),
            "budget": cfg.get("budget"),
            "git_sha": cfg.get("git_sha"),
            "warnings": cfg.get("warnings", []),
            "stages": cfg.get("stages", []),
            "seconds": round(sum(s.get("seconds", 0) for s in cfg.get("stages", [])), 3),
            "has_report": (p / "report.html").exists(),
        })
    return out


def _design_row(rec, rank: int, picked: set[str]) -> dict:
    return {
        "rank": rank,
        "design_id": rec.design_id,
        "lab": rec.design_id in picked,
        "track": rec.track,
        "format": rec.format,
        "parent": rec.parent,
        "generator": rec.generator,
        "cluster": rec.cluster,
        "tier": _verdict(rec),
        "joint": rec.joint_score,
        "axes": {a: rec.axes.get(a) for a in AXES},
        "identity": rec.cdrh3_identity_to_tras,
        "cdrh3": rec.cdrh3,
        "mutations": rec.cdrh3_mutations_from_tras,
        "gates_passed": rec.gates.passed,
        "failed_rules": rec.gates.failed_rules,
        "sequence": rec.sequence,
        "length": len(rec.sequence),
        "rationale": list(rec.rationale),
        "kill_criterion": rec.kill_criterion,
        "stub": bool(rec.is_stub),
    }


def load_run(root: Path, run_id: str) -> dict | None:
    if not RUN_ID.match(run_id):
        return None
    p = _runs_dir(root) / run_id
    # Resolve and confirm it is really inside results/: a run id must never be
    # able to walk out of the directory it names.
    try:
        p = p.resolve()
        p.relative_to(_runs_dir(root).resolve())
    except (ValueError, OSError):
        return None
    if not (p / "designs.jsonl").exists():
        return None

    cfg = {}
    if (p / "config.json").exists():
        try:
            cfg = json.loads((p / "config.json").read_text())
        except ValueError:
            pass
    records = read_jsonl(p / "designs.jsonl")
    selected = (read_jsonl(p / "selected.jsonl")
                if (p / "selected.jsonl").exists()
                else sorted([r for r in records if r.selected],
                            key=lambda r: r.rank or 999))
    shortlist = build_shortlist(records, selected)
    picked = {r.design_id for r in selected}

    failed: dict[str, int] = {}
    from ..report import _rule_name
    for r in records:
        for rule in r.gates.failed_rules or []:
            k = _rule_name(rule)
            failed[k] = failed.get(k, 0) + 1

    return {
        "run_id": run_id,
        "config": cfg,
        "has_report": (p / "report.html").exists(),
        "counts": {
            "generated": len(records),
            "passed": sum(1 for r in records if r.gates.passed),
            "submitted": len(shortlist),
            "lab_slots": len(selected),
            "stub": sum(1 for r in records if r.is_stub),
            "cap": SUBMISSION_CAP,
        },
        "failed_rules": dict(sorted(failed.items(), key=lambda kv: -kv[1])),
        "axes": list(AXES),
        "shortlist": [_design_row(r, i, picked) for i, r in enumerate(shortlist, 1)],
        "rejected": [
            _design_row(r, 0, picked) for r in records if not r.gates.passed
        ],
    }


def overview(root: Path) -> dict:
    runs = list_runs(root)
    calls = read_log(root / "logs" / "calls.jsonl")
    s = summarise(calls)
    latest = load_run(root, runs[0]["run_id"]) if runs else None
    return {
        "runs": len(runs),
        "latest": {
            "run_id": latest["run_id"],
            "counts": latest["counts"],
            "warnings": latest["config"].get("warnings", []),
            "target": latest["config"].get("target"),
            "seconds": round(
                sum(x.get("seconds", 0) for x in latest["config"].get("stages", [])), 3
            ),
        } if latest else None,
        "calls": s,
    }


# ---------------------------------------------------------------- server

class App(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    root = Path(".")

    # -- helpers --------------------------------------------------------
    def _send(self, body: bytes, code: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, code: int = 200):
        self._send(json.dumps(payload, default=str).encode(), code,
                   "application/json; charset=utf-8")

    def _static(self, name: str):
        p = (STATIC / name).resolve()
        try:
            p.relative_to(STATIC.resolve())
        except ValueError:
            self._json({"error": "not found"}, 404)
            return
        if not p.is_file():
            self._json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(p.read_bytes(), 200, ctype)

    # -- routes ---------------------------------------------------------
    def do_POST(self):  # noqa: N802
        # Only a local same-origin request may start work. Model commands and
        # paths are CLI-only; browser jobs are safe, explicit offline demos.
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            self._json({"error": "same-origin requests only"}, 403)
            return
        if self.path != "/api/experiments":
            self._json({"error": "no such endpoint"}, 404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16000:
                raise ValueError("Request must contain 1–16000 bytes")
            spec = json.loads(self.rfile.read(size))
            if not isinstance(spec, dict) or spec.get("mode", "demo") != "demo" or any(
                    k in spec for k in ("input", "profile")):
                raise ValueError("Browser can start offline demos; use the CLI for imports and model execution")
            self._json(start(self.root, spec), 202)
        except (ValueError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        path, q = u.path.rstrip("/") or "/", parse_qs(u.query)

        if path == "/favicon.ico":
            self._send(b"", 204, "image/x-icon")
            return
        if path.startswith("/static/"):
            self._static(path[len("/static/"):])
            return

        if path == "/api/experiments":
            self._json({"iterations": Store(self.root).list(), "resources": resource_status(self.root)})
            return
        if path.startswith("/api/experiments/"):
            parts = path[len("/api/experiments/"):].split("/")
            try:
                store = Store(self.root)
                job = store.get(parts[0])
                if not job:
                    raise ValueError("No such iteration")
                if len(parts) == 1:
                    self._json(job)
                elif parts[1:] == ["diversity"]:
                    ids = q.get("candidate", [])
                    if not 2 <= len(ids) <= 4 or len(set(ids)) != len(ids):
                        raise ValueError("Choose 2–4 distinct candidate IDs")
                    candidates = job.get("result", {}).get("candidates", [])
                    picked = [c for c in candidates if c["design_id"] in ids]
                    if len(picked) != len(ids):
                        raise ValueError("No such candidate")
                    from ..evidence import sequence_diversity
                    self._json({"pairs": sequence_diversity(picked)})
                elif parts[1:] == ["export"]:
                    body = export_bundle(self.root, parts[0])
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="{parts[0]}.zip"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                elif len(parts) == 3 and parts[1] == "structure":
                    # Only structures retained and checksummed by the pipeline
                    # are visible; never serve the project root or tool logs.
                    names = set()
                    for c in job.get("result", {}).get("candidates", []):
                        names.update(s["path"] for s in c.get("structures", []))
                        if c.get("reference_structure"):
                            names.add(c["reference_structure"])
                    name = "structures/" + parts[2]
                    if name not in names:
                        raise ValueError("No saved structure")
                    from ..structures import atoms
                    self._json({"atoms": atoms(store.directory(parts[0]) / name)})
                else:
                    raise ValueError("No such resource")
            except (ValueError, OSError) as exc:
                self._json({"error": str(exc)}, 404)
            return

        if path == "/api/overview":
            self._json(overview(self.root))
            return
        if path == "/api/runs":
            self._json({"runs": list_runs(self.root)})
            return
        if path.startswith("/api/runs/"):
            run = load_run(self.root, path[len("/api/runs/"):])
            self._json(run or {"error": "no such run"}, 200 if run else 404)
            return
        if path == "/api/calls":
            calls = read_log(self.root / "logs" / "calls.jsonl")
            try:
                since = int(q.get("since", ["0"])[0])
            except ValueError:
                since = 0
            # Incremental: the client holds a count and asks for what is new,
            # so polling stays cheap as the log grows through the day.
            tail = calls[since:]
            self._json({
                "total": len(calls),
                "since": since,
                "entries": tail,
                "summary": summarise(calls),
            })
            return
        if path.startswith("/api/report/"):
            rid = path[len("/api/report/"):]
            if RUN_ID.match(rid):
                f = _runs_dir(self.root) / rid / "report.html"
                if f.exists():
                    self._send(f.read_bytes())
                    return
            self._json({"error": "no report for that run"}, 404)
            return

        if path.startswith("/api/"):
            self._json({"error": "no such endpoint"}, 404)
            return

        # Everything else is the app shell; the front end routes it.
        self._send((STATIC / "index.html").read_bytes())

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def log_message(self, *a):
        pass


def bind(host: str, port: int, handler):
    """First free port at or after `port`. Returns (server, port)."""
    for candidate in range(port, port + PORT_SPAN):
        try:
            return ThreadingHTTPServer((host, candidate), handler), candidate
        except OSError:
            continue
    return None, port


def serve(root: Path, host: str = "127.0.0.1", port: int = 4173,
          open_browser: bool = True) -> int:
    import webbrowser

    handler = type("BoundApp", (App,), {"root": root})
    wanted = port
    srv, port = bind(host, port, handler)
    if srv is None:
        print(f"could not bind a port in {wanted}..{wanted + PORT_SPAN - 1}.")
        print("Pass --port to choose another.")
        return 1
    if port != wanted:
        print(f"\n  ! port {wanted} is in use — using {port} instead.")
        print(f"  ! to find what holds it: lsof -nP -iTCP:{wanted} -sTCP:LISTEN")

    url = f"http://{host}:{port}/experiments"
    print(f"\n  AntibodyLab AI  {url}")
    print(f"  serving    {root}")
    print("  Ctrl-C to stop\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            print("  (no browser here — open the URL above)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="fourwells.web", description=__doc__)
    ap.add_argument("--port", type=int, default=4173)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--root", default=None, help="project directory to read")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[2]
    return serve(root, host=a.host, port=a.port, open_browser=not a.no_open)
