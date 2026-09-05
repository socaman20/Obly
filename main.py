"""
Star Citizen voice command router.

Hold the push-to-talk key, speak a command, release. The phrase is
transcribed locally (faster-whisper), fuzzy-matched against
config/commands.json, and replayed into Star Citizen as keystrokes.

Only sends keys when Star Citizen is the focused window (see
settings.require_focused_window in commands.json) so this can't leak
keystrokes into chat, Discord, etc.

(A hands-free "wake word" mode was prototyped and deliberately shelved
for this version -- see git history / conversation notes if picking
that back up later. PTT-only for now.)
"""

import json
import os
import tempfile
import queue
import re
import sys
import time
import ctypes
import ctypes.wintypes
import winsound
from pathlib import Path

import keyboard
import numpy as np
import pydirectinput
import sounddevice as sd
import win32gui
from faster_whisper import WhisperModel
from rapidfuzz import fuzz

import build_info
import first_run
import joystick_ptt
import phonetic
import sc_keybinds
import control_scheme
import phrase_grammar

# When frozen into an exe by PyInstaller, __file__ resolves inside a
# temp extraction folder, not next to the exe -- config/, whisper_model/,
# and voice_acks/ need to be found next to the actual exe on disk so
# they stay visible and editable, not buried in a temp dir.
BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "commands.json"
WHISPER_MODEL_ROOT = BASE_DIR / "whisper_model"
VOICE_ACKS_DIR = BASE_DIR / "voice_acks"
pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: could not find {CONFIG_PATH}")
        print("Make sure the 'config' folder is sitting right next to this program.")
        input("Press Enter to close...")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: commands.json has a typo and isn't valid JSON: {e}")
        print(f"Open {CONFIG_PATH} in Notepad, go to line {e.lineno}, and check for a")
        print("missing comma, missing quote, or missing bracket near there.")
        input("Press Enter to close...")
        sys.exit(1)

    # Expand the phrase grammar -- "[open;bring up] mobiglas" becomes every
    # spoken variant. A phrase with no brackets comes back unchanged, so
    # everything authored before this existed still works untouched.
    try:
        before, after = phrase_grammar.expand_commands(config.get("commands", []))
        if after > before:
            print(f"  Phrases   : {before} written -> {after} recognised")
    except phrase_grammar.GrammarError as e:
        print(f"ERROR: a phrase in commands.json is malformed.")
        print(f"  {e}")
        print("Brackets group alternatives, like [open;bring up] mobiglas.")
        print("Every '[' needs a matching ']'.")
        input("Press Enter to close...")
        sys.exit(1)

    # Layer 3: what actually gets pressed. Bindings live in
    # config/schemes/<name>.json, never in commands.json, so one phrase set
    # can serve many physical layouts.
    scheme_name = config.get("settings", {}).get(
        "control_scheme", control_scheme.DEFAULT_SCHEME)
    try:
        bindings = control_scheme.load(BASE_DIR, scheme_name)
    except control_scheme.SchemeError as e:
        print("ERROR: " + str(e))
        input("Press Enter to close...")
        sys.exit(1)

    unbound = control_scheme.apply(config["commands"], bindings, scheme_name)
    others = [n for n in control_scheme.available(BASE_DIR) if n != scheme_name]
    print(f"  Controls  : {scheme_name}" +
          (f"  (also available: {', '.join(others)})" if others else ""))
    if unbound:
        # Honest answer, not a silent failure: this layout has no input for
        # these, so they are dropped rather than half-firing.
        print(f"  {len(unbound)} command(s) unbound on this layout and disabled:")
        print("    " + ", ".join(unbound))
        config["commands"] = [c for c in config["commands"]
                              if not c.get("_unbound")]

    return config


def foreground_window_title():
    hwnd = win32gui.GetForegroundWindow()
    return win32gui.GetWindowText(hwnd)


# pyttsx3 only ever speaks when a command has no pre-rendered clip, but
# initialising it eagerly costs ~22 MB of the process's ~174 MB idle
# footprint. Star Citizen wants every megabyte, so load it on first
# actual need and never at all in the normal case.
_tts_engine = None


def _fallback_tts():
    global _tts_engine
    if _tts_engine is None:
        import pyttsx3
        _tts_engine = pyttsx3.init()
    return _tts_engine


# Which voice pack is selected. Set from settings.voice_pack at startup.
# "" means the flat voice_acks/ folder -- the layout every build before
# packs existed used, so old installs keep working untouched.
_voice_pack = ""


def set_voice_pack(name):
    """Point playback at voice_acks/<name>/. Falls back if it isn't there."""
    global _voice_pack
    name = (name or "").strip()
    if name and not (VOICE_ACKS_DIR / name).is_dir():
        print(f"  Voice pack: '{name}' not found, using the default voice")
        name = ""
    _voice_pack = name
    return name


def available_voice_packs():
    """Every subfolder of voice_acks/ that actually contains clips."""
    if not VOICE_ACKS_DIR.is_dir():
        return []
    return sorted(d.name for d in VOICE_ACKS_DIR.iterdir()
                  if d.is_dir() and any(d.glob("*.wav")))


def ack_clip(cmd_id):
    """Selected pack first, then the default folder. None if neither has it."""
    if _voice_pack:
        packed = VOICE_ACKS_DIR / _voice_pack / f"{cmd_id}.wav"
        if packed.exists():
            return packed
    flat = VOICE_ACKS_DIR / f"{cmd_id}.wav"
    return flat if flat.exists() else None


