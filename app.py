"""The window, properly dressed.

WHY THIS EXISTS ALONGSIDE gui.py
--------------------------------
gui.py draws the same data with CustomTkinter. Tkinter cannot do the things
the design actually asks for -- a glow, a drifting field behind the panels,
a palette that cross-fades when you switch titles, a real starmap. So the
same data gets a second front end: an HTML page in a native window, using the
Edge WebView2 runtime that is already on every Windows 11 machine.

Nothing is duplicated. The loading below is the same three layers main.py and
gui.py use -- phrase grammar, control scheme, then the player's own overrides
-- and every write goes through the same CustomStore, so a switch flicked here
is the same switch main.py reads at start-up.

    python app.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import collections
import tempfile
import traceback
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Products/_shared on the path, for the same reason gui.py does it inline:
# bootstrap lives inside the package we are trying to reach.
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_shared"))
if os.path.isdir(os.path.join(_SHARED, "voicecore")) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import webview                                              # noqa: E402
from voicecore import control_scheme, phrase_grammar        # noqa: E402

from voiceui.store import CustomStore, atomic_write_json   # noqa: E402
from voiceui.datacache import DataCache                    # noqa: E402

import build_info                                           # noqa: E402

CONFIG_PATH = BASE_DIR / "config" / "commands.json"
CUSTOM_PATH = BASE_DIR / "config" / "my_commands.json"
PLACES_PATH = BASE_DIR / "config" / "places.json"
ROUTE_PATH = BASE_DIR / "config" / "current_route.json"
CACHE_DIR = BASE_DIR / "config" / "datacache"
WEBUI = BASE_DIR / "webui"


LOG_PATH = None


def _log(message):
    """Append to a log beside the program. Never raises."""
    global LOG_PATH
    try:
        if LOG_PATH is None:
            here = Path(sys.executable).parent if getattr(sys, "frozen", False) \
                else BASE_DIR
            LOG_PATH = here / "voice-control.log"
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _read_json(path, default=None):
    """Missing or broken file is never fatal here -- the page still opens."""
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# --------------------------------------------------------------- the payload
def build_payload():
    """Everything the page draws, in one dict. No live objects cross over."""
    config = _read_json(CONFIG_PATH) or {"commands": [], "settings": {}}
    commands = config.get("commands", [])
    settings = config.get("settings", {})

    problem = None
    written = recognised = 0
    try:
        written, recognised = phrase_grammar.expand_commands(commands)
    except Exception as exc:                    # a bad phrase must not blank the app
        problem = "A phrase in commands.json is malformed: %s" % exc

    scheme_name = settings.get("control_scheme", control_scheme.DEFAULT_SCHEME)
    unbound = []
    try:
        bindings = control_scheme.load(BASE_DIR, scheme_name)
        unbound = control_scheme.apply(commands, bindings, scheme_name)
    except Exception as exc:
        problem = problem or ("Control scheme %s: %s" % (scheme_name, exc))

    custom = CustomStore(CUSTOM_PATH)
    rebound = custom.apply_key_overrides(commands)

    mine = custom.all()
    rows = []
    for c, is_mine in ([(x, False) for x in commands] + [(x, True) for x in mine]):
        # A macro or a mouse-hold has no `keys` at all but is perfectly bound;
        # the label is what tells the truth, so it wins over an empty list.
        rows.append({
            "id": c.get("id"),
            "display_name": c.get("display_name") or c.get("id", ""),
            "category": c.get("category") or "Other",
            "phrases": c.get("phrases") or [],
            "keys": c.get("keys") or [],
            "key_label": c.get("key_label") or "",
            "verified": c.get("verified", True),
            "unbound": bool(c.get("_unbound")),
            "notes": c.get("notes") or "",
            "custom": is_mine,
        })
    order = {}
    for r in rows:
        order.setdefault(r["category"], len(order))
    rows.sort(key=lambda r: (order[r["category"]], r["display_name"]))

    places = (_read_json(PLACES_PATH) or {}).get("places", [])
    route = _read_json(ROUTE_PATH) or {}
    starmap = _read_json(BASE_DIR / "config" / "starmap.json") or {}

    cached = []
    if CACHE_DIR.is_dir():
        for p in sorted(CACHE_DIR.glob("*.json")):
            if p.name.endswith(".backup.json"):
                continue
            age = (time.time() - p.stat().st_mtime) / 3600.0
            cached.append({"name": p.stem,
                           "age": ("%.0f h old" % age) if age >= 1
                                  else ("%.0f min old" % (age * 60)),
                           "fresh": age < 24})

    schemes = []
    try:
        for n in control_scheme.available(BASE_DIR):
            doc = _read_json(BASE_DIR / "config" / "schemes" / (n + ".json")) or {}
            schemes.append({"name": n,
                            "description": doc.get("description", ""),
                            "bindings": len(doc.get("bindings") or {})})
    except Exception:
        pass

    return {
        "product": build_info.PRODUCT,
        "schemes": schemes,
        "ptt": {
            "key": settings.get("ptt_key", "right ctrl"),
            "joystick_name": settings.get("ptt_joystick_name"),
            "joystick_button": settings.get("ptt_joystick_button"),
            "gamepad_button": settings.get("ptt_gamepad_button"),
        },
        "listen_mode": settings.get("listen_mode", "ptt"),
        "wake_word": settings.get("open_mic_wake_word", ""),
        "game": "sc",
        "version": build_info.VERSION,
        "build": "%s  %s" % (build_info.BUILD_ID, build_info.BUILD_DATE),
        "scheme": scheme_name,
        "commands": rows,
        "settings": settings,
        "disabled": sorted(custom.disabled_ids()),
        "theme_overrides": custom.theme(),
        "problem": problem,
        "places": {
            "total": len(places),
            "live": sum(1 for p in places if p.get("live")),
        },
        "route": route,
        "market": {
            "version": (starmap.get("version") or {}).get("live", "?"),
            "cached": cached,
            "attribution": "Community trade data. Prices move; treat them as a "
                           "guide, not a quote.",
        },
        "credits": _read_json(BASE_DIR / "config" / "about.json") or {},
        "about": {
            "Product": build_info.PRODUCT,
            "Version": "%s   %s" % (build_info.VERSION, build_info.BUILD_DATE),
            "Made by": build_info.AUTHOR,
            "Cost": "Free. Pass it on to anyone who wants it.",
            "Recognition": "Local Whisper - offline, nothing leaves this PC",
            "Commands": "%d built-in, %d yours" % (len(commands), len(custom)),
            "Phrases": "%d written -> %d recognised" % (written, recognised),
            "Destinations": "%d known, %d in the live build"
                            % (len(places), sum(1 for p in places if p.get("live"))),
            "Controls": scheme_name,
            "Your edits": "%d rebound, %d disabled, %d custom"
                          % (rebound, len(custom.disabled_ids()), len(custom)),
            "Unbound": "%d command(s) have no key on this layout" % len(unbound),
        },
    }


def _data_cache():
    """One cache object, built the way sc_data expects it."""
    return DataCache(CACHE_DIR, bundled_dir=BASE_DIR / "config" / "bundled",
                     user_agent="StarCitizenVoiceControl/%s" % build_info.VERSION)


def _cached_rows():
    """Which feeds we hold and how old each one is."""
    out = []
    if CACHE_DIR.is_dir():
        for p in sorted(CACHE_DIR.glob("*.json")):
            if p.name.endswith(".backup.json"):
                continue
            age = (time.time() - p.stat().st_mtime) / 3600.0
            out.append({"name": p.stem,
                        "age": ("%.0f h old" % age) if age >= 1
                               else ("%.0f min old" % (age * 60)),
                        "fresh": age < 24})
    return out


# ------------------------------------------------------------------- the API
WINDOW = None          # set once the window exists


class _Mailbox:
    """Events the engine has produced that the page has not collected yet.

    Pushing straight into the page from the engine's worker thread did not
    arrive -- so the direction is reversed: the worker drops events here, the
    page drains them on a timer. A queue in the middle also means an event
    raised while the page is mid-render is still delivered, instead of hitting
    a handler that does not exist yet.
    """

    def __init__(self, cap=200):
        self._lock = threading.Lock()
        self._events = collections.deque(maxlen=cap)
        self.level = 0.0
        self.status = "stopped"
        self.message = ""
        self.tone = "neutral"

    def put(self, kind, detail):
        if kind == "level":                 # a meter, not a log: keep the last
            self.level = detail.get("rms", 0.0)
            return
        if kind == "state":
            self.status = detail.get("status", self.status)
            self.message = detail.get("message", "")
            self.tone = detail.get("tone", "neutral")
        with self._lock:
            self._events.append({"kind": kind, **detail})

    def drain(self):
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out


MAIL = _Mailbox()


def _to_page(kind, detail):
    """Never raises into the worker: a full mailbox drops the oldest event."""
    try:
        MAIL.put(kind, detail)
    except Exception:
        pass


class Api:
    """What the page is allowed to ask the machine to do.

    Deliberately small. The page renders and reads; anything that touches disk
    or the engine comes through here, so there is one list of side effects
    rather than a scattering of them.
    """

    def __init__(self):
        self.store = CustomStore(CUSTOM_PATH)
        self._engine = None

    # ------------------------------------------------------------- engine
    def _eng(self):
        """Built on first use: importing it loads sounddevice and numpy, and
        a player who never presses Start should not pay for that."""
        if self._engine is None:
            import engine as engine_mod
            self._engine = engine_mod.Engine(BASE_DIR, on_event=_to_page)
        return self._engine

    def engine_start(self, mode="ptt"):
        """Start listening, and never fail quietly.

        A packaged build has no console, so an exception here used to vanish:
        the button came back up and nothing else happened, which looks exactly
        like a program that ignored you. Anything that goes wrong now lands on
        screen and in a log beside the exe.
        """
        try:
            e = self._eng()
            e.start(mode)
            return {"running": True, "mode": mode, "triggers": e.triggers()}
        except Exception as exc:
            detail = traceback.format_exc()
            _log("engine_start failed\n" + detail)
            return {"running": False, "error": "%s: %s"
                    % (type(exc).__name__, exc), "trace": detail}

    def diagnose(self):
        """Import everything the engine needs and report what breaks.

        Written for exactly the situation it was written in: the packaged copy
        would not listen and there was no way to see why.
        """
        out = []
        for name in ("numpy", "sounddevice", "faster_whisper", "keyboard",
                     "pydirectinput", "rapidfuzz", "joystick_ptt", "phonetic",
                     "gamedex", "main", "engine"):
            try:
                __import__(name)
                out.append({"name": name, "ok": True, "why": ""})
            except Exception as exc:
                out.append({"name": name, "ok": False,
                            "why": "%s: %s" % (type(exc).__name__, exc)})
        try:
            import sounddevice as sd
            devs = [d["name"] for d in sd.query_devices()
                    if d["max_input_channels"] > 0]
        except Exception as exc:
            devs = ["could not list microphones: %s" % exc]
        model = BASE_DIR / "whisper_model"
        out.append({"name": "whisper_model folder", "ok": model.is_dir(),
                    "why": ", ".join(sorted(p.name for p in model.glob("*")))
                           if model.is_dir() else "not found at %s" % model})
        _log("diagnose: " + "; ".join(
            "%s=%s" % (r["name"], "ok" if r["ok"] else r["why"]) for r in out))
        return {"checks": out, "microphones": devs, "base": str(BASE_DIR)}

    def engine_stop(self):
        if self._engine:
            self._engine.stop(wait=False)
        return {"running": False}

    def engine_mode(self, mode):
        """Switch between hold-to-talk and open mic without dropping the mic."""
        e = self._eng()
        e.set_mode(mode)
        self.set_setting("listen_mode", mode)
        return {"mode": mode, "triggers": e.triggers()}

    def drain(self):
        """Everything that has happened since the page last asked.

        One call rather than several: the page needs the meter, the status and
        the new lines together, and three round trips a second is how a UI
        starts feeling laggy.
        """
        e = self._engine
        return {
            "running": bool(e and e.running),
            "status": MAIL.status,
            "message": MAIL.message,
            "tone": MAIL.tone,
            "level": MAIL.level,
            "events": MAIL.drain(),
            "triggers": e.triggers() if e else "",
        }

    def engine_status(self):
        e = self._engine
        return {"running": bool(e and e.running),
                "status": e.status if e else "stopped",
                "triggers": e.triggers() if e else ""}

    def capture_hotas(self):
        """Watch for a stick button and save it as a second push-to-talk."""
        got = self._eng().capture_hotas()
        if not got:
            return {"saved": False}
        device, name, button = got
        self.set_setting("ptt_joystick_device", device)
        self.set_setting("ptt_joystick_name", name)
        self.set_setting("ptt_joystick_button", button)
        if self._engine:
            self._engine.reload()
        return {"saved": True, "name": name, "button": button,
                "triggers": self._eng().triggers()}

    def clear_hotas(self):
        for k in ("ptt_joystick_device", "ptt_joystick_name",
                  "ptt_joystick_button"):
            self.set_setting(k, None)
        if self._engine:
            self._engine.reload()
        return {"saved": False, "triggers": self._eng().triggers()}

    def calibrate_search_click(self, delay_s=10):
        """Record where the starmap's search box is, by watching the mouse.

        Ten seconds to alt-tab into the game with the map open and rest the
        pointer on the search field. What gets stored is a fraction of the
        game window, not a pixel, so it survives a resolution change or a
        move between monitors.
        """
        import ctypes, ctypes.wintypes, time as _t
        _t.sleep(float(delay_s))

        u32 = ctypes.windll.user32
        hwnd = u32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value or ""

        rect = ctypes.wintypes.RECT()
        u32.GetClientRect(hwnd, ctypes.byref(rect))
        origin = ctypes.wintypes.POINT(0, 0)
        u32.ClientToScreen(hwnd, ctypes.byref(origin))
        cur = ctypes.wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(cur))

        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return {"saved": False, "why": "could not measure that window"}

        fx = (cur.x - origin.x) / float(w)
        fy = (cur.y - origin.y) / float(h)
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            return {"saved": False, "window": title,
                    "why": "the pointer was outside that window"}

        target = (_read_json(CONFIG_PATH) or {}).get(
            "settings", {}).get("control_scheme", control_scheme.DEFAULT_SCHEME)
        path = BASE_DIR / "config" / "schemes" / (target + ".json")
        doc = _read_json(path)
        if not doc:
            return {"saved": False, "why": "could not read %s" % target}
        for st in doc["bindings"]["plot_route_to"]["steps"]:
            if st.get("action") == "click":
                st["x"] = round(fx, 4)
                st["y"] = round(fy, 4)
        atomic_write_json(path, doc)
        return {"saved": True, "window": title, "scheme": target,
                "x": round(fx, 4), "y": round(fy, 4),
                "pixels": "%d,%d in a %dx%d window" % (cur.x - origin.x,
                                                       cur.y - origin.y, w, h)}

    def test_plot(self, destination="Lorville", delay_s=6):
        """Run the plot macro for real, without saying anything.

        Same code path a spoken command takes -- name resolution, the click,
        the paste, Enter -- so a pass here means the spoken one works too.
        The delay is to alt-tab into the game with the map open first.
        """
        import time as _t
        import main as core

        cfg = _read_json(CONFIG_PATH) or {}
        settings = cfg.get("settings", {})
        scheme_name = settings.get("control_scheme", control_scheme.DEFAULT_SCHEME)
        doc = _read_json(BASE_DIR / "config" / "schemes" / (scheme_name + ".json")) or {}
        binding = (doc.get("bindings") or {}).get("plot_route_to")
        if not binding:
            return {"ok": False, "why": "no plot binding in %s" % scheme_name}

        steps = binding.get("steps") or []
        click = next((x for x in steps if x.get("action") == "click"), None)
        calibrated = bool(click and click.get("x") is not None)

        target, note = core.resolve_destination(destination)
        _t.sleep(float(delay_s))

        front = core.foreground_window_title()
        core.run_steps(steps, destination,
                       settings.get("default_step_wait_ms", 350))
        return {"ok": True, "heard": destination, "resolved": target,
                "note": note, "calibrated": calibrated, "window": front,
                "scheme": scheme_name,
                "steps": " -> ".join(x["action"] for x in steps)}

    def game_state(self):
        """Where the player is and what the game last plotted.

        Read straight out of Star Citizen's own Game.log -- there is no API --
        and every name resolved through the same place index the voice
        commands use, so the map can draw whatever this returns.
        """
        try:
            import sc_state
            return sc_state.resolved()
        except Exception as exc:
            return {"found": False, "error": str(exc)}

    def reconcile(self):
        """What we heard vs what the game actually plotted."""
        try:
            import reconcile as rc
            return rc.check()
        except Exception as exc:
            return {"ok": False, "why": str(exc), "rows": []}

    def keybinds(self):
        """Read the player's own Star Citizen bindings and say what breaks.

        This is the answer to "why did that command do nothing". A command
        cleared in game, or moved onto a stick, cannot be reached by sending a
        keystroke -- and until you are told that, it looks like the program is
        broken rather than the binding being absent.
        """
        try:
            import sc_keybinds
            import main as core
            found = sc_keybinds.find_actionmaps()
            cfg = core.load_config()
            lines = sc_keybinds.report(cfg["commands"], base_dir=BASE_DIR,
                                       allow_prompt=False)
        except Exception as exc:
            return {"ok": False, "why": str(exc), "rows": []}

        rows = []
        for line in lines:
            text = line.strip()
            if text.startswith("[X]"):
                body = text[3:].strip()
                cid, _, why = body.partition(":")
                rows.append({"id": cid.strip(), "why": why.strip()})
        return {"ok": True,
                "profile": str(found[0]) if found else "",
                "summary": lines[0].strip() if lines else "",
                "rows": rows,
                "extra": [l.strip() for l in lines if l.strip().startswith("(")]}

    def refresh_data(self):
        """Pull fresh prices and locations from the live services.

        The cache already knows how to fall back -- fresh copy, then the
        service, then a backup service, then a stale copy, then the snapshot
        that shipped -- so a service being down degrades rather than fails.
        This just tells it to go and look now.
        """
        try:
            import sc_data
            cache = _data_cache()
            done = cache.refresh_all(sc_data.ENDPOINTS)
            ok = sum(1 for r in done if getattr(r, "is_live", False))
            return {"ok": ok > 0, "updated": ok, "total": len(sc_data.ENDPOINTS),
                    "why": "" if ok else "no service answered",
                    "cached": _cached_rows()}
        except Exception as exc:
            return {"ok": False, "updated": 0, "total": 0, "why": str(exc),
                    "cached": _cached_rows()}

    def market_search(self, term, kind=""):
        """Everything in the game that matches `term`.

        Same index and the same matcher the voice command uses, so what you
        can say you can type, and both spell it wrong the same way.
        """
        try:
            import gamedex
            kinds = [kind] if kind else None
            return {"ok": True, "term": term,
                    "hits": gamedex.look_up(term, kinds=kinds, limit=25)}
        except Exception as exc:
            return {"ok": False, "term": term, "hits": [], "why": str(exc)}

    # ------------------------------------------------------------ settings
    def set_setting(self, key, value):
        """Write one key into commands.json and nothing else.

        Re-read from disk first: the copy the engine holds has the phrase
        grammar expanded and the control scheme merged in, so writing that
        back would bake hundreds of generated phrases into the authored file.
        """
        on_disk = _read_json(CONFIG_PATH) or {}
        on_disk.setdefault("settings", {})
        on_disk["settings"][key] = value
        atomic_write_json(CONFIG_PATH, on_disk)
        return {key: value}

    def payload(self):
        return build_payload()

    def set_enabled(self, command_id, enabled):
        """The same switch main.py reads. Flicking it here is permanent."""
        self.store.set_enabled(command_id, bool(enabled))
        self.store.save()
        return sorted(self.store.disabled_ids())

    def set_theme(self, game_key):
        """Remember which title's colours you were last looking at."""
        overrides = dict(self.store.theme())
        overrides["_game"] = game_key
        self.store.set_theme(overrides)
        self.store.save()
        return game_key

    def route(self):
        return _read_json(ROUTE_PATH) or {}

    def clear_route(self):
        atomic_write_json(ROUTE_PATH, {
            "_readme": "Routes plotted by voice. The game forgets these; this "
                       "file does not. Safe to delete.",
            "legs": []})
        return {}

    def open_config_folder(self):
        os.startfile(str(BASE_DIR / "config"))       # noqa: S606 - user asked

    def quit(self):
        for w in webview.windows:
            w.destroy()


