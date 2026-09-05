"""
Open the shell for any title, with sample data. A dev tool, not a product.

    python -m voiceui.preview sc
    python -m voiceui.preview hd2 --page Commands

WHY IT EXISTS
-------------
Four titles now share one interface, so a change to a widget can look right in
Star Citizen and wrong in Helldivers. This opens any of them in one command,
without needing that product's engine, config or microphone -- so the palettes
can actually be compared side by side instead of assumed to work.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voiceui import AppShell, theme                              # noqa: E402
from voiceui.pages import (AboutPage, CommandsPage,              # noqa: E402
                           CustomPage, RunPage)
from voiceui.settings import ADVANCED, SIMPLE, Setting, SettingsPage  # noqa: E402
from voiceui.appearance import AppearancePage                     # noqa: E402

SAMPLE_COMMANDS = [
    dict(id="open_mobiglas", display_name="Open MobiGlas",
         category="Comms & Systems", keys=["f1"], verified=True,
         phrases=["open mobiglas", "bring up mobiglas"]),
    dict(id="engage_quantum", display_name="Engage Quantum Drive",
         category="Flight & Navigation", keys=[], key_label="Hold Mouse 1 (3s)",
         verified=True, phrases=["quantum", "engage quantum drive", "spool up"]),
    dict(id="open_map", display_name="Open Map", category="Flight & Navigation",
         keys=["f2"], verified=False,
         phrases=["open map", "star map", "bring up the map"]),
    dict(id="self_destruct", display_name="Self Destruct",
         category="Emergency", keys=["backspace"], verified=True,
         phrases=["self destruct", "scuttle the ship"]),
]

SAMPLE_SETTINGS = dict(
    ptt_key="right ctrl", ptt_gamepad_button="X", whisper_model="tiny.en",
    require_focused_window=True, fallback_tts=True, voice_pack="",
    match_threshold=72, target_window_title="Star Citizen",
    default_step_wait_ms=350, whisper_device="cpu",
    whisper_compute_type="int8", whisper_cpu_threads=4,
)

SAMPLE_SCHEMA = [
    Setting("ptt_key", "Push-to-talk key", "key", tier=SIMPLE, group="Listening",
            help="Hold this while you speak. Click, then press the key."),
    Setting("whisper_model", "Recognition model", "choice",
            choices=["tiny.en", "base.en"], tier=SIMPLE, group="Listening",
            help="Both run on this PC. Nothing is sent anywhere."),
    Setting("require_focused_window", "Only when the game is in front", "bool",
            tier=SIMPLE, group="Safety",
            help="Stops a command firing into Discord or a text box."),
    Setting("match_threshold", "Match strictness", "int", minimum=50,
            maximum=95, suffix="%", tier=ADVANCED, group="Recognition tuning",
            help="Higher means it must hear you more exactly."),
]


class _Store:
    """Just enough of CustomStore for the preview to render."""
    def __init__(self):
        self._off = set()
        self._theme = {}

    def all(self):
        return []

    def __len__(self):
        return 0

    def is_enabled(self, cid):
        return cid not in self._off

    def set_enabled(self, cid, on):
        self._off.discard(cid) if on else self._off.add(cid)

    def disabled_ids(self):
        return set(self._off)

    def theme(self):
        return dict(self._theme)

    def set_theme(self, o):
        self._theme = dict(o or {})

    def clear_theme(self):
        self._theme = {}


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "sc"
    t = theme.get(key)

    shell = AppShell(t, version="4.4.0", build_id="PREVIEW")
    shell.commands = SAMPLE_COMMANDS
    shell.custom_store = _Store()
    shell.controller = None
    shell.settings = dict(SAMPLE_SETTINGS)
    shell.settings_schema = SAMPLE_SCHEMA
    shell.settings_save = lambda changed: shell.settings.update(changed)
    shell.about_info = {
        "Product": t.product,
        "Preview": "sample data - not this product's real commands",
        "Palette": key,
    }

    for page in (RunPage, CommandsPage, CustomPage, SettingsPage,
                 AppearancePage, AboutPage):
        shell.add_page(page)

    if "--page" in sys.argv:
        try:
            shell.show(sys.argv[sys.argv.index("--page") + 1])
        except IndexError:
            pass

    shell.set_meta("preview  |  %s  |  offline" % key)
    shell.set_status("Preview of the %s palette." % key, "Idle", "neutral")
    shell.start()


if __name__ == "__main__":
    main()
