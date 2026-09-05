"""One index over everything the game has a name for.

WHY
---
The voice path only ever looked things up in one place: the destination slot
of a route command consulted the place list, and nothing else consulted
anything. Ships, commodities and shops were cached and searchable on the
Market page, but saying their names out loud reached nothing -- 280 ships and
205 commodities that the program knew and could not hear.

This puts them in one index, so "look up iron", "where can I buy a Cutlass"
and "set route to Lorville" are all the same operation: take what was heard,
find the thing in the game it names, and say what we know about it.

It also feeds the recogniser. Whisper leans on a vocabulary hint when a word
is ambiguous, and these are not English words -- left to itself it writes
"new beverage" for New Babbage and "art court" for ArcCorp. Priming it with
the real terms is what stops the mistake being made in the first place;
correcting afterwards is the safety net.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE = BASE_DIR / "config" / "datacache"

_INDEX = None


def _read(path):
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def build():
    """Every named thing, as one list of {n, kind, detail, live}.

    Deliberately flat: the matcher only needs a name and something to say
    about it. Anything richer belongs on the page that renders it.
    """
    out = []

    doc = _read(BASE_DIR / "config" / "places.json") or {}
    for p in doc.get("places", []):
        where = (" in " + p["in"]) if p.get("in") else ""
        out.append({"n": p["n"], "kind": "place", "k": p.get("k", "place"),
                    "detail": p.get("k", "place") + where,
                    "live": bool(p.get("live"))})

    ships = (_read(CACHE / "vehicles.json") or {}).get("rows") or []
    for v in ships:
        name = (v.get("name") or "").strip()
        if not name:
            continue
        bits = [b for b in (v.get("company_name"),
                            "cargo %s SCU" % v.get("scu") if v.get("scu") else None,
                            "crew %s" % v.get("crew") if v.get("crew") else None)
                if b]
        out.append({"n": name, "kind": "ship", "k": "ship",
                    "detail": ", ".join(bits) or "ship",
                    "live": bool(v.get("is_available_live", 1))})

    comms = (_read(CACHE / "commodities.json") or {}).get("rows") or []
    for c in comms:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        bits = []
        if c.get("price_buy"):
            bits.append("buy ~%s aUEC" % round(float(c["price_buy"])))
        if c.get("price_sell"):
            bits.append("sell ~%s aUEC" % round(float(c["price_sell"])))
        if c.get("is_illegal"):
            bits.append("ILLEGAL")
        out.append({"n": name, "kind": "commodity", "k": "commodity",
                    "detail": ", ".join(bits) or "commodity",
                    "live": bool(c.get("is_available", 1))})

    terms = (_read(CACHE / "terminals.json") or {}).get("rows") or []
    seen = set()
    for t in terms:
        name = (t.get("nickname") or t.get("name") or "").strip()
        low = name.lower()
        if not name or low in seen:
            continue
        seen.add(low)
        where = t.get("star_system_name") or ""
        out.append({"n": name, "kind": "shop", "k": t.get("type") or "terminal",
                    "detail": ("%s in %s" % (t.get("type") or "terminal", where)).strip(),
                    "live": t.get("is_available_live") in (1, "1", True)})

    return out


def index():
    global _INDEX
    if _INDEX is None:
        _INDEX = build()
    return _INDEX


def look_up(spoken, kinds=None, limit=5):
    """What in the game is he naming? Returns a list of matches, best first.

    Reuses the same scorer the route command uses -- characters, numbers as
    digits, and how it sounds -- so a name that works when spoken as a
    destination works when spoken as a lookup. One matcher, one behaviour.
    """
    import main

    # "where can I buy A cutlass" -- the article belongs to the sentence, not
    # the ship. Left on, it costs real points against a short name.
    spoken = (spoken or "").strip()
    for article in ("a ", "an ", "the ", "some "):
        if spoken.lower().startswith(article):
            spoken = spoken[len(article):]
            break

    rows = index()
    if kinds:
        rows = [r for r in rows if r["kind"] in kinds]
    if not rows or not (spoken or "").strip():
        return []

    scored = []
    for r in rows:
        best, score, _ = main._score_places(spoken, [r])
        if score >= 62:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], not x[1]["live"], len(x[1]["n"])))

    out, seen = [], set()
    for score, r in scored:
        low = r["n"].lower()
        if low in seen:
            continue
        seen.add(low)
        out.append({**r, "score": round(score, 1)})
        if len(out) >= limit:
            break
    return out


def vocabulary(limit_each=90):
    """Names worth telling the recogniser about, most-said kinds first.

    Whisper's prompt is finite, so this is a budget, not a dump: the places
    you fly to and the ships you own get priority over 800 shop terminals.
    """
    rows = index()
    picks = []
    for kind, keep in (("place", limit_each), ("ship", limit_each),
                       ("commodity", limit_each)):
        names = sorted({r["n"] for r in rows
                        if r["kind"] == kind and r["live"]}, key=len)
        picks.extend(names[:keep])
    return picks


if __name__ == "__main__":
    rows = index()
    import collections
    print("indexed:", dict(collections.Counter(r["kind"] for r in rows)))
    for q in ("iron", "gold", "cutlass", "lorville", "quantanium",
              "aurora", "art court", "new beverage"):
        hits = look_up(q, limit=3)
        print("\n  %-14s ->" % q, "nothing" if not hits else "")
        for h in hits:
            print("      %-28s %-10s %-40s %.0f"
                  % (h["n"], h["kind"], h["detail"][:40], h["score"]))