# Global switch for the robot-voice fallback. Set from settings at startup.
# Testers asked for some commands not to talk back; without this, "no clip
# recorded yet" and "meant to stay quiet" were the same state and BOTH came
# out as pyttsx3. Silence is now something you can actually choose.
_fallback_tts_enabled = True


def set_fallback_tts(enabled):
    global _fallback_tts_enabled
    _fallback_tts_enabled = bool(enabled)


def speak(cmd_id, text, silent=False):
    # A command marked "silent": true never makes a sound -- not a clip,
    # not TTS. It still prints, so the log shows it fired.
    if silent:
        print(f"[computer] ({cmd_id} - silent by choice)")
        return
    if not (text or "").strip():
        return
    print(f"[computer] {text}")
    clip = ack_clip(cmd_id)
    if clip:
        # SND_ASYNC so the ack plays *over* the next command instead of
        # blocking the loop until Raina finishes talking -- holding PTT
        # again mid-ack used to have to wait out the clip.
        winsound.PlaySound(str(clip), winsound.SND_FILENAME | winsound.SND_ASYNC)
    elif _fallback_tts_enabled:
        engine = _fallback_tts()
        engine.say(text)
        engine.runAndWait()


def press_combo(keys, hold_ms=50):
    for k in keys:
        pydirectinput.keyDown(k)
    time.sleep(hold_ms / 1000.0)
    for k in reversed(keys):
        pydirectinput.keyUp(k)


def type_text(text):
    pydirectinput.write(text, interval=0.02)


# --- clipboard paste -------------------------------------------------------
# HCS/VoiceAttack solve destination entry by pasting rather than typing: their
# Elite profile has "plot a course to my clipboard" for exactly this reason.
# pydirectinput.write() sends one synthetic keystroke per character and games
# drop those in menus, so a long name is a long list of chances to fail.
# A paste is a single event.
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# ctypes assumes an int return unless told otherwise. On 64-bit Windows these
# return handles and pointers, so without these declarations the top 32 bits
# are discarded, GlobalLock gets a bad handle, and reading through it takes the
# whole process down with no traceback at all.
_u32 = ctypes.windll.user32
_k32 = ctypes.windll.kernel32
_u32.OpenClipboard.argtypes = [ctypes.c_void_p]
_u32.OpenClipboard.restype = ctypes.c_int
_u32.CloseClipboard.restype = ctypes.c_int
_u32.EmptyClipboard.restype = ctypes.c_int
_u32.GetClipboardData.argtypes = [ctypes.c_uint]
_u32.GetClipboardData.restype = ctypes.c_void_p
_u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
_u32.SetClipboardData.restype = ctypes.c_void_p
_k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
_k32.GlobalAlloc.restype = ctypes.c_void_p
_k32.GlobalLock.argtypes = [ctypes.c_void_p]
_k32.GlobalLock.restype = ctypes.c_void_p
_k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
_k32.GlobalUnlock.restype = ctypes.c_int


def _clipboard_get():
    """Whatever is on the clipboard now, so we can put it back afterwards."""
    try:
        if not _open_clipboard(tries=8):
            return None
        try:
            h = _u32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return None
            p = _k32.GlobalLock(h)
            if not p:
                return None
            try:
                return ctypes.c_wchar_p(p).value
            finally:
                _k32.GlobalUnlock(h)
        finally:
            _u32.CloseClipboard()
    except Exception:
        return None


def _open_clipboard(tries=20, gap_s=0.025):
    """Take the clipboard lock, waiting for whoever else has it.

    Only ONE process on the machine may hold the clipboard at a time, and
    OpenClipboard fails outright rather than queueing. Discord, OBS and
    Windows' own clipboard-history service all grab it briefly and often, so a
    single attempt loses the race regularly -- which is exactly the "it
    clicked but never typed" failure: the paste silently did nothing and the
    macro carried on. Half a second of retries turns a coin flip into a
    near-certainty, and costs nothing when the clipboard is free.
    """
    for _ in range(tries):
        if _u32.OpenClipboard(None):
            return True
        time.sleep(gap_s)
    return False


def _clipboard_set(text, verify=True):
    """Put text on the clipboard. Returns False rather than raising.

    Reads back what landed: SetClipboardData can report success and still lose
    to another process writing a moment later. Failing loudly here lets the
    caller fall back while there is still time to.
    """
    data = str(text)
    for attempt in (1, 2):
        try:
            buf = ctypes.create_unicode_buffer(data)
            size = ctypes.sizeof(buf)
            h = _k32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not h:
                continue
            p = _k32.GlobalLock(h)
            if not p:
                continue
            ctypes.memmove(p, buf, size)
            _k32.GlobalUnlock(h)
            if not _open_clipboard():
                print("  clipboard is held by another program "
                      "(Discord, OBS and clipboard history all do this)")
                continue
            try:
                _u32.EmptyClipboard()
                # Windows owns the block once SetClipboardData succeeds --
                # do not free it here.
                ok = bool(_u32.SetClipboardData(CF_UNICODETEXT, h))
            finally:
                _u32.CloseClipboard()
            if not ok:
                continue
            if not verify:
                return True
            time.sleep(0.02)
            if _clipboard_get() == data:
                return True
            print(f"  clipboard did not hold on attempt {attempt}, retrying")
        except Exception as exc:
            print(f"  clipboard error: {exc}")
    return False