def main():
    api = Api()
    page = build_payload()

    # The payload is injected as a literal rather than fetched, so the page has
    # its data in the first frame -- no spinner, no empty shell, no round trip.
    html = io.open(WEBUI / "app.html", "r", encoding="utf-8").read()
    marker = "/*__DATA__*/"
    assert marker in html, "app.html lost its data marker"
    head, tail = html.split(marker, 1)
    tail = tail[tail.index(";"):]                 # drop the placeholder literal
    html = head + json.dumps(page, ensure_ascii=False) + tail

    saved = (page.get("theme_overrides") or {}).get("_game")
    if saved:
        html = html.replace('let theme = DATA.game in THEMES',
                            'let theme = %s in THEMES' % json.dumps(saved), 1)

    # Written out and opened as a file rather than handed over as a string:
    # the Map page embeds map.html sitting beside it, and a relative src only
    # resolves against a real URL.
    live = WEBUI / "_live.html"
    fd, tmp = tempfile.mkstemp(prefix="._live.", suffix=".tmp", dir=str(WEBUI))
    with io.open(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, str(live))

    global WINDOW
    WINDOW = webview.create_window(
        "%s  %s" % (build_info.PRODUCT, build_info.VERSION),
        url=live.as_uri(),
        width=1280, height=820, min_size=(1000, 680),
        background_color="#070b10",
        js_api=api,
    )
    # WebView2 keeps a browser profile -- cache, cookies, a lock file -- and
    # it must not live inside the program folder. It broke the build (the
    # packager could not read a cache file the running app had open), and in
    # an installed copy that folder may be read-only. Per-user data belongs
    # in the per-user place.
    profile = Path(os.environ.get("LOCALAPPDATA") or BASE_DIR) / "ObiVoiceControl"
    try:
        profile.mkdir(parents=True, exist_ok=True)
    except OSError:
        profile = BASE_DIR
    webview.start(gui="edgechromium", private_mode=False,
                  storage_path=str(profile))


if __name__ == "__main__":
    main()
