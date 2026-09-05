"""
Read the player's real Star Citizen keybinds and check our commands against them.

WHY THIS EXISTS: commands.json ships with Star Citizen's *default* keys. Any
player who has rebound something -- or who flies a HOTAS -- has a setup we're
not sending the right input for, and the failure is silent: the console says
it matched the command, and nothing happens in game.

WHAT STAR CITIZEN ACTUALLY STORES (this is the part that trips people up):

    <install>\\LIVE\\USER\\Client\\0\\Profiles\\default\\actionmaps.xml

is written automatically by the game, but it holds ONLY the bindings the
player has CHANGED. Defaults are not in it -- they live inside Data.p4k,
the game's 150 GB+ packed archive. We read those ONCE, offline, to build
COMMAND_TO_SC_ACTION below (see tools/); at runtime we never touch the
p4k. So:

    effective binding = our shipped default table, overridden by actionmaps.xml

That is also why a player on stock keybinds needs no file and no setup: an
absent or near-empty actionmaps.xml means "everything is default", and our
table is already correct for them.

Do NOT ask players to use the in-game keybind *export* instead. It also only
writes deltas, and in testing it produced a 498-byte file containing zero
actions -- a useless round trip.

INPUT PREFIXES in that file: kb1_ keyboard, mo1_ mouse, js1_/js2_ joystick,
gp1_ gamepad. A prefix with nothing after it (e.g. "js1_") means the player
cleared that binding. Only kb1_ and mo1_ are things this program can send.
"""

import string
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# Our command id -> the Star Citizen action it corresponds to.
#
# Derived from Star Citizen's own defaultProfile.xml (extracted from
# Data.p4k, decoded from CryXmlB): each of our keys was matched against
# the action that actually DEFAULTS to that key, restricted to ship/seat
# actionmaps. Every entry was then reviewed by hand, because auto-matching
# alone gets it wrong -- "lalt+h" resolves to both toggleAttachHelmet and
# a countermeasure action, and only one of those is what we mean.
#
# Commands whose owning action could not be confirmed are left out on
# purpose and reported as unchecked. A wrong action name here would
# produce confident, wrong advice, which is worse than no advice.
COMMAND_TO_SC_ACTION = {
    # Ship / seat actions
    "open_mobiglas":              "mobiglas",
    "close_mobiglas":             "mobiglas",
    "open_map":                   "v_starmap",
    "nav_mode":                   "v_master_mode_cycle_long",
    "engage_quantum_drive":       "v_toggle_qdrive_engagement",
    "landing_gear":               "v_toggle_landing_system",
    "autoland":                   "v_autoland",
    "toggle_vtol":                "v_vtol_toggle",
    "cycle_flight_configuration": "v_transform_cycle",
    "request_landing":            "v_atc_request",
    "request_cargo_loading":      "v_atc_loading_area_request",
    "toggle_power_thrusters":     "v_power_toggle_thrusters",
    "toggle_power_shields":       "v_power_toggle_shields",
    "toggle_power_weapons":       "v_power_toggle_weapons",
    "full_power_weapons":         "v_engineering_assignment_weapons_max",
    "full_power_engines":         "v_engineering_assignment_engine_max",
    "full_power_shields":         "v_engineering_assignment_shields_max",
    "raise_power_weapons":        "v_engineering_assignment_weapons_increase",
    "lower_power_weapons":        "v_engineering_assignment_weapons_decrease",
    "raise_power_engines":        "v_engineering_assignment_engine_increase",
    "lower_power_engines":        "v_engineering_assignment_engine_decrease",
    "raise_power_shields":        "v_engineering_assignment_shields_increase",
    "lower_power_shields":        "v_engineering_assignment_shields_decrease",
    "headlights":                 "v_lights",
    "toggle_flight_ready":        "v_flightready",
    "cut_all_power":              "v_power_toggle",
    "self_destruct":              "v_self_destruct",
    "hail_target":                "v_target_hail",
    "ping":                       "v_invoke_ping",
    "emergency_exit_seat":        "v_emergency_exit",
    "eject":                      "v_eject",
    "boost":                      "v_afterburner",
    "decoupled_mode":             "v_ifcs_vector_decoupling_toggle",
    "spacebrake":                 "v_space_brake",
    "toggle_scanning_mode":       "v_toggle_scan_mode",
    "toggle_mining_mode":         "v_toggle_mining_mode",
    "toggle_salvage_mode":        "v_toggle_salvage_mode",
    "next_operator_mode":         "v_operator_mode_cycle_forward",
    "cycle_camera_view":          "v_view_cycle_fwd",
    "lock_unlock_doors":          "v_toggle_all_doorlocks",
    "toggle_port_locks":          "v_toggle_all_portlocks",
    "visor_wipe":                 "visor_wipe",
    "open_close_doors":           "v_toggle_all_doors",
    "interact":                   "v_view_interact",
    # On-foot action, but reachable from the seat
    "toggle_helmet":              "toggleAttachHelmet",
    # Deliberately NOT mapped -- no ship action confirmed to own these keys:
    #   confirm_route, exit_seat, park_ship, present
}