# --- our own copy of the route ---------------------------------------------
# Star Citizen drops the route when you log out, and its map can glitch. Every
# plot is written here with the jump path, so the leg is still readable on our
# side even when the game has forgotten it.
def record_route(spoken, resolved, note):
    path = BASE_DIR / "config" / "current_route.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = {"_readme": "Routes plotted by voice. The game forgets these; "
                          "this file does not. Safe to delete.",
               "legs": []}

    place = next((p for p in load_places() if p["n"] == resolved), {})
    doc["legs"] = (doc.get("legs") or [])[-49:] + [{
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "heard": spoken,
        "destination": resolved,
        "kind": place.get("k", ""),
        "in": place.get("in", ""),
        "live": place.get("live", None),
        "note": note,
    }]
    doc["current"] = doc["legs"][-1]
    try:
        folder = os.path.dirname(str(path))
        fd, tmp = tempfile.mkstemp(prefix=".route.", suffix=".tmp", dir=folder)
        with open(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except OSError:
        pass


# --- destination resolving -------------------------------------------------
# The map knows every real place name; the recogniser does not. Correcting the
# spoken name before it reaches the game is the step VoiceAttack's clipboard
# command cannot do -- theirs pastes whatever it is given.
_PLACES = None


def load_places():
    """Every destination the game knows. Missing file is not fatal."""
    global _PLACES
    if _PLACES is not None:
        return _PLACES
    path = BASE_DIR / "config" / "places.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            _PLACES = (json.load(f) or {}).get("places", [])
    except (OSError, ValueError):
        _PLACES = []
    return _PLACES


_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_digits(text):
    """'area eighteen' -> 'area 18'.

    Whisper writes numbers as words about as often as digits, and a great many
    place names in this game end in one -- Area 18, ArcCorp Mining Area 045,
    HUR-L2. Without this the match rests on the fuzzy score alone, and
    "eighteen" against "18" scores far too low to survive. Handles nought to
    ninety-nine, which covers every numbered place in the index.
    """
    out, words = [], (text or "").lower().split()
    i = 0
    while i < len(words):
        w = words[i].strip(".,")
        if w in _TENS:
            n = _TENS[w]
            nxt = words[i + 1].strip(".,") if i + 1 < len(words) else ""
            if nxt in _ONES and 1 <= _ONES[nxt] <= 9:
                n += _ONES[nxt]
                i += 1
            out.append(str(n))
        elif w in _ONES:
            out.append(str(_ONES[w]))
        else:
            out.append(words[i])
        i += 1
    return " ".join(out)


def _score_places(spoken, places):
    """Best match in `places`, as (place, score, runner_up_score).

    The runner-up matters as much as the winner. Whisper mangles proper nouns,
    so a real destination often lands in the sixties -- "new beverage" scores
    69.6 against New Babbage. On the absolute number that is a miss; next to a
    runner-up on 50 it is obviously the right answer. A wide margin is the
    evidence that there was only ever one candidate.
    """
    squash = lambda t: "".join(ch for ch in t.lower() if ch.isalnum())
    # Score against both what was said and its numbers-as-digits form, and
    # keep the better of the two. "Area 18" wins on the digits; a name that
    # happens to contain a number word wins on the original.
    wants = {spoken.lower(), words_to_digits(spoken)}
    tights = {squash(w) for w in wants}
    _best_want = spoken.lower()          # phonetics run on what was actually said

    best, best_score, second = None, 0, 0
    for p in places:
        name = p["n"]
        # Score against the bare name too. "Terra Gateway (Stanton)" is our
        # label, not the game's: the suffix exists so two Gateways can be told
        # apart on the map, and it was quietly costing 24 points -- "terror
        # gateway" scored 64.9 against the full string and 88.9 against the
        # real name, which is the difference between working and refused.
        forms = {name.lower()}
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip().lower()
        if bare:
            forms.add(bare)
        # Jump points are named for both ends -- "Stanton - Terra". Say either
        # end and you have named the jump point, so each side is a form in its
        # own right. Without this, "terra" lost to the moon Vatra on raw
        # letters, when the live thing he can actually fly to is the Terra
        # jump point. Ends are only added when there are exactly two, so a
        # hyphenated place name is not chopped up.
        halves = set()
        if p.get("k") == "jump point" and bare.count("-") == 1:
            for half in bare.split("-"):
                half = half.strip()
                if len(half) >= 3:
                    halves.add(half)
        low = min(forms, key=len) if len(forms) > 1 else name.lower()
        if low in wants or squash(name) in tights:
            score = 100                       # exact, ignoring spacing/case
        elif any(h in wants for h in halves):
            # Half of a jump point's name is half an answer. It should win
            # when nothing else fits -- "terra" has no live Terra, so the
            # Terra jump point is the useful reply -- but never beat a place
            # actually called that. Say "Pyro" and you mean the system, not
            # the Nyx-Pyro jump point.
            score = 92
        else:
            score = max(max(fuzz.ratio(w, f), fuzz.token_sort_ratio(w, f))
                        for w in wants for f in (forms | halves))
            # How it SOUNDS, not how it is spelled. These names are not
            # English, so Whisper keeps the sound and loses the letters:
            # "art court" for ArcCorp, "origin" for Orison.
            #
            # But sound alone is dangerous, and measurably so. Letting it set
            # the score outright accepted "what time is it" as HDMS-Hadley
            # (sound 80) and "power to weapons" as Pyro Gateway (sound 75),
            # because unrelated words collide once you throw the vowels away.
            # So sound only PROMOTES a candidate that already looks alike --
            # it never creates one. Measured on his own transcripts, every
            # true match scored 62-89 on characters and every false one
            # 23-56, which is where the gate sits. The lift is capped so a
            # near-miss cannot leapfrog an exact spelling.
            if len(low) >= 4 and score >= 60:
                try:
                    heard = phonetic.similarity(_best_want, low)
                    score = max(score, min(heard, score + 15))
                except Exception:
                    pass
            # A prefix is strong evidence only when there is enough of it.
            # Without this guard the two-letter planet "Lo" scored 88 against
            # "lorval" purely because the word starts with those letters, and
            # beat Lorville. The shorter side has to be at least four
            # characters and half the longer one before a prefix counts.
            for w in wants:
                if not w or not low:
                    continue
                short, long_ = (w, low) if len(w) <= len(low) else (low, w)
                if len(short) >= 4 and len(short) * 2 >= len(long_)                         and long_.startswith(short):
                    score = max(score, 88)
                    break
        if score > best_score:
            # Only a genuinely different place counts as the runner-up: a
            # moon and the outpost on it can share a name, and that is not
            # competition, it is the same answer twice.
            if best is not None and best["n"].lower() != p["n"].lower():
                second = best_score
            best, best_score = p, score
        elif score > second and (best is None
                                 or best["n"].lower() != p["n"].lower()):
            second = score
    return best, best_score, second


def _confident(score, second):
    """Is this match trustworthy? Either strong, or unopposed."""
    return score >= 70 or (score >= 58 and score - second >= 12)


def resolve_destination(spoken, live_only=False):
    """Best real destination for what was heard. Returns (name, note).

    `live_only` is for the one caller that types into the game. The map wants
    every announced place and greys out what you cannot reach; the game's
    search box has never heard of them, so typing one finds nothing and says
    nothing.

    The subtlety is that filtering to live places alone makes the fuzzy match
    reach: ask for "Terra", a system that is not in the build, and the nearest
    live name is "Terra Mills HydroFarm" -- a real place, on the wrong planet,
    that you never asked for. Flying somewhere you did not choose is worse
    than being told no. So both sets are scored, and when the best answer
    overall is a place that is not in this build, that is what you are told.
    """
    spoken = (spoken or "").strip()
    if not spoken:
        return "", "nothing heard"
    places = load_places()
    if not places:
        return spoken, "no place list; pasting what was heard"

    def describe(p):
        note = "%s in %s" % (p["k"], p["in"]) if p["in"] else p["k"]
        return note if p.get("live") else note + " - not in this build"

    if not live_only:
        best, score, second = _score_places(spoken, places)
        if best and _confident(score, second):
            return best["n"], describe(best)
        return spoken, "no match; pasting what was heard"

    live = [p for p in places if p.get("live")]
    live_best, live_score, live_second = _score_places(spoken, live)
    any_best, any_score, any_second = _score_places(spoken, places)

    # Something that is not in the build fits noticeably better than anything
    # that is: he named a real place we simply cannot fly to yet.
    # Say "that is not in this build" only when there is no decent live
    # alternative. Otherwise the better letter-match wins over the place he
    # can actually reach: "origin" looks more like Orion (85.7, a system we
    # cannot fly to) than Orison (75.0, a city we can), and reporting Orion
    # helps nobody. A live match that stands on its own is always the more
    # useful answer.
    if (any_best and not any_best.get("live")
            and _confident(any_score, any_second)
            and any_score > live_score + 6
            and live_score < 70):
        return "", "%s is %s" % (any_best["n"], describe(any_best))

    if live_best and _confident(live_score, live_second):
        return live_best["n"], describe(live_best)
    return "", "no match in the live build"


_SEARCH_NAMES = None


def game_search_name(name):
    """What to actually type into Star Citizen's search box for `name`.

    The map's name and the game's search string are not always the same
    string -- Area 18 is written Area18 in there. Pasting the pretty name
    finds nothing and says nothing, so the mismatch has to live somewhere
    explicit rather than being discovered mid-flight.
    """
    global _SEARCH_NAMES
    if _SEARCH_NAMES is None:
        try:
            with open(BASE_DIR / "config" / "search_names.json", "r",
                      encoding="utf-8") as f:
                _SEARCH_NAMES = (json.load(f) or {}).get("names", {})
        except (OSError, ValueError):
            _SEARCH_NAMES = {}
    if name in _SEARCH_NAMES:
        return _SEARCH_NAMES[name]
    # Case-insensitive fallback, so a lowercase entry still matches.
    for k, v in _SEARCH_NAMES.items():
        if k.lower() == (name or "").lower():
            return v

    # A trailing parenthetical is ours, not the game's. Four stations are all
    # called some flavour of Gateway and only differ by which system they sit
    # in, so the index disambiguates them -- "Pyro Gateway (Nyx)" -- to keep
    # them apart on the map and in a route list. The game's search box has
    # never heard that suffix; it wants "Pyro Gateway". Strip it on the way
    # out and the two names stay right for their own audience.
    trimmed = re.sub(r"\s*\([^)]*\)\s*$", "", name or "").strip()
    return trimmed or name


def paste_text(text):
    """Put `text` on the clipboard, Ctrl+V it, then restore what was there.

    This is how HCS/VoiceAttack enter a destination in Elite ("plot a course to
    my clipboard"). One paste beats one synthetic keystroke per character,
    because games drop synthetic keystrokes in menus.
    """
    if not text:
        return False
    keep = _clipboard_get()
    if not _clipboard_set(text):
        # Typing it out is the fallback, but games drop synthetic keystrokes
        # in menus, so it often does nothing either. The caller is told it
        # failed rather than left to assume.
        print("  clipboard unavailable, trying to type it instead")
        type_text(text)
        return False
    time.sleep(0.08)                  # let the game notice the clipboard
    pydirectinput.keyDown("ctrl")
    pydirectinput.press("v")
    pydirectinput.keyUp("ctrl")
    time.sleep(0.12)
    if keep is not None:
        _clipboard_set(keep, verify=False)   # their clipboard is not ours to keep
    return True


def mouse_hold(button, hold_ms):
    pydirectinput.mouseDown(button=button)
    time.sleep(hold_ms / 1000.0)
    pydirectinput.mouseUp(button=button)


def click_at(fx, fy):
    """Click a point given as a FRACTION of the game window, not pixels.

    Star Citizen's starmap is a mouse-driven UI: unlike Elite's galaxy map,
    there is no "next panel / accept" pair that walks focus into the search
    field, so the only way to put the caret in the box is to click it. Storing
    the position as a fraction rather than pixels means one calibration
    survives a resolution change, a windowed/fullscreen switch and a second
    monitor.
    """
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
        pt = ctypes.wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return False
        x = int(pt.x + w * float(fx))
        y = int(pt.y + h * float(fy))
    except Exception:
        return False

    # SetCursorPos + a real button event: the game reads raw mouse input, and
    # a synthetic move without a click does not place the caret.
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)   # left down
    time.sleep(0.03)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)   # left up
    print(f"  clicked {fx:.3f},{fy:.3f} of the game window -> {x},{y}")
    return True


