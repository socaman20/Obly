"""
Full self-test. Run before every build.

Exercises every subsystem from source: config, licensing, integrity,
activation, keybind detection, the three push-to-talk triggers, the
first-run note, and the build stamp. Prints PASS/FAIL per check and exits
non-zero if anything fails, so it can gate a release.

    venv\\Scripts\\python.exe selftest.py
"""

import os
import base64
import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

PASS, FAIL = [], []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return condition


print("=" * 70)
print("  STAR CITIZEN VOICE CONTROL -- SELF TEST")
print("=" * 70)

# ---------------------------------------------------------------- imports
print("\n[1] Modules import")
import activation          # noqa: E402
import build_info          # noqa: E402
import first_run           # noqa: E402
import integrity           # noqa: E402
import joystick_ptt        # noqa: E402
import licensing           # noqa: E402
import sc_keybinds         # noqa: E402
check("all modules import", True)
check("version is set", build_info.VERSION != "", build_info.VERSION)

# ----------------------------------------------------------------- config
print("\n[2] Config")
cfg_path = HERE / "config" / "commands.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
settings, commands = cfg["settings"], cfg["commands"]

# Bindings live in config/schemes/ now, not on the command. Apply the
# active scheme so the checks below see the same command dicts main.py does.
import control_scheme
_scheme = settings.get("control_scheme", control_scheme.DEFAULT_SCHEME)
_bindings = control_scheme.load(HERE, _scheme)
_unbound = control_scheme.apply(commands, _bindings, _scheme)
by_id = {c["id"]: c for c in commands}

check("commands.json is valid JSON", True, f"{len(commands)} commands")
check("control scheme loads", len(_bindings) > 0, f"{_scheme}: {len(_bindings)} bindings")
check("every command is bound in the default scheme", not _unbound,
      "unbound: " + ", ".join(_unbound) if _unbound else "all 50 bound")
check("autoland holds > 5s", by_id["autoland"]["hold_ms"] > 5000,
      f'{by_id["autoland"]["hold_ms"]} ms')
check("autoland is a keyhold on 'n'",
      by_id["autoland"]["type"] == "keyhold" and by_id["autoland"]["keys"] == ["n"])
check("boost holds 5s", by_id["boost"]["hold_ms"] == 5000,
      f'{by_id["boost"]["hold_ms"]} ms')
check("landing_gear still a tap (not a hold)", by_id["landing_gear"]["type"] == "keypress")
check("ptt_key unchanged", settings["ptt_key"] == "right ctrl", settings["ptt_key"])
check("joystick PTT settings present",
      "ptt_joystick_device" in settings and "ptt_joystick_button" in settings)
check("gamepad PTT set to X", settings.get("ptt_gamepad_button") == "X")
check("every command has phrases and an id",
      all(c.get("id") and c.get("phrases") for c in commands))
dupes = [i for i in by_id if sum(1 for c in commands if c["id"] == i) > 1]
check("no duplicate command ids", not dupes, str(dupes))

# -------------------------------------------------------------- licensing
print("\n[3] Licensing")
ok, lic = licensing.check_license(HERE)
check("owner's own key still verifies", ok, lic if isinstance(lic, str) else lic.get("name"))
check("public key round-trips",
      licensing.public_key().public_bytes_raw().hex()
      == "e1468781965181d2f4824750da27782d9094e6d8cc60463c99c9ee09085f90a2")
check("plain key text absent from source",
      "e1468781965181" not in (HERE / "licensing.py").read_text(encoding="utf-8"))

legacy = licensing._parse_payload("Someone|2026-01-01")
check("2-field legacy key parses as perpetual FULL",
      legacy["expires"] == "" and legacy["tier"] == "FULL")
expired = licensing._parse_payload("X|2026-01-01|2020-01-01|TESTER|TT-1")
check("expiry field parses", expired["expires"] == "2020-01-01")

tmp = Path(tempfile.mkdtemp())
(tmp / "license.key").write_text("garbage.notasignature", encoding="utf-8")
bad_ok, _ = licensing.check_license(tmp)
check("malformed key is rejected", not bad_ok)
empty = Path(tempfile.mkdtemp())
none_ok, _ = licensing.check_license(empty)
check("missing key is rejected", not none_ok)

# -------------------------------------------------------------- integrity
print("\n[4] Integrity")
src_ok, note = integrity.verify(HERE, licensing.public_key())
check("source run skips integrity check", src_ok, note)

test_dir = Path(r"C:\Users\necko\SCVC TEST")
exe = test_dir / "StarCitizenVoiceControl.exe"
if exe.exists():
    e_ok, e_note = integrity.verify(test_dir, licensing.public_key(), exe_path=exe)
    check("packaged exe verifies against its integrity.sig", e_ok, e_note)
    fake = Path(tempfile.mkdtemp())
    (fake / "integrity.sig").write_text("AAAA", encoding="utf-8")
    f_ok, _ = integrity.verify(fake, licensing.public_key(), exe_path=exe)
    check("bad signature is rejected", not f_ok)
