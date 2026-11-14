"""Call log — what we asked an external thing, what it said, and how long it took.

Every expensive call the pipeline makes lands here as one JSON line: the
request, the response, the duration, and whether it was served from cache,
blocked by offline mode, or failed. The log is append-only and lives outside
any single run directory, so it accumulates across a day's work and you can ask
"what did Foundry actually return at 14:20" after the fact.

Why this exists separately from the run's own output: `designs.jsonl` records
what we decided, not what we asked. When a run produces nothing, the question
is always "did the call fail, did it get blocked offline, or did it return
something we then threw away" — and that is unanswerable from the records.

Everything is stdlib and local. Nothing is sent anywhere.

Two deliberate limits, because a log that leaks or fills the disk is worse than
no log:

  - Bodies are truncated to MAX_BODY characters. The full payload is already
    reproducible from the cache key.
  - Values under keys that look like secrets are redacted before writing. The
    repo is public and these logs are easy to paste into a chat.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "calls.jsonl"
MAX_BODY = 4000  # characters kept per request/response body

# Anything whose key looks like one of these is redacted, at any depth.
_SECRET = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|authorization|auth|bearer|"
    r"credential|cookie|session)", re.I
)
# ASCII on purpose: json.dumps escapes non-ASCII, so a pretty «» marker would be
# written as \u00ab and would not match a plain grep for the word.
REDACTED = "[redacted]"

# Status values. Kept small and fixed so the UI can colour them without guessing.
OK = "ok"
ERROR = "error"
CACHE_HIT = "cache_hit"
OFFLINE_BLOCKED = "offline_blocked"


def redact(value: Any) -> Any:
    """Strip anything that looks like a credential, at any depth."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _SECRET.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _clip(value: Any) -> tuple[Any, bool]:
    """Serialise for the log, truncating long bodies. Returns (value, clipped)."""
    if value is None:
        return None, False
    try:
        text = value if isinstance(value, str) else json.dumps(redact(value), default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > MAX_BODY:
        return text[:MAX_BODY] + f"\n… [{len(text) - MAX_BODY} more characters]", True
    # Give the UI structured data where we have it, a string otherwise.
    if not isinstance(value, str):
        return redact(value), False
    return text, False


class CallLog:
    """Append-only JSONL. One instance per run; cheap to construct."""

    def __init__(self, path: Path | str = DEFAULT_LOG, run_id: str = "",
                 enabled: bool = True):
        self.path = Path(path)
        self.run_id = run_id
        self.enabled = enabled
        self.entries: list[dict] = []
        if self.enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                # An unwritable log directory disables logging; it does not stop
                # the run. Constructing the log used to raise here, which made
                # observability a way to lose the pipeline.
                self.enabled = False

    def write(self, entry: dict) -> None:
        """Append one entry. Redacts here, not only in `call()`.

        `call()` already redacts on the way in, so this is belt and braces —
        but it is the boundary where bytes hit the disk, and a caller that
        builds an entry by hand (a test, a future stage, an import of somebody
        else's log) must not be able to write a credential into the file. This
        caught a real leak the first time the UI was exercised.
        """
        entry = redact(entry)
        self.entries.append(entry)
        if not self.enabled:
            return
        try:
            with open(self.path, "a") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            # Logging must never be the reason a run dies.
            self.enabled = False

    @contextmanager
    def call(self, provider: str, op: str, *, stage: str = "",
             request: Any = None, **extra) -> Iterator[dict]:
        """Time one external call and record how it ended.

        Set `slot["response"]` inside the block; set `slot["status"]` to
        override the outcome (for a cache hit, say). An exception is recorded
        as an error and then re-raised — the log never swallows a failure.
        """
        slot: dict[str, Any] = {"response": None, "status": OK}
        t0 = time.time()
        started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))
        try:
            yield slot
        except BaseException as exc:
            req, req_clipped = _clip(request)
            self.write({
                "ts": started,
                "run_id": self.run_id,
                "stage": stage,
                "provider": provider,
                "op": op,
                "status": ERROR,
                "ms": round((time.time() - t0) * 1000, 1),
                "request": req,
                "request_clipped": req_clipped,
                "response": None,
                "error": f"{exc.__class__.__name__}: {exc}",
                **extra,
            })
            raise
        req, req_clipped = _clip(request)
        resp, resp_clipped = _clip(slot.get("response"))
        self.write({
            "ts": started,
            "run_id": self.run_id,
            "stage": stage,
            "provider": provider,
            "op": op,
            "status": slot.get("status", OK),
            "ms": round((time.time() - t0) * 1000, 1),
            "request": req,
            "request_clipped": req_clipped,
            "response": resp,
            "response_clipped": resp_clipped,
            "error": None,
            **extra,
        })

    # ---------------------------------------------------------------- summary

    def summary(self) -> dict:
        return summarise(self.entries)


