"""Disk cache keyed by content hash.

Every expensive call — Foundry, folding, any fetch — goes through here. The
cache directory is committed, which means the demo run works offline and a
judge can reproduce our numbers without a GPU or a network.

That last property is worth protecting: `--offline` is the default, and a cache
miss in offline mode is a loud error rather than a silent network call.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


class CacheMiss(RuntimeError):
    """Raised when offline mode needs a value the cache does not have."""


def key_for(namespace: str, payload: Any) -> str:
    """Stable key from a namespace plus any JSON-serialisable payload.

    Sorted keys so that dict ordering never changes the hash — otherwise the
    same request caches twice and the committed cache stops being reproducible.
    """
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(blob).hexdigest()[:16]
    return f"{namespace}-{digest}"


class Cache:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR, offline: bool = True):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self._path(key)
        if p.exists():
            self.hits += 1
            return json.loads(p.read_text())["value"]
        return None

    def put(self, key: str, value: Any) -> None:
        self._path(key).write_text(
            json.dumps({"key": key, "value": value}, sort_keys=True, indent=2)
        )

    def memo(self, namespace: str, payload: Any, compute: Callable[[], Any]) -> Any:
        """Return cached value, or compute and store it.

        In offline mode a miss raises instead of calling `compute`, so we never
        quietly depend on the network during a demo.

        Every outcome is recorded to the call log — hit, miss, and the offline
        block in particular. A run that produces nothing because it was blocked
        offline looks identical, from the records alone, to a run whose model
        returned nothing useful, and that ambiguity has cost us time already.
        """
        from . import calllog

        log = calllog.active()
        key = key_for(namespace, payload)

        hit = self.get(key)
        if hit is not None:
            with log.call(namespace, "memo", request=payload, key=key) as slot:
                slot["status"] = calllog.CACHE_HIT
                slot["response"] = hit
            return hit

        self.misses += 1
        if self.offline:
            with log.call(namespace, "memo", request=payload, key=key) as slot:
                slot["status"] = calllog.OFFLINE_BLOCKED
                slot["response"] = "offline: no cached value, compute() not called"
            raise CacheMiss(
                f"offline: no cached value for {key} ({namespace}). "
                f"Re-run with --online once to populate it, then commit cache/."
            )

        with log.call(namespace, "compute", request=payload, key=key) as slot:
            value = compute()
            slot["response"] = value
        self.put(key, value)
        return value

    def stats(self) -> str:
        return f"cache {self.hits} hit / {self.misses} miss ({self.dir})"