# Star Citizen key token -> pydirectinput key name. Only the tokens that
# differ; anything not listed passes through unchanged (letters, digits).
SC_KEY_ALIASES = {
    "lalt": "altleft", "ralt": "altright",
    "lshift": "shiftleft", "rshift": "shiftright",
    "lctrl": "ctrlleft", "rctrl": "ctrlright",
    "period": ".", "comma": ",", "slash": "/", "backslash": "\\",
    "minus": "-", "equals": "=", "semicolon": ";", "apostrophe": "'",
    "lbracket": "[", "rbracket": "]", "grave": "`",
    "pgup": "pageup", "pgdn": "pagedown",
    "enter": "enter", "escape": "esc", "capslock": "capslock",
}


def _translate_token(token: str) -> str:
    if token.startswith("np_"):          # numpad
        return "num" + token[3:]
    return SC_KEY_ALIASES.get(token, token)


def sc_input_to_keys(sc_input: str):
    """'kb1_lalt+k' -> ['altleft', 'k']. Returns None if not a keyboard bind."""
    if not sc_input.startswith("kb1_"):
        return None
    body = sc_input[4:]
    if not body:
        return None                       # 'kb1_' alone = binding cleared
    return [_translate_token(t) for t in body.split("+")]


def classify(sc_input: str) -> str:
    """What kind of device is this binding on?"""
    if not sc_input:
        return "unbound"
    prefix, _, body = sc_input.strip().partition("_")
    if not body.strip():
        return "unbound"                  # e.g. 'js1_' -- player cleared it
    return {"kb1": "keyboard", "mo1": "mouse",
            "js1": "joystick", "js2": "joystick",
            "gp1": "gamepad"}.get(prefix, "other")


CACHE_NAME = "sc_keybind_path.cache"
SCAN_BUDGET_S = 4.0

_TAIL = "StarCitizen/*/USER/Client/*/Profiles/default/actionmaps.xml"

# The launcher's DEFAULT install is "Roberts Space Industries\StarCitizen",
# not "RSI" -- only a custom library folder gets called RSI. Missing the
# default name meant a stock install was never found at all.
_LAUNCHER_DIRS = ("RSI", "Roberts Space Industries")

# Depth 0-1. Measured across nine drives: every one of these returns in
# under 0.6s, and this is what actually found the install on this machine
# (E:\Games Obly\RSI\... in 0.01s).
FAST_PATTERNS = [f"{prefix}{d}/{_TAIL}"
                 for d in _LAUNCHER_DIRS for prefix in ("", "*/")]

# Depth 2. Costs ~1.9s per large drive and found nothing on any of them,
# so it only runs as a fallback when the cheap patterns come up empty.
SLOW_PATTERNS = [f"*/*/{d}/{_TAIL}" for d in _LAUNCHER_DIRS]

DRIVE_FIXED = 3


# Top-level names that mean "this drive letter is really a cloud account
# streamed over the network", not a local disk. Google Drive and OneDrive
# both report themselves as DRIVE_FIXED, so the drive type alone won't
# save us -- and a deep glob against one enumerates the whole account.
CLOUD_MARKERS = {"my drive", "shared drives", "other computers", "onedrive"}


def _scannable_drives():
    """Local fixed disks only, skipping cloud-backed drive letters.

    Two hazards, both found the hard way:

    * Network and removable drives can block for many seconds per call.
      GetDriveTypeW filters those out without touching them.
    * A cloud drive (Google Drive, OneDrive) reports itself as FIXED but is
      really a network filesystem. Listing its root is fast, so a timing
      probe does NOT catch it -- only the deep `*/*/RSI/...` pattern is
      slow. That hung startup indefinitely on the dev machine while Drive
      was syncing, so cloud roots are identified by name and skipped.
    """
    import ctypes

    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(root) != DRIVE_FIXED:
                continue
        except Exception:
            continue

        try:
            top = {p.name.lower() for p in Path(root).iterdir()}
        except OSError:
            continue
        if top & CLOUD_MARKERS:
            continue

        drives.append(Path(root))
    return drives


def _scan_one(root: Path, patterns, hits: list):
    for pattern in patterns:
        try:
            hits.extend(root.glob(pattern))
        except OSError:
            continue


