"""
The window. Run this instead of main.py to get a UI.

WHY THIS IS A SEPARATE ENTRY POINT
----------------------------------
main.py stays exactly as it is -- a console app that works, that the testers
are already running, and that never needs a display. This adds a window in
front of the same data and the same engine rather than rewriting either.

Everything visual lives in Products/_shared/voiceui/, shared with the other
three titles. This file is only the wiring: load Star Citizen's commands and
control scheme, hand them to the shell, name the accent.

    python gui.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Put Products/_shared on sys.path so `voicecore` and `voiceui` resolve.
#
# This is done inline rather than via `from voicecore import bootstrap`,
# because bootstrap lives *inside* voicecore -- importing it already requires
# the path we are trying to add. main.py gets away with it only because the
# local control_scheme.py shim happens to insert the path as a side effect of
# an earlier import. Depending on import order for this is a trap; be explicit.
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_shared"))
if os.path.isdir(os.path.join(_SHARED, "voicecore")) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from voicecore import control_scheme, phrase_grammar   # noqa: E402

from voiceui import AppShell, theme
from voiceui.appearance import AppearancePage
from voiceui.pages import AboutPage, CommandsPage, CustomPage, RunPage
from voiceui.settings import ADVANCED, SIMPLE, Setting, SettingsPage
from voiceui.datacache import DataCache
from voiceui.store import CustomStore, atomic_write_json

import sc_data
from sc_lookup import LookupPage
from sc_routes import RoutesPage

import build_info


# Which dial is a player meant to touch, and which is a diagnostic? That is
# the whole Simple/Advanced split, declared once, in the product that knows.
SETTINGS_SCHEMA = [
    Setting("ptt_key", "Push-to-talk key", "key", tier=SIMPLE, group="Listening",
            help="Hold this key while you speak. Click the button, then press "
                 "the key you want."),
    Setting("ptt_gamepad_button", "Gamepad push-to-talk", "choice",
            choices=["", "A", "B", "X", "Y", "LB", "RB"], tier=SIMPLE,
            group="Listening",
            help="Optional. Use a controller button instead of a key."),
    Setting("whisper_model", "Recognition model", "choice",
            choices=["tiny.en", "base.en"], tier=SIMPLE, group="Listening",
            help="base.en hears you more accurately; tiny.en starts faster and "
                 "uses less memory. Both run on this PC -- nothing is sent "
                 "anywhere."),
    Setting("require_focused_window", "Only when the game is in front", "bool",
            tier=SIMPLE, group="Safety",
            help="Strongly recommended. Stops a command firing into Discord, "
                 "your browser, or a text box."),
    Setting("fallback_tts", "Speak back when there's no recorded clip", "bool",
            tier=SIMPLE, group="Voice",
            help="Off means those commands confirm silently instead of using "
                 "the built-in robot voice."),
    Setting("voice_pack", "Voice pack", "text", tier=SIMPLE, group="Voice",
            help="Name of a folder inside voice_acks/. Leave empty for the "
                 "built-in voice."),

    Setting("match_threshold", "Match strictness", "int",
            minimum=50, maximum=95, suffix="%", tier=ADVANCED,
            group="Recognition tuning",
            help="Higher means it must hear you more exactly. Raise it if "
                 "wrong commands fire; lower it if yours are being missed."),
    Setting("target_window_title", "Game window title", "text", tier=ADVANCED,
            group="Recognition tuning",
            help="Used by the focus check above. Only change this if Star "
                 "Citizen's window is named something else."),
    Setting("default_step_wait_ms", "Pause between macro steps", "int",
            minimum=50, maximum=1000, suffix=" ms", tier=ADVANCED,
            group="Recognition tuning",
            help="How long multi-step commands wait between keypresses."),
    Setting("whisper_device", "Compute device", "choice",
            choices=["cpu", "cuda"], tier=ADVANCED, group="Performance",
            help="cuda uses your graphics card and is much faster, if it is "
                 "supported on this machine."),
    Setting("whisper_compute_type", "Compute precision", "choice",
            choices=["int8", "int8_float16", "float16", "float32"],
            tier=ADVANCED, group="Performance",
            help="int8 is the smallest and fastest on CPU."),
    Setting("whisper_cpu_threads", "CPU threads", "int",
            minimum=1, maximum=16, tier=ADVANCED, group="Performance",
            help="How many cores transcription may use."),
]

BASE_DIR = (Path(sys.executable).parent if getattr(sys, "frozen", False)
            else Path(__file__).parent)
CONFIG_PATH = BASE_DIR / "config" / "commands.json"
CUSTOM_PATH = BASE_DIR / "config" / "my_commands.json"
CACHE_DIR = BASE_DIR / "config" / "datacache"
BUNDLED_DIR = BASE_DIR / "config" / "bundled"


class ConfigError(Exception):
    """Carries a message meant for the user, not a stack trace."""


def load_commands():
    """Same three layers main.py uses, but raising instead of exiting.

    A GUI cannot call input() and sys.exit() -- there is no console to read the
    message. Errors come back as text the window can show.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise ConfigError(
            "Could not find %s.\nMake sure the 'config' folder is sitting "
            "next to this program." % CONFIG_PATH)
    except json.JSONDecodeError as e:
        raise ConfigError(
            "commands.json isn't valid JSON: %s\nOpen it in Notepad, go to "
            "line %s, and look for a missing comma, quote or bracket."
            % (e.msg, e.lineno))

    # Layer 1: "[open;bring up] mobiglas" -> every spoken variant.
    try:
        before, after = phrase_grammar.expand_commands(config.get("commands", []))
    except phrase_grammar.GrammarError as e:
        raise ConfigError(
            "A phrase in commands.json is malformed:\n  %s\n"
            "Brackets group alternatives, like [open;bring up] mobiglas." % e)

    # Layer 3: what actually gets pressed.
    scheme_name = config.get("settings", {}).get(
        "control_scheme", control_scheme.DEFAULT_SCHEME)
    try:
        bindings = control_scheme.load(BASE_DIR, scheme_name)
    except control_scheme.SchemeError as e:
        raise ConfigError(str(e))

    unbound = control_scheme.apply(config["commands"], bindings, scheme_name)
    if unbound:
        # Honest: this layout genuinely cannot reach these, so they are
        # dropped rather than half-firing. The count is surfaced in the UI.
        config["commands"] = [c for c in config["commands"]
                              if not c.get("_unbound")]

    return config, scheme_name, before, after, unbound