def read_log(path: Path | str = DEFAULT_LOG, limit: int | None = None) -> list[dict]:
    """Read the log, newest last. A corrupt line is skipped, not fatal."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[-limit:] if limit else out


def _pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile. No numpy, and exact enough for a call log."""
    if not values:
        return 0.0
    s = sorted(values)
    i = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[i]


def summarise(entries: list[dict]) -> dict:
    """Totals, latency percentiles, and a per-provider breakdown."""
    ms = [e.get("ms", 0) or 0 for e in entries]
    by_status: dict[str, int] = {}
    by_provider: dict[str, dict] = {}
    by_run: dict[str, dict] = {}

    for e in entries:
        st = e.get("status", "?")
        by_status[st] = by_status.get(st, 0) + 1

        p = by_provider.setdefault(
            e.get("provider", "?"),
            {"calls": 0, "ms": 0.0, "errors": 0, "slowest": 0.0, "slowest_op": ""},
        )
        p["calls"] += 1
        p["ms"] += e.get("ms", 0) or 0
        if st == ERROR:
            p["errors"] += 1
        if (e.get("ms") or 0) > p["slowest"]:
            p["slowest"] = e.get("ms") or 0
            p["slowest_op"] = e.get("op", "")

        r = by_run.setdefault(
            e.get("run_id") or "(none)",
            {"calls": 0, "ms": 0.0, "errors": 0, "first": e.get("ts"), "last": e.get("ts")},
        )
        r["calls"] += 1
        r["ms"] += e.get("ms", 0) or 0
        if st == ERROR:
            r["errors"] += 1
        r["last"] = e.get("ts")

    for p in by_provider.values():
        p["ms"] = round(p["ms"], 1)
        p["avg_ms"] = round(p["ms"] / p["calls"], 1) if p["calls"] else 0.0
    for r in by_run.values():
        r["ms"] = round(r["ms"], 1)

    n = len(entries)
    errors = by_status.get(ERROR, 0)
    hits = by_status.get(CACHE_HIT, 0)
    return {
        "calls": n,
        "total_ms": round(sum(ms), 1),
        "errors": errors,
        "error_rate": round(errors / n, 4) if n else 0.0,
        "cache_hits": hits,
        "cache_hit_rate": round(hits / n, 4) if n else 0.0,
        "offline_blocked": by_status.get(OFFLINE_BLOCKED, 0),
        "p50_ms": round(_pct(ms, 0.50), 1),
        "p95_ms": round(_pct(ms, 0.95), 1),
        "max_ms": round(max(ms), 1) if ms else 0.0,
        "by_status": by_status,
        "by_provider": dict(sorted(by_provider.items(), key=lambda kv: -kv[1]["ms"])),
        "by_run": by_run,
    }


# A module-level log so a stage deep in the call tree can record without having
# the object threaded through every signature. set_log() is called once per run.
_active: CallLog | None = None


def set_log(log: CallLog | None) -> None:
    global _active
    _active = log


def active() -> CallLog:
    """The current log, or a disabled one so callers never need a None check."""
    global _active
    if _active is None:
        _active = CallLog(enabled=bool(os.environ.get("FOURWELLS_LOG", "1") != "0"))
    return _active