def run_steps(steps, destination, default_wait_ms, report=None):
    """Run a macro, saying what each step did.

    A macro that half-works is the worst thing to debug: the click lands, the
    paste silently does nothing, Enter fires into an empty box, and all you
    can say afterwards is "sometimes it works". Every step now reports whether
    it did its job, so an intermittent failure names itself instead of having
    to be reproduced.

    Returns True only if every step ran.
    """
    total = len(steps)

    def done(i, action, ok=True, why=""):
        print("  %s step %d/%d: %s%s" % (" " if ok else "!", i, total, action,
                                         (" -- " + why) if why else ""))
        if report:
            try:
                report("step", {"i": i, "of": total, "action": action,
                                "ok": bool(ok), "why": why})
            except Exception:
                pass

    for i, step in enumerate(steps, 1):
        action = step["action"]

        if action == "keypress":
            press_combo(step["keys"])
            done(i, "press " + "+".join(step["keys"]))

        elif action == "keyhold":
            press_combo(step["keys"], step.get("hold_ms", 1500))
            done(i, "hold " + "+".join(step["keys"]))

        elif action == "mousehold":
            mouse_hold(step["button"], step.get("hold_ms", 1500))
            done(i, "hold mouse " + str(step["button"]))

        elif action == "click":
            if step.get("x") is None or step.get("y") is None:
                done(i, "click", False, "not calibrated, skipped")
            else:
                ok = click_at(step["x"], step["y"])
                done(i, "click", ok,
                     "" if ok else "could not measure the game window")

        elif action == "type":
            type_text(destination if step.get("source") == "destination"
                      else step.get("text", ""))
            done(i, "type")

        elif action == "paste":
            if step.get("source") == "destination":
                target, note = resolve_destination(destination, live_only=True)
                if not target:
                    # The resolver refused; `note` already says why, either
                    # "that place is not in this build" or nothing matched.
                    print("  '%s': %s -- nothing was typed" % (destination, note))
                    speak("plot_route_to", note if "not in this build" in note
                          else "I don't know anywhere called %s." % destination)
                    done(i, "paste", False, note)
                    return False
                if target != destination:
                    print("  heard '%s' -> %s  (%s)" % (destination, target, note))
                else:
                    print("  destination: %s  (%s)" % (target, note))
                record_route(destination, target, note)
                typed = game_search_name(target)
                if typed != target:
                    print("  typing '%s' -- that is how the game spells it" % typed)
                ok = paste_text(typed)
                done(i, "paste", ok, typed if ok
                     else "clipboard would not take it, nothing was typed")
                if not ok:
                    # Enter on an empty box selects whatever was already
                    # showing. Stopping is the safe failure.
                    return False
            else:
                ok = paste_text(step.get("text", ""))
                done(i, "paste", ok)
                if not ok:
                    return False

        elif action == "wait":
            done(i, "wait")

        time.sleep(step.get("wait_ms", default_wait_ms) / 1000.0)

    return True