else:
    print("  [skip] no packaged exe on the Desktop to check")

# ------------------------------------------------------------- activation
print("\n[5] Activation")
L1 = {"name": "T", "issued": "2026-01-01", "expires": "", "tier": "TESTER", "copy_id": "A"}
L2 = dict(L1, copy_id="B")
p1 = "|".join([L1[k] for k in ("name", "issued", "expires", "tier", "copy_id")])
p2 = "|".join([L2[k] for k in ("name", "issued", "expires", "tier", "copy_id")])
check("different licenses get different record slugs",
      activation._slug(p1) != activation._slug(p2))
check("same license is stable across calls", activation._slug(p1) == activation._slug(p1))
check("machine fingerprint is readable", len(activation._machine_fingerprint()) > 0)
check("token differs per license", activation._token(p1) != activation._token(p2))

# ---------------------------------------------------------- keybind logic
print("\n[6] Star Citizen keybinds")
check("cloud drives excluded from scan",
      not any(str(d).upper().startswith("G") for d in sc_keybinds._scannable_drives()),
      str([str(d) for d in sc_keybinds._scannable_drives()]))
t0 = time.perf_counter()
found = sc_keybinds.find_actionmaps()
elapsed = time.perf_counter() - t0
check("scan completes inside its budget", elapsed < sc_keybinds.SCAN_BUDGET_S,
      f"{elapsed:.2f}s")
check("scan found an install", bool(found), str(found[0]) if found else "none")
check("hard timeout returns cleanly",
      sc_keybinds.find_actionmaps(budget_s=0.001) is None)

check("kb1_lalt+k -> ['altleft','k']",
      sc_keybinds.sc_input_to_keys("kb1_lalt+k") == ["altleft", "k"])
check("numpad translates", sc_keybinds.sc_input_to_keys("kb1_np_7") == ["num7"])
check("joystick input is not a key", sc_keybinds.sc_input_to_keys("js1_button4") is None)
check("cleared binding classified as unbound", sc_keybinds.classify("js1_ ") == "unbound")
check("joystick classified", sc_keybinds.classify("js2_button18") == "joystick")
check("keyboard classified", sc_keybinds.classify("kb1_v") == "keyboard")
check("mapping table covers most commands",
      len(set(sc_keybinds.COMMAND_TO_SC_ACTION) & set(by_id)) >= 40,
      f"{len(set(sc_keybinds.COMMAND_TO_SC_ACTION) & set(by_id))}/{len(by_id)}")
check("no mapping entries for commands that don't exist",
      not (set(sc_keybinds.COMMAND_TO_SC_ACTION) - set(by_id)))
if found:
    check("install path accepted at any level",
          all(sc_keybinds.actionmaps_under(p) for p in
              [found[0], found[0].parent, found[0].parents[3]]))

# A tester on STOCK keybinds reported "it didn't find my Star Citizen folder".
# Cause: Star Citizen only writes actionmaps.xml once you change a binding, so
# searching for that file reports "no install" for every default-keybind
# player -- wrong, alarming, and impossible for them to resolve. The install
# must be findable independently of whether any keybind was ever changed.
print("\n[6c] Install is found even with no keybind file")
_t0 = time.perf_counter()
_roots = sc_keybinds.find_install_roots()
_elapsed = time.perf_counter() - _t0
check("install scan finishes well inside its budget", _elapsed < 2.0, f"{_elapsed:.2f}s")
check("install found without needing actionmaps.xml", bool(_roots),
      str(_roots[0]) if _roots else "none")
if _roots:
    _live = _roots[0].parent
    check("install folder recognised at LIVE level", sc_keybinds.looks_like_install(_live))
    check("install folder recognised one level up",
          sc_keybinds.looks_like_install(_live.parent))
    check("install folder recognised two levels up",
          sc_keybinds.looks_like_install(_live.parent.parent))
check("a non-install folder is rejected",
      not sc_keybinds.looks_like_install(Path(r"C:\Windows")))

# Obly's rule, 2026-08-21: "only override if it finds a button in that slot."
# The shipped key must survive every case EXCEPT a real keyboard rebind --
# a cleared binding or one moved to a stick must not blank out our default,
# because then the command would send nothing at all.
print("\n[6b] Overrides only replace a key when the player has a real one")
import copy as _copy
_orig = {c["id"]: list(c.get("keys") or []) for c in commands}


def _keys_after(binds):
    cmds = _copy.deepcopy(commands)
    f, _ = sc_keybinds.audit(cmds, binds)
    sc_keybinds.apply_overrides(cmds, f)
    return {c["id"]: c.get("keys") for c in cmds}["headlights"]


check("cleared binding keeps our key",
      _keys_after({"v_lights": "js1_ "}) == _orig["headlights"])