def _scan_all(patterns, hits: list):
    """Scan every eligible drive in parallel, one thread per drive."""
    workers = []
    for root in _scannable_drives():
        t = threading.Thread(target=_scan_one, args=(root, patterns, hits), daemon=True)
        t.start()
        workers.append(t)
    for t in workers:
        t.join()


def _scan(hits: list):
    """Cheap patterns first; only pay for the deep ones if nothing turned up."""
    _scan_all(FAST_PATTERNS, hits)
    if not hits:
        _scan_all(SLOW_PATTERNS, hits)


def find_actionmaps(base_dir: Path | None = None, budget_s: float = SCAN_BUDGET_S):
    """Locate every actionmaps.xml on this PC, newest first.

    The RSI launcher lets the player put their library anywhere, so this
    globs for the folder shape rather than assuming Program Files. Tested
    against a real install buried at E:\\Games Obly\\RSI\\StarCitizen\\LIVE.

    Bounded by a hard time budget on a daemon thread. Startup must never
    hang waiting on a filesystem, no matter how strange the player's disk
    layout is -- a tool that doesn't start is worse than one that misses
    a keybind override.
    """
    # A remembered path makes every launch after the first instant.
    if base_dir is not None:
        cache = base_dir / CACHE_NAME
        try:
            if cache.exists():
                cached = Path(cache.read_text(encoding="utf-8").strip())
                if cached.is_file():
                    return [cached]
        except OSError:
            pass

    hits: list = []
    worker = threading.Thread(target=_scan, args=(hits,), daemon=True)
    worker.start()
    worker.join(budget_s)
    if worker.is_alive():
        return None                                    # timed out; caller reports it

    found = sorted(set(hits), key=lambda p: p.stat().st_mtime, reverse=True)

    if base_dir is not None and found:
        try:
            (base_dir / CACHE_NAME).write_text(str(found[0]), encoding="utf-8")
        except OSError:
            pass
    return found


def parse_actionmaps(path: Path) -> dict:
    """{action_name: sc_input} for every binding the player has changed."""
    binds = {}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return binds
    for action in root.iter("action"):
        name = action.get("name")
        for rebind in action.iter("rebind"):
            # SC writes a cleared binding as "js1_ " -- device prefix, then
            # whitespace. Strip it or that reads as a real joystick button.
            value = (rebind.get("input") or "").strip()
            # A player can bind one action on several devices. Prefer a
            # keyboard bind, since that's the only kind we can send.
            if name not in binds or (classify(value) == "keyboard"
                                     and classify(binds[name]) != "keyboard"):
                binds[name] = value
    return binds


def audit(commands, binds: dict):
    """Compare our configured keys against the player's real bindings.

    Returns (findings, unmapped_rebinds) where each finding is a dict with
    a 'status' of ok / differs / not_keyboard / cleared.
    """
    findings = []
    for cmd in commands:
        action = COMMAND_TO_SC_ACTION.get(cmd["id"])
        if not action or action not in binds:
            continue                       # default binding, or not mapped
        sc_input = binds[action]
        kind = classify(sc_input)
        entry = {"id": cmd["id"], "action": action,
                 "sc_input": sc_input, "kind": kind,
                 "ours": cmd.get("keys") or []}
        if kind == "keyboard":
            theirs = sc_input_to_keys(sc_input) or []
            entry["theirs"] = theirs
            entry["status"] = "ok" if [k.lower() for k in entry["ours"]] == theirs else "differs"
        elif kind == "unbound":
            entry["status"] = "cleared"
        else:
            entry["status"] = "not_keyboard"
        findings.append(entry)

    mapped_actions = set(COMMAND_TO_SC_ACTION.values())
    unmapped = {a: v for a, v in binds.items() if a not in mapped_actions}
    return findings, unmapped


def apply_overrides(commands, findings):
    """Rewrite our keys to the player's actual keyboard bindings, in memory.

    This is the point of the whole module: if they moved an action to a
    different key, send THEIR key instead of making them hand-edit
    commands.json. Only rewrites where they have a real keyboard binding
    -- a joystick binding has no key to send, so those are left alone and
    reported instead.

    commands.json on disk is never touched; the player's file stays theirs.
    """
    by_id = {c["id"]: c for c in commands}
    applied = []
    for f in findings:
        if f["status"] != "differs":
            continue
        cmd = by_id.get(f["id"])
        if cmd is None or not f.get("theirs"):
            continue
        cmd["keys"] = list(f["theirs"])
        applied.append(f)
    return applied


