"""Check what we heard against what the game actually did.

WHY
---
Two histories exist and neither one alone tells the truth:

    config/current_route.json   what was SAID, and what we resolved it to
    Star Citizen's Game.log     what the game ACTUALLY plotted

Comparing them turns "sometimes it works" into a list. Every voice plot either
shows up in the game's own log a moment later with the same destination, or it
does not -- and the ones that do not are the errors worth fixing. A mismatch
says the recogniser or the matcher picked the wrong place; silence says the
macro never got as far as the game, which is a different fault with a
different fix.

Nothing here changes anything. It reads two files and reports.
"""
from __future__ import annotations

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROUTE = BASE_DIR / "config" / "current_route.json"

# How long after speaking the game may take to log the plot. Every confirmed
# pair in the real data landed within a second, so a wide window buys nothing
# and costs accuracy: at 90s it paired "terra gateway" with a Lorville plot 58
# seconds later and called it a mismatch, when in truth the first never
# reached the game at all and the second was a different trip. Anything slower
# than this is not the same action.
WINDOW_S = 12


def _read(path):
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _local_to_epoch(stamp):
    """'2026-09-04 20:21:00' in local time -> epoch seconds."""
    try:
        return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError):
        return None


def _utc_to_epoch(stamp):
    """'2026-09-05T00:21:00.995Z' -> epoch seconds."""
    if not stamp:
        return None
    try:
        txt = stamp.rstrip("Z")
        if "." in txt:
            txt = txt.split(".")[0]
        dt = datetime.strptime(txt, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def check(log_path=None):
    """Reconcile the two histories. Returns a report dict.

    Each voice plot gets one of four verdicts:

      confirmed   the game logged the same place, soon after
      mismatch    the game logged a DIFFERENT place -- we resolved wrongly
      unseen      the game logged nothing -- the macro never reached it
      refused     we deliberately did not type it (not in this build, etc.)
    """
    doc = _read(ROUTE) or {}
    legs = doc.get("legs") or []

    try:
        import sc_state
        state = sc_state.resolved(log_path)
    except Exception as exc:
        return {"ok": False, "why": "could not read Game.log: %s" % exc,
                "spoken": len(legs), "rows": []}

    plots = []
    for pl in state.get("plots", []):
        plots.append({
            "raw": pl["raw"],
            "name": (pl.get("place") or {}).get("name") or "",
            "epoch": _utc_to_epoch(pl.get("at")),
            "at": pl.get("at", ""),
            "used": False,
        })

    rows = []
    for leg in legs:
        said = leg.get("heard", "")
        ours = leg.get("destination", "")
        when = _local_to_epoch(leg.get("at"))
        note = leg.get("note", "")

        if not ours or "no match" in note:
            rows.append({"heard": said, "ours": ours, "verdict": "refused",
                         "detail": note, "at": leg.get("at")})
            continue

        # The game's nearest plot after we spoke, inside the window.
        best = None
        for p in plots:
            if p["used"] or p["epoch"] is None or when is None:
                continue
            gap = p["epoch"] - when
            if -5 <= gap <= WINDOW_S and (best is None or gap < best[0]):
                best = (gap, p)

        if best is None:
            rows.append({"heard": said, "ours": ours, "verdict": "unseen",
                         "detail": "the game logged no plot after this",
                         "at": leg.get("at")})
            continue

        gap, p = best
        p["used"] = True
        same = (p["name"] or "").lower() == (ours or "").lower()
        # A city sits on a planet; routing to Lorville and the game logging
        # Hurston is not a mistake, it is the same journey described one level
        # up. Only flag a genuinely different destination.
        related = (p["name"] and ours
                   and (p["name"].lower() in ours.lower()
                        or ours.lower() in p["name"].lower()))
        rows.append({
            "heard": said, "ours": ours,
            "game": p["name"] or p["raw"], "raw": p["raw"],
            "verdict": "confirmed" if (same or related) else "mismatch",
            "detail": "%+.0fs" % gap, "at": leg.get("at"),
        })

    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1

    unclaimed = [p for p in plots if not p["used"]]
    return {
        "ok": True,
        "spoken": len(legs),
        "logged": len(plots),
        "tally": tally,
        "rows": rows,
        "game_only": [{"name": p["name"] or p["raw"], "at": p["at"]}
                      for p in unclaimed],
    }


if __name__ == "__main__":
    rep = check()
    if not rep["ok"]:
        raise SystemExit(rep["why"])
    print("spoken plots: %d   game-logged plots: %d" % (rep["spoken"], rep["logged"]))
    print("verdicts    :", rep["tally"])
    print()
    print("%-24s %-22s %-22s %s" % ("HEARD", "WE RESOLVED TO", "GAME PLOTTED", "VERDICT"))
    for r in rep["rows"]:
        print("  %-22s %-22s %-22s %-10s %s"
              % (r["heard"][:22], r["ours"][:22], r.get("game", "-")[:22],
                 r["verdict"], r["detail"][:34]))
    if rep["game_only"]:
        print()
        print("plotted in game with nothing spoken for it (you used the map by hand):")
        for g in rep["game_only"]:
            print("   %-24s %s" % (g["name"], g["at"][:19]))