def main():
    # Read the player's colour overrides BEFORE the palette loads -- a widget
    # built against the default would keep it.
    _early = CustomStore(CUSTOM_PATH)
    t = theme.get("sc", _early.theme())

    try:
        config, scheme_name, written, recognised, unbound = load_commands()
    except ConfigError as exc:
        # Even the failure gets a window. A console app could print and quit;
        # a double-clicked exe that vanishes tells the user nothing.
        shell = AppShell(t, version=build_info.VERSION)
        shell.commands = []
        shell.about_info = {"Problem": str(exc)}
        shell.add_page(AboutPage)
        shell.set_status("Could not load your commands.", "Error", "crit")
        shell.start()
        return

    commands = config["commands"]
    settings = config.get("settings", {})

    custom = _early

    shell = AppShell(t, version=build_info.VERSION,
                     build_id=build_info.COPY_ID)

    # What the shared pages read. Nothing in voiceui knows these are Star
    # Citizen commands -- it only knows they are commands.
    # The player's own rebinds go on LAST, after the control scheme, so their
    # choice beats the shipped binding.
    rebound = custom.apply_key_overrides(commands)
    shell.commands = commands + custom.all()
    shell.custom_store = custom
    shell.controller = None            # engine adapter lands here next
    shell.settings = settings
    shell.settings_schema = SETTINGS_SCHEMA
    shell.data_cache = DataCache(CACHE_DIR, bundled_dir=BUNDLED_DIR,
                                 user_agent="StarCitizenVoiceControl/%s"
                                            % build_info.VERSION)

    def save_settings(changed: dict):
        """Write the changed keys back into commands.json, and nothing else.

        Re-read from disk first rather than dumping the in-memory config: that
        copy has had the phrase grammar expanded and the control scheme merged
        into it, so writing it out would bake 400 generated phrases and a
        device layout into the authored file. Only settings keys move.
        """
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            on_disk = json.load(f)
        on_disk.setdefault("settings", {})
        for key, value in changed.items():
            if value == "":                       # empty text field means unset
                value = None if key.endswith(("_device", "_name")) else value
            on_disk["settings"][key] = value
        atomic_write_json(CONFIG_PATH, on_disk)
        settings.update(changed)

    shell.settings_save = save_settings
    shell.about_info = {
        "Product":    build_info.PRODUCT,
        "Version":    "%s  (%s)" % (build_info.VERSION, build_info.CHANNEL),
        "Build":      "%s   %s" % (build_info.BUILD_ID, build_info.BUILD_DATE),
        "Copy ID":    build_info.COPY_ID,
        "Publisher":  build_info.PUBLISHER,
        "Copyright":  build_info.COPYRIGHT,
        "Support":    build_info.SUPPORT,
        "Recognition": "Local Whisper - offline, nothing leaves this PC",
        "Commands":   "%d built-in, %d yours" % (len(commands), len(custom)),
        "Phrases":    "%d written -> %d recognised" % (written, recognised),
        "Controls":   scheme_name,
        "Your edits": "%d rebound, %d disabled, %d custom"
                      % (rebound, len(custom.disabled_ids()), len(custom)),
    }

    shell.add_page(RunPage)
    shell.add_page(CommandsPage)
    shell.add_page(CustomPage)
    shell.add_page(LookupPage)
    shell.add_page(RoutesPage)
    shell.add_page(SettingsPage)
    shell.add_page(AppearancePage)
    shell.add_page(AboutPage)

    # `python gui.py --page Commands` opens straight to a page. Handy when
    # you are working on one and do not want to click through every time.
    if "--page" in sys.argv:
        try:
            shell.show(sys.argv[sys.argv.index("--page") + 1])
        except (IndexError, KeyError):
            pass

    shell.set_meta("%s  |  %d commands  |  offline" %
                   (scheme_name, len(shell.commands)))
    if unbound:
        shell.set_status(
            "%d command(s) have no key on this layout and are disabled."
            % len(unbound), "Idle", "warn")
    else:
        shell.set_status("Ready. Open Listen to start.", "Idle", "neutral")

    shell.start()


if __name__ == "__main__":
    main()