def build_matchers(commands):
    """Split commands into plain-phrase matchers and wildcard (prefix-capture) matchers."""
    plain, wildcard = [], []
    for cmd in commands:
        for phrase in cmd["phrases"]:
            if "*" in phrase:
                prefix = phrase.split("*")[0].strip()
                wildcard.append((prefix, cmd))
            else:
                plain.append((phrase, cmd))
    return plain, wildcard


def match_command(text, plain, wildcard, threshold):
    text = text.lower().strip().strip(".").strip()

    # Wildcard (e.g. "route to *") checked first via prefix containment,
    # since the tail is arbitrary destination text rapidfuzz shouldn't score.
    best_wc, best_wc_score, best_wc_dest = None, 0, ""
    for prefix, cmd in wildcard:
        if prefix in text:
            idx = text.index(prefix) + len(prefix)
            dest = text[idx:].strip()
            if dest:
                score = fuzz.partial_ratio(prefix, text)
                if score > best_wc_score:
                    best_wc, best_wc_score, best_wc_dest = cmd, score, dest

    best_plain, best_plain_score, best_plain_threshold = None, 0, threshold
    for phrase, cmd in plain:
        # A command marked "strict" is scored on ratio ALONE. token_set_ratio
        # returns 100 whenever the spoken words are a SUBSET of the phrase, so
        # "jump point" scores ~97 against "activate jump point" and fires it --
        # deleting the short phrase from the list doesn't help, because the
        # fuzzy match recreates it. Dropping token_set_ratio is what actually
        # makes the full phrase required. Use it for commands that are
        # expensive to trigger by accident.
        if cmd.get("strict"):
            score = fuzz.ratio(phrase, text)
        else:
            # ratio catches phonetic misheard-word substitutions (e.g. Whisper's
            # "now have mode" for "nav mode"); token_set_ratio catches repeated
            # phrases (e.g. "toggle flight ready. toggle flight ready."). Neither
            # alone covers both, so take the best of the two.
            score = max(fuzz.ratio(phrase, text), fuzz.token_set_ratio(phrase, text))
        # token_set_ratio treats a short phrase as a near-perfect match
        # whenever it's a subset of a longer transcript, regardless of
        # qualifying words -- e.g. toggle's "power to weapons" vs "increase
        # power to weapons". Penalize by word-count difference so a longer,
        # more complete phrase match (the actual "increase power to
        # weapons" phrase) wins over a shorter generic one that just
        # happens to be a substring.
        word_diff = abs(len(phrase.split()) - len(text.split()))
        score -= word_diff * 3
        if score > best_plain_score:
            best_plain, best_plain_score = cmd, score
            # Per-command floor, so one risky command can demand more
            # confidence without making every command fussy.
            best_plain_threshold = cmd.get("match_threshold", threshold)

    if best_wc_score >= threshold and best_wc_score >= best_plain_score:
        return best_wc, {"destination": best_wc_dest}
    if best_plain_score >= best_plain_threshold:
        return best_plain, {}
    return None, {}