def actionmaps_under(root: Path):
    """Find actionmaps.xml given whatever level of the install a player names.

    People will paste any of these, so accept all of them rather than
    demanding an exact path:
        ...\\RSI                      ...\\RSI\\StarCitizen
        ...\\RSI\\StarCitizen\\LIVE     ...\\actionmaps.xml itself
    """
    # Accepts a str or a Path. Pasted Windows paths often arrive wrapped in
    # quotes ("Copy as path" does this), so strip those before using it.
    root = Path(str(root).strip().strip('"').strip("'"))
    if root.is_file() and root.name.lower() == "actionmaps.xml":
        return root
    if not root.is_dir():
        return None

    # Specific shapes first -- these are what people actually paste, and
    # matching the full tail avoids picking up some unrelated actionmaps.xml.
    tail = "USER/Client/*/Profiles/default/actionmaps.xml"
    patterns = [tail, f"*/{tail}", f"*/*/{tail}"]

    # Then a bounded generic sweep, so a path pointing part-way INTO the
    # install still works -- someone who pastes ...\Profiles\default or
    # ...\Client shouldn't be told their install doesn't exist.
    patterns += ["actionmaps.xml", "*/actionmaps.xml",
                 "*/*/actionmaps.xml", "*/*/*/actionmaps.xml"]

    for pattern in patterns:
        try:
            for hit in root.glob(pattern):
                if hit.is_file():
                    return hit
        except OSError:
            continue
    return None


def find_install_roots(budget_s: float = SCAN_BUDGET_S):
    """Locate the Star Citizen INSTALL, whether or not keybinds were changed.

    Critically different from find_actionmaps(). Star Citizen writes
    actionmaps.xml only once the player edits a keybind, so a player on stock
    keybinds has no such file -- and searching for it reports "no install
    found", which is wrong, alarming, and unfixable by the player. A tester
    hit exactly that.

    This looks for the USER folder, which always exists once the game has run.
    """
    tail = "StarCitizen/*/USER"
    fast = [f"{prefix}{d}/{tail}" for d in _LAUNCHER_DIRS for prefix in ("", "*/")]
    slow = [f"*/*/{d}/{tail}" for d in _LAUNCHER_DIRS]

    hits: list = []

    def scan_drive(root, patterns):
        for pattern in patterns:
            try:
                hits.extend(p for p in root.glob(pattern) if p.is_dir())
            except OSError:
                continue

    def scan():
        # Cheap patterns across all drives in parallel first. The depth-2
        # sweep costs ~1.9s per large drive, so running it up front blows the
        # whole budget and finds nothing -- which is exactly what happened
        # the first time this function was written.
        drives = _scannable_drives()
        for patterns in (fast, slow):
            workers = [threading.Thread(target=scan_drive, args=(d, patterns), daemon=True)
                       for d in drives]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
            if hits:
                return

    worker = threading.Thread(target=scan, daemon=True)
    worker.start()
    worker.join(budget_s)
    return sorted(set(hits))


def looks_like_install(path: Path) -> bool:
    """True if this folder is (or contains) a Star Citizen install."""
    path = Path(str(path).strip().strip('"').strip("'"))
    if not path.is_dir():
        return False
    for pattern in ("USER", "*/USER", "*/*/USER", "*/*/*/USER"):
        try:
            if any(p.is_dir() for p in path.glob(pattern)):
                return True
        except OSError:
            continue
    return False