check("joystick binding keeps our key",
      _keys_after({"v_lights": "js2_button7"}) == _orig["headlights"])
check("gamepad binding keeps our key",
      _keys_after({"v_lights": "gp1_a"}) == _orig["headlights"])
check("action absent from actionmaps keeps our key",
      _keys_after({}) == _orig["headlights"])
check("a real keyboard rebind DOES override",
      _keys_after({"v_lights": "kb1_lalt+j"}) == ["altleft", "j"])

# ------------------------------------------------------- push-to-talk
print("\n[7] Push-to-talk triggers")
check("XInput library loaded", joystick_ptt._xinput is not None)
check("unconfigured joystick reads as not-held",
      joystick_ptt.is_held(None, None) is False)
check("unconfigured gamepad reads as not-held",
      joystick_ptt.gamepad_is_held(None) is False)
check("nonsense gamepad button name is safe",
      joystick_ptt.gamepad_is_held("NOT_A_BUTTON") is False)
check("X is a known gamepad button", "X" in joystick_ptt.GAMEPAD_BUTTONS)
devs = joystick_ptt.devices()
print(f"        joysticks seen: {[(d, n.strip(), c) for d, n, c in devs] or 'none'}")
print(f"        gamepad connected: {joystick_ptt.gamepad_present()}")
check("joystick enumeration doesn't crash", isinstance(devs, list))
check("absent device reads as not-held", joystick_ptt.is_held(9, 1) is False)
check("pygame backend active", bool(joystick_ptt._init_pygame()))
check("both X56 halves enumerated", len(devs) >= 2 if devs else False,
      str([n for _, n, _ in devs]))
throttle = [d for d in devs if "throttle" in d[1].lower()]
check("throttle visible with >32 buttons (winmm could not do this)",
      bool(throttle) and throttle[0][2] > 32,
      f"{throttle[0][2]} buttons" if throttle else "no throttle")
check("unknown device name resolves to not-held",
      joystick_ptt.is_held(None, 4, "No Such Device") is False)
# Deliberately NOT asserting that a specific button reads as held -- an
# earlier version checked throttle button 34, which is a latched switch, and
# the test broke the moment that switch got flipped. A self-test must not
# depend on the physical position of hardware.
check("button state query returns a bool, not an error",
      isinstance(joystick_ptt.is_held(None, 34, "X56 H.O.T.A.S. Throttle"), bool)
      if throttle else True)
check("out-of-range button is safe",
      joystick_ptt.is_held(None, 999, "X56 H.O.T.A.S. Throttle") is False
      if throttle else True)
check("pygame banner suppressed",
      "PYGAME_HIDE_SUPPORT_PROMPT" in Path("joystick_ptt.py").read_text(encoding="utf-8"))

# --------------------------------------------------------------- first run
print("\n[8] First run")
fr = Path(tempfile.mkdtemp())
check("fresh folder reports not-yet-run", not first_run.already_ran(fr))
note = first_run._write_note(fr, ["  [X] example: on your joystick"], "WATERMARK-HERE")
body = note.read_text(encoding="utf-8")
check("note is written", note.exists())
check("note carries the watermark", "WATERMARK-HERE" in body)
check("note includes the keybind findings", "example: on your joystick" in body)
check("note explains the [X] marker", "[X]" in body)

# -------------------------------------------------------------- build stamp
print("\n[9] Build stamp")
banner = build_info.banner(
    {"name": "Tester", "tier": "TESTER", "issued": "2026-08-21", "expires": ""})
check("banner renders", "STAR CITIZEN VOICE CONTROL" in banner)
check("the banner names the author", "Obly" in banner)
check("source tree left unstamped (DEV)", build_info.CHANNEL == "DEV",
      build_info.CHANNEL)

# ------------------------------------------- reference poster cannot drift
print("")
print("[10] Printable reference is in sync")
import subprocess
try:
    _r = subprocess.run([sys.executable, os.path.join("tools", "make_reference.py"),
                         "--check"], capture_output=True, text=True)
    _out = (_r.stdout or _r.stderr).strip()
    _last = _out.splitlines()[-1] if _out else ""
    check("reference matches commands.json", _r.returncode == 0, _last)
except Exception as _e:
    check("reference matches commands.json", False, str(_e))

# the phrase grammar must never silently lose a phrase
import phrase_grammar
_copy = json.loads(json.dumps(commands))
_b, _a = phrase_grammar.expand_commands(_copy)
check("phrase grammar expands cleanly", _a >= _b,
      str(_b) + " written -> " + str(_a) + " recognised")
check("every command still has phrases",
      all(c["phrases"] for c in _copy),
      str(sum(len(c["phrases"]) for c in _copy)) + " total")

# ------------------------------------------------------------------ result
print("\n" + "=" * 70)
print(f"  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print(f"    FAILED: {f}")
print("=" * 70)
sys.exit(1 if FAIL else 0)