# Biases Whisper's decoding toward this game's actual vocabulary --
# short and natural-reading on purpose (a long list of every phrase
# would dilute the effect rather than help). Costs nothing in speed.
_VOCAB_BASE = (
    "Star Citizen ship voice commands: quantum drive, nav mode, master mode, "
    "landing gear, VTOL, mobiGlas, headlights, flight ready, power to weapons, "
    "power to shields, power to thrusters, engines, hail target, scuttle the ship, "
    "self destruct, exit seat, disembark, backspace, cut all power, "
    "visor wipe, port lock."
)

_VOCAB = None


def vocab_prompt():
    """The recogniser's hint list, including the places you can fly to.

    Whisper leans on this prompt when a word is ambiguous, and these names are
    not English -- left to itself it produced "new beverage" for New Babbage.
    Correcting that afterwards works, but priming it means the mistake is
    never made. Only live places go in: a prompt listing hundreds of
    unreachable systems would bias it toward words that cannot be destinations.
    """
    global _VOCAB
    if _VOCAB is not None:
        return _VOCAB
    names = []
    try:
        import gamedex
        names = gamedex.vocabulary()      # live places, ships and commodities
    except Exception:
        try:
            for pl in load_places():
                if pl.get("live") and pl["k"] in ("system", "planet", "moon",
                                                  "city", "station"):
                    names.append(pl["n"])
        except Exception:
            names = []
    # Cities and planets first: they are what people actually say.
    names.sort(key=lambda n: len(n))
    # These are the words that must beat ordinary English. Whisper writes
    # "new beverage" and "art court" unless it is told that New Babbage and
    # ArcCorp are things people say.
    _VOCAB = _VOCAB_BASE + " In-game names: " + ", ".join(names[:200]) + "."
    return _VOCAB


VOCAB_PROMPT = _VOCAB_BASE          # kept: other code imports this name


def transcribe(model, audio):
    segments, _ = model.transcribe(
        audio, language="en", beam_size=1, initial_prompt=vocab_prompt()
    )
    return " ".join(seg.text for seg in segments).strip()


