"""Read where the player is and where the game just plotted, from Game.log.

WHY THIS EXISTS
---------------
Our starmap knew every place in the 'verse and nothing about the player. So a
route plotted by voice appeared in the game and not on our map, and the map
could not answer "where am I" -- which is the one thing it needs to know
before it can be more useful than the in-game one.

Star Citizen has no API for this, but it narrates itself into Game.log, and
two lines carry what we need:

    ...  planet cells: 0 [16384] meshes: 0 [2048] name: OOC_Stanton_4_Microtech
        the cell that is loaded around you -- i.e. where you are

    ... OnPlayerRequestFuelToQuantumTarget|Player has requested fuel
        calculation to destination ObjectContainer_Lorville_City [QuantumTravel]
        the destination the game itself just plotted

The names are the engine's, not the ones a person says, so each is normalised
and then resolved against the same places index the voice commands use. That
means one source of truth for names: if the map knows a place, so does this.

Reading only. Nothing here writes to the game or touches its files.
"""
from __future__ import annotations

import io
import os
import re
import time
from pathlib import Path

# The two lines worth reading, and nothing else. Matching narrowly keeps this
# working when CIG changes unrelated logging, which they do every patch.
_WHERE = re.compile(r"name:\s*(OOC_[A-Za-z0-9_]+)")
_DEST = re.compile(r"requested fuel calculation to destination\s+([A-Za-z0-9_@]+)")
_STAMP = re.compile(r"^<([0-9T:.\-]+Z)>")

# Engine names carry wrappers a person never says. Strip them before the
# fuzzy match, or "ObjectContainer_Lorville_City" scores worse than it should.
_STRIP_PREFIX = ("ObjectContainer_", "OOC_", "SolarSystem_", "Stanton_", "Pyro_")
_STRIP_SUFFIX = ("_LOC", "_City", "_Station", "_Landing_Zone", "_LandingZone")


def default_log_path():
    """Find Game.log next to the player's own actionmaps.xml.

    sc_keybinds already worked out where the game lives; reusing its answer
    means one place to fix if the install moves.
    """
    try:
        import sc_keybinds
        found = sc_keybinds.find_actionmaps()  # .../LIVE/USER/Client/0/Profiles/default/actionmaps.xml
        if found:
            p = Path(found)
            for parent in p.parents:
                cand = parent / "Game.log"
                if cand.is_file():
                    return cand
    except Exception:
        pass
    for guess in (r"E:\Games Obly\RSI\StarCitizen\LIVE\Game.log",
                  r"C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log"):
        if os.path.isfile(guess):
            return Path(guess)
    return None


def humanise(engine_name):
    """'ObjectContainer_Lorville_City' -> 'Lorville'. Best effort, never raises."""
    if not engine_name:
        return ""
    name = engine_name
    for p in _STRIP_PREFIX:
        if name.startswith(p):
            name = name[len(p):]
    for s in _STRIP_SUFFIX:
        if name.endswith(s):
            name = name[: -len(s)]
    # "Stanton_4_Microtech" -> "Microtech": the leading system and index are
    # positional, not part of the name anyone uses.
    parts = [x for x in name.split("_") if x]
    while parts and (parts[0].isdigit() or re.fullmatch(r"[0-9]+[a-z]?", parts[0])):
        parts.pop(0)
    if len(parts) > 1 and re.fullmatch(r"[0-9]+[a-z]?", parts[-1]):
        parts.pop()
    return " ".join(parts).strip()


def read(log_path=None, tail_bytes=400_000):
    """Current location, last plotted destination, and the plots this session.

    Only the tail is read: Game.log runs to megabytes over a long session and
    everything we want is recent. A missing or locked file returns empties
    rather than raising -- the map still has to draw.
    """
    path = Path(log_path) if log_path else default_log_path()
    out = {"log": str(path) if path else None, "found": False,
           "here": None, "here_raw": None,
           "destination": None, "destination_raw": None,
           "plots": [], "age_s": None}
    if not path or not path.is_file():
        return out

    try:
        size = path.stat().st_size
        out["age_s"] = round(time.time() - path.stat().st_mtime, 1)
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()                 # drop the half line we landed in
            lines = f.readlines()
    except OSError:
        return out

    out["found"] = True
    plots = []
    for line in lines:
        m = _WHERE.search(line)
        if m:
            out["here_raw"] = m.group(1)
        m = _DEST.search(line)
        if m and m.group(1):
            stamp = _STAMP.match(line.strip())
            plots.append({"raw": m.group(1),
                          "at": stamp.group(1) if stamp else ""})

    # The game re-requests fuel for the same target repeatedly while the map is
    # open, so collapse runs -- otherwise one plot reads as twenty.
    collapsed = []
    for p in plots:
        if not collapsed or collapsed[-1]["raw"] != p["raw"]:
            collapsed.append(p)
    out["plots"] = collapsed[-20:]
    if collapsed:
        out["destination_raw"] = collapsed[-1]["raw"]

    out["here"] = humanise(out["here_raw"])
    out["destination"] = humanise(out["destination_raw"])
    return out


def resolved(log_path=None):
    """Same, with every name run through the map's own place index.

    Uses main.resolve_destination so a place the map can draw is the same
    place the voice commands can plot -- one index, no second spelling list.
    """
    state = read(log_path)
    try:
        import main
    except Exception:
        return state

    def fix(name):
        if not name:
            return None
        target, note = main.resolve_destination(name)
        return {"name": target, "note": note}

    state["here_place"] = fix(state.get("here"))
    state["destination_place"] = fix(state.get("destination"))
    for p in state.get("plots", []):
        p["place"] = fix(humanise(p["raw"]))
    return state


if __name__ == "__main__":
    import json
    print(json.dumps(resolved(), indent=2))