def browse_for_folder(title="Select your Star Citizen folder"):
    """Open the normal Windows folder picker. Returns a Path, or None.

    Asking someone to type or paste a filesystem path is the worst possible
    prompt: they don't know it, it's long, and a stray quote or trailing
    space breaks it. People know how to find a folder by clicking through
    it, so give them the dialog they already use everywhere else.

    Driven through PowerShell's Shell.Application COM object rather than
    tkinter -- tkinter would add roughly 10 MB to the exe for one dialog,
    and we already shell out to PowerShell elsewhere.
    """
    import subprocess

    script = (
        "$ErrorActionPreference='Stop';"
        "$shell = New-Object -ComObject Shell.Application;"
        f"$f = $shell.BrowseForFolder(0, '{title}', 0, 17);"
        "if ($f -ne $null) { Write-Output $f.Self.Path }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    picked = (result.stdout or "").strip().splitlines()
    if picked and picked[-1].strip():
        return Path(picked[-1].strip())
    return None


def ask_for_install(base_dir: Path | None):
    """Last resort: have the player point at their install.

    Auto-detection covers the normal cases, but a player on a drive layout
    we didn't anticipate shouldn't be stuck with a tool that silently uses
    the wrong keys. They always know where they installed the game, so ask
    rather than guess. Answer is cached, so this happens at most once.
    """
    print()
    print("  Couldn't find your Star Citizen install automatically.")
    print()
    print("  A folder browser is opening -- click through to your Star")
    print("  Citizen folder and hit OK. Any level works: the RSI folder,")
    print("  StarCitizen, or LIVE.")
    print()
    print("  (Cancel it if you'd rather type the path, or skip entirely --")
    print("   the program still works, it just assumes default keys.)")

    answer = browse_for_folder()

    if answer is None:
        # Dialog cancelled or unavailable -- fall back to typing.
        print()
        print(r"  Paste the folder instead (e.g. D:\Games\RSI\StarCitizen\LIVE)")
        print("  or press Enter to skip.")
        try:
            typed = input("  Star Citizen folder: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not typed:
            return None
        answer = Path(typed)

    found = actionmaps_under(answer)
    if not found:
        # Distinguish "wrong folder" from "right folder, stock keybinds".
        # Telling someone their correct answer was wrong is the fastest way
        # to make them think the program is broken.
        if looks_like_install(answer):
            print()
            print("  That's your Star Citizen install -- but there's no keybind")
            print("  file in it, which means you're still on the game's default")
            print("  keys. Nothing to adapt: the program already matches them.")
            print("  Change a binding in game and it'll pick that up next launch.")
        else:
            print(f"  That doesn't look like a Star Citizen install: {answer}")
            print("  Look for a folder containing StarCitizen\\LIVE.")
        print("  Continuing with default keys.")
        return None

    print(f"  Found it: {found}")
    if base_dir is not None:
        try:
            (base_dir / CACHE_NAME).write_text(str(found), encoding="utf-8")
            print("  Saved, so you won't be asked again.")
        except OSError:
            pass
    return found


def report(commands, path: Path | None = None, base_dir: Path | None = None,
           allow_prompt: bool = False):
    """Human-readable summary, printed at startup. Returns () if nothing to say."""
    if path is None:
        candidates = find_actionmaps(base_dir)

        if not candidates:
            # No actionmaps.xml. Before crying "install not found", check
            # whether the game is simply installed with STOCK keybinds --
            # that is the normal state for a new player, it is not a failure,
            # and prompting them to hunt for a folder is both wrong and
            # unresolvable (the file they'd be pointing us at doesn't exist).
            installs = find_install_roots()
            if installs:
                return ["Star Citizen keybinds: you're on the game's default "
                        "keys -- nothing to adapt.",
                        f"  (found your install at {installs[0].parent}; Star Citizen only",
                        "   writes a keybind file once you change a binding in game)"]

            asked = ask_for_install(base_dir) if allow_prompt else None
            if asked is None:
                why = ("the scan timed out" if candidates is None
                       else "no install was found")
                return [f"Star Citizen keybinds: using default keys ({why}).",
                        "  If commands fire the wrong action, delete "
                        f"'{CACHE_NAME}' next to the program and restart to be",
                        "  asked for your Star Citizen folder again."]
            path = asked
        else:
            path = candidates[0]

    binds = parse_actionmaps(path)
    if not binds:
        return ["Star Citizen keybinds: using defaults (no changes on file)."]

    findings, unmapped = audit(commands, binds)
    applied = apply_overrides(commands, findings)
    problems = [f for f in findings if f["status"] not in ("ok", "differs")]

    lines = [f"Star Citizen keybinds: read {len(binds)} custom bindings from {path.parent}"]
    for f in applied:
        lines.append(f"  [OK] {f['id']}: using your key '{'+'.join(f['theirs'])}' "
                     f"instead of the default '{'+'.join(f['ours'])}'")
    if not problems and not applied:
        lines.append("  All checked commands match your bindings.")
    for f in problems:
        if f["status"] == "not_keyboard":
            lines.append(f"  [X] {f['id']}: bound to your {f['kind']} ({f['sc_input']}), "
                         f"not the keyboard -- voice can't trigger this one")
        elif f["status"] == "cleared":
            lines.append(f"  [X] {f['id']}: you've cleared this binding in game "
                         f"-- nothing to send")
    if unmapped:
        lines.append(f"  ({len(unmapped)} other rebound actions we don't track yet -- "
                     f"if a command misbehaves, that's the first place to look)")
    return lines


if __name__ == "__main__":
    import json

    here = Path(__file__).parent
    config = json.loads((here / "config" / "commands.json").read_text(encoding="utf-8"))

    found = find_actionmaps()
    print(f"actionmaps.xml files found: {len(found)}")
    for f in found:
        print(f"   {f}")
    print()
    for line in report(config["commands"]):
        print(line)