def process_command(model, plain, wildcard, settings, audio, report=None):
    """Transcribe, check focus, match, execute, speak the ack.

    `report(kind, detail)` is optional and additive: the console keeps printing
    exactly what it always printed, and a window can subscribe to the same
    moments instead of scraping stdout. Kinds are "heard", "blocked",
    "nomatch" and "fired".
    """
    def say(kind, **detail):
        if report:
            try:
                report(kind, detail)
            except Exception:
                pass          # a broken listener must never stop a command

    text = transcribe(model, audio)
    if not text:
        print("(heard nothing)")
        say("heard", text="", matched=False)
        return
    print(f'heard: "{text}"')
    say("heard", text=text)

    cmd, slots = match_command(text, plain, wildcard, settings["match_threshold"])

    # Answering a question is not the same as pressing a key. The focus rule
    # exists so a command cannot fire into Discord; a lookup sends nothing, so
    # it is allowed to work with the app in front -- which is exactly when you
    # want to ask what iron is going for.
    if cmd is not None and cmd["type"] == "lookup":
        term = (slots.get("destination") or "").strip()
        try:
            import gamedex
            hits = gamedex.look_up(term, limit=5)
        except Exception as exc:
            print(f"  lookup failed: {exc}")
            hits = []
        if hits:
            top = hits[0]
            print(f"  {term!r} -> {top['n']}  ({top['detail']})")
            for h in hits[1:]:
                print(f"       also {h['n']}  ({h['detail']})")
            speak("look_up", f"{top['n']}. {top['detail']}.")
        else:
            print(f"  nothing in the game called {term!r}")
            speak("look_up", f"I can't find anything called {term}.")
        say("lookup", text=text, term=term, hits=hits)
        return

    if settings["require_focused_window"]:
        title = foreground_window_title()
        if settings["target_window_title"].lower() not in title.lower():
            print(f"(Star Citizen not focused -- current window: '{title}', ignoring)")
            say("blocked", text=text, window=title)
            return

    if cmd is None:
        print("(no matching command)")
        say("nomatch", text=text)
        return

    print(f"-> {cmd['id']}")
    say("fired", text=text, id=cmd["id"],
        name=cmd.get("display_name") or cmd["id"],
        keys=cmd.get("keys") or [], key_label=cmd.get("key_label", ""),
        action=cmd["type"], destination=slots.get("destination", ""))
    if cmd["type"] == "keypress":
        press_combo(cmd["keys"])
    elif cmd["type"] == "keyhold":
        press_combo(cmd["keys"], cmd.get("hold_ms", 1500))
    elif cmd["type"] == "mousehold":
        mouse_hold(cmd["button"], cmd.get("hold_ms", 1500))
    elif cmd["type"] in ("route", "macro"):
        run_steps(cmd["steps"], slots.get("destination", ""),
                  settings["default_step_wait_ms"], report=report)

    ack = cmd.get("ack", "").format(**slots)
    if cmd.get("silent"):
        speak(cmd["id"], "", silent=True)
    elif ack:
        speak(cmd["id"], ack)


