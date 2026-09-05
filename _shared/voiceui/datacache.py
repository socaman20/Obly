"""
Fetch-with-fallback and a disk cache, so "update" is one button and one click.

WHY
---
The lookup features need live data, and live data is the part most likely to
fail a user: the source moves, the server is down, the patch changed
everything, or they are on a plane. A tool that answers "error" in any of those
cases is worse than one that answers "here is what I knew on Tuesday".

So every question walks the same ladder, in order:

    1. fresh cache       inside its max age, answer instantly, no network
    2. primary source    UEX for us -- the good one
    3. backup source     a second opinion when the primary is down
    4. stale cache       expired, but true as of a date we can show
    5. bundled snapshot  shipped with the product, so a brand new install
                         with no internet still answers

It only fails after all five. Every answer carries where it came from and how
old it is, because "I don't know how current this is" is information the player
needs, not an admission we should hide.

GAME-AGNOSTIC
-------------
This knows nothing about commodities or ships. A product declares its own
`Endpoint` list; this fetches, caches and reports. Star Citizen's endpoints
live in the Star Citizen project, per the same rule as voicecore.
"""
from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .store import atomic_write_json

DAY = 86400          # UEX sends Cache-Control: max-age=86400. Honour it.
TIMEOUT = 20


@dataclass
class Endpoint:
    """One question a product wants answered, and where to ask it."""
    key: str                      # cache filename, e.g. "commodities"
    label: str                    # what to call it in the UI
    primary: str                  # full URL
    backup: str = ""              # optional second source
    unwrap: str = "data"          # key holding the payload, "" for a bare list
    max_age: int = DAY


@dataclass
class Result:
    key: str
    rows: list = field(default_factory=list)
    origin: str = "none"          # cache | primary | backup | stale | bundled
    fetched: float = 0.0
    error: str = ""

    @property
    def age_text(self) -> str:
        if not self.fetched:
            return "unknown age"
        secs = max(0, time.time() - self.fetched)
        if secs < 3600:
            return "%d min old" % (secs // 60)
        if secs < DAY:
            return "%d hr old" % (secs // 3600)
        return "%d days old" % (secs // DAY)

    @property
    def is_live(self) -> bool:
        return self.origin in ("primary", "backup")


class DataCache:
    """Cached fetching for a product's endpoint list."""

    def __init__(self, cache_dir, bundled_dir=None, user_agent="voice-control",
                 token: str = ""):
        self.dir = str(cache_dir)
        self.bundled = str(bundled_dir) if bundled_dir else None
        self.ua = user_agent
        self.token = token
        os.makedirs(self.dir, exist_ok=True)

    # -------------------------------------------------------------- network

    def _get(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": self.ua})
        if self.token:
            # UEX documents a Bearer token even though reads answer without
            # one today. Send it when we have it rather than depending on
            # unauthenticated access staying open.
            req.add_header("Authorization", "Bearer " + self.token)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))

    @staticmethod
    def _rows(doc, unwrap):
        payload = doc.get(unwrap, doc) if (unwrap and isinstance(doc, dict)) else doc
        if isinstance(payload, list):
            return payload
        return [payload] if payload else []

    # ---------------------------------------------------------------- cache

    def _path(self, key):
        return os.path.join(self.dir, key + ".json")

    def _read_cache(self, key):
        try:
            with io.open(self._path(key), encoding="utf-8") as f:
                doc = json.load(f)
            return doc.get("rows", []), float(doc.get("fetched", 0))
        except (OSError, ValueError, TypeError):
            return None, 0

    def _read_bundled(self, key):
        if not self.bundled:
            return None
        p = os.path.join(self.bundled, key + ".json")
        try:
            with io.open(p, encoding="utf-8") as f:
                doc = json.load(f)
            return doc.get("rows", doc if isinstance(doc, list) else [])
        except (OSError, ValueError, TypeError):
            return None

    def _write_cache(self, key, rows, origin):
        # Backups get their OWN file. Two sources answering the same question
        # rarely answer it in the same SHAPE -- UEX returns `name_full`, the
        # wiki returns something else -- so letting a backup write over the
        # primary's cache poisons it with rows the caller cannot read, and it
        # stays poisoned long after the primary comes back.
        #
        # This is not hypothetical: the fallback test in this session did
        # exactly that, PASSED, and left 50 wiki rows sitting where 280 UEX
        # rows belonged. A test that breaks the thing it proves is worse than
        # no test.
        path = self._path(key if origin == "primary" else key + ".backup")
        atomic_write_json(path, {
            "_readme": "Cached lookup data. Safe to delete -- it refetches.",
            "fetched": time.time(),
            "origin": origin,
            "rows": rows,
        })

    # ----------------------------------------------------------------- get

    def get(self, ep: Endpoint, force: bool = False) -> Result:
        """Walk the ladder. Never raises -- a Result always comes back."""
        cached, when = self._read_cache(ep.key)
        fresh = cached is not None and (time.time() - when) < ep.max_age

        if fresh and not force:
            return Result(ep.key, cached, "cache", when)

        errors = []
        for origin, url in (("primary", ep.primary), ("backup", ep.backup)):
            if not url:
                continue
            try:
                rows = self._rows(self._get(url), ep.unwrap)
                if rows:
                    self._write_cache(ep.key, rows, origin)
                    return Result(ep.key, rows, origin, time.time())
                errors.append("%s: empty" % origin)
            except (urllib.error.URLError, ValueError, OSError, TimeoutError) as e:
                errors.append("%s: %s" % (origin, type(e).__name__))

        if cached is not None:
            # Expired, but true as of a date we can show. Far better than
            # nothing, as long as we say how old it is.
            return Result(ep.key, cached, "stale", when, "; ".join(errors))

        bundled = self._read_bundled(ep.key)
        if bundled is not None:
            return Result(ep.key, bundled, "bundled", 0, "; ".join(errors))

        return Result(ep.key, [], "none", 0, "; ".join(errors) or "no source")

    def refresh_all(self, endpoints, on_step=None) -> list:
        """The one button. Refetch everything, report each step.

        `on_step(label, result)` is called after each endpoint so a UI can show
        progress instead of freezing -- a button that appears to hang is the
        thing people click twice.
        """
        out = []
        for ep in endpoints:
            res = self.get(ep, force=True)
            out.append(res)
            if on_step:
                on_step(ep.label, res)
        return out

    def status(self, endpoints) -> dict:
        """Ages and origins without touching the network."""
        rows = {}
        for ep in endpoints:
            cached, when = self._read_cache(ep.key)
            rows[ep.key] = {
                "label": ep.label,
                "have": cached is not None,
                "count": len(cached or []),
                "fetched": when,
                "fresh": cached is not None and (time.time() - when) < ep.max_age,
            }
        return rows