def main():
    # No licence check, no activation lock, no tamper hard-stop. This is a
    # free release: those existed to keep a paid product from being copied,
    # and there is nothing here worth copy-protecting any more. Removed
    # rather than disabled, so nobody has to wonder whether a flag re-arms
    # them.
    print(build_info.banner())

    config = load_config()
    settings = config["settings"]

    # Voice pack. Empty = the default voice in voice_acks/. A pack is just a
    # subfolder of .wav files named <command_id>.wav, so making one is
    # filling a folder -- no code, no rebuild, no API key at runtime.
    set_fallback_tts(settings.get("fallback_tts", True))
    chosen = set_voice_pack(settings.get("voice_pack", ""))
    packs = available_voice_packs()
    if packs:
        print(f"  Voice pack: {chosen or 'default'}  (available: {', '.join(packs)})")
    commands = config["commands"]
    plain, wildcard = build_matchers(commands)

    # "Set HOTAS Button.bat" runs us with this flag. Capture a stick button
    # and write it into commands.json, so the player never has to work out a
    # device id or button number by hand.
    if "--setup-ptt" in sys.argv:
        print("SET A HOTAS BUTTON FOR PUSH-TO-TALK")
        print("=" * 62)
        print(f"Your keyboard key ('{settings['ptt_key']}') keeps working either way.")
        print()
        result = joystick_ptt.capture()
        if result is None:
            print("\nNothing saved. Your existing settings are unchanged.")
        else:
            device, name, button = result
            settings["ptt_joystick_device"] = device
            settings["ptt_joystick_name"] = name
            settings["ptt_joystick_button"] = button
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                    json.dump(config, fh, indent=2, ensure_ascii=False)
                print(f"\nSaved. Hold '{settings['ptt_key']}' or that button to talk.")
            except OSError as exc:
                print(f"\nCouldn't write {CONFIG_PATH}: {exc}")
                print("Run this as Administrator, or set it by hand in commands.json:")
                print(f'  "ptt_joystick_name": "{name}", "ptt_joystick_button": {button}')
        input("\nPress Enter to close...")
        return

    # Read the player's real Star Citizen bindings and say plainly which
    # commands can't work for them. Without this the failure is silent:
    # the console reports a match and nothing happens in game, which reads
    # as "your program is broken" rather than "that action is on your
    # joystick". Takes ~0.5s; never fatal if it can't find anything.
    keybind_lines = []
    try:
        # allow_prompt: if auto-detection fails, ask where the game is
        # rather than silently running with the wrong keys.
        keybind_lines = sc_keybinds.report(commands, base_dir=BASE_DIR,
                                           allow_prompt=True)
        for line in keybind_lines:
            print(line)
    except Exception as exc:
        print(f"(couldn't check your Star Citizen keybinds: {exc})")
    print()

    # First launch only: open the command reference card and a note saying
    # what the program found in this player's own keybinds. They unzipped
    # a folder and double-clicked an exe -- this is the only chance to tell
    # them what they've got without making them go read files first.
    if not first_run.already_ran(BASE_DIR):
        opened = first_run.show(BASE_DIR, keybind_lines, build_info.WATERMARK)
        if opened:
            print("First run -- opened: " + ", ".join(opened))
            print()

    # Star Citizen is the priority process on this machine, not us. We only
    # burn CPU in ~450 ms bursts when PTT is released, but a burst that
    # grabs every core mid-dogfight is exactly the kind of hitch that gets
    # blamed on the game. Below-normal priority means Windows hands our
    # burst whatever is spare instead of preempting the game for it.
    try:
        import ctypes
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass  # nice-to-have, never worth failing startup over

    bundled_model_dir = WHISPER_MODEL_ROOT / settings["whisper_model"]
    model_source = str(bundled_model_dir) if bundled_model_dir.exists() else settings["whisper_model"]
    print(f"Loading Whisper model from '{model_source}' ...")
    # Measured: capping at 4 threads costs nothing in transcribe latency
    # (598 ms vs 619 ms unrestricted on tiny.en/int8) while leaving the
    # other cores to the game. Configurable in case a weaker CPU wants
    # more; 0 means "use every core", faster-whisper's default.
    model = WhisperModel(
        model_source,
        device=settings["whisper_device"],
        compute_type=settings["whisper_compute_type"],
        cpu_threads=settings.get("whisper_cpu_threads", 4),
    )

    sample_rate = settings["sample_rate"]

    # Everything the running loop reads lives in here so a live config reload
    # can swap it out atomically. Editing commands.json used to require a
    # restart, and the failure was invisible: the console still matched your
    # phrase, it just sent the old key (or nothing). That cost a 95-minute
    # debugging session, so the file is now watched.
    live = {
        "settings": settings,
        "plain": plain,
        "wildcard": wildcard,
        "commands": commands,
    }


    def _ptt_config():
        s = live["settings"]
        # Optional HOTAS / gamepad buttons as SECOND and THIRD push-to-talk.
        # The keyboard key keeps working exactly as before; these are purely
        # additive, so a keyboard-only player is unaffected and unplugged
        # hardware just reads as "not held". The joystick is matched by NAME
        # first, because SDL reorders devices depending on what is powered on.
        return (s["ptt_key"], s.get("ptt_joystick_device"),
                s.get("ptt_joystick_button"), s.get("ptt_joystick_name"),
                s.get("ptt_gamepad_button"))


    def ptt_held():
        key, dev, btn, name, pad = _ptt_config()
        # Cheapest check first: the keyboard state is already in memory,
        # while the controller checks each cost a driver call.
        if keyboard.is_pressed(key):
            return True
        if joystick_ptt.is_held(dev, btn, name):
            return True
        return joystick_ptt.gamepad_is_held(pad)


    def describe_triggers():
        key, dev, btn, name, pad = _ptt_config()
        out = [f"'{key}'"]
        if btn is not None and (name or dev is not None):
            out.append(f"{name or f'device {dev}'} button {btn}")
        if pad:
            found = " " if joystick_ptt.gamepad_present() else " (no pad detected) "
            out.append(f"gamepad {pad}{found}button")
        return " or ".join(out)


    config_watch = {"mtime": 0.0, "checked": 0.0}
    try:
        config_watch["mtime"] = CONFIG_PATH.stat().st_mtime
    except OSError:
        pass


    def reload_if_changed():
        """Re-read commands.json when it changes on disk. Never fatal."""
        now = time.monotonic()
        if now - config_watch["checked"] < 1.0:      # at most once a second
            return
        config_watch["checked"] = now
        try:
            mtime = CONFIG_PATH.stat().st_mtime
        except OSError:
            return
        if mtime == config_watch["mtime"]:
            return
        config_watch["mtime"] = mtime

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                fresh = json.load(fh)
            new_commands = fresh["commands"]
            new_settings = fresh["settings"]
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            # A half-saved or mistyped file must not take the program down
            # mid-flight. Keep running on the last good config and say so.
            print(f"\n[config] commands.json changed but could not be read: {exc}")
            print("[config] still using the previous settings -- fix it and save again.\n")
            return

        # Re-apply the player's own Star Citizen bindings over the fresh file,
        # exactly as at startup, so a reload can't silently drop the overrides.
        try:
            sc_keybinds.report(new_commands, base_dir=BASE_DIR)
        except Exception:
            pass

        live["settings"] = new_settings
        live["commands"] = new_commands
        live["plain"], live["wildcard"] = build_matchers(new_commands)
        print(f"\n[config] reloaded -- {len(new_commands)} commands. "
              f"Hold {describe_triggers()} to speak.\n")


    print(f"Ready. Hold {describe_triggers()} to speak. Ctrl+C to quit.")
    print("(Edits to config\\commands.json apply immediately -- no restart needed.)")
    if _ptt_config()[2] is None:          # no joystick button configured yet
        print('(To add a HOTAS button too, run "Set HOTAS Button.bat".)')

    audio_q = queue.Queue()
    recording = {"active": False}

    def audio_callback(indata, frames, time_info, status):
        if recording["active"]:
            audio_q.put(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate, channels=1, dtype="float32", callback=audio_callback
    )
    stream.start()

    try:
        while True:
            # Poll rather than keyboard.wait(): wait() only blocks on a key,
            # and PTT can now also come from a joystick button. 100 Hz is
            # imperceptible next to the game and costs nothing measurable.
            while not ptt_held():
                reload_if_changed()      # only while idle, never mid-recording
                time.sleep(0.01)

            # drain any stale audio, then record until PTT release
            while not audio_q.empty():
                audio_q.get_nowait()
            recording["active"] = True
            print("listening...")
            chunks = []
            while ptt_held():
                try:
                    chunks.append(audio_q.get(timeout=0.1))
                except queue.Empty:
                    pass
            recording["active"] = False

            if not chunks:
                continue
            audio = np.concatenate(chunks, axis=0).flatten()
            if len(audio) < sample_rate * 0.3:
                continue  # too short, probably an accidental tap

            process_command(model, live["plain"], live["wildcard"],
                            live["settings"], audio)

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        stream.close()


if __name__ == "__main__":
    main()
