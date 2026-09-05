"""
The look. One shared craft, a different world per game.

WHAT IS SHARED AND WHAT IS NOT
------------------------------
Shared: the layout, the component set, the typography discipline, the layering
technique lifted from the website (art low, glow behind, content on top), and
the quality bar. Learn one tool, you can drive all four.

NOT shared: the colours. Each title wears its OWN game's palette --

    Star Citizen      cockpit cyan on blue-black, amber cautions
    Helldivers 2      Super Earth yellow, hazard stripes, stencil black
    Elite Dangerous   the famous cockpit orange on near-black
    Bridge Crew       LCARS: amber, violet and blue blocks on true black

That is the point Obly made directly: "Star Citizen would have the Star Citizen
colours and the Star Citizen theme, whereas the Helldivers version would have
the different colours from Helldivers. They are all team specific."

HOW IT WORKS
------------
`Ink` is the ACTIVE palette. It starts on Star Citizen's and is rewritten in
place by `apply(theme)` at startup. Every widget reads `Ink.SURFACE` and friends
at construction time -- which happens after apply() -- so no component needs to
know which game it is drawing, and adding a fifth title touches only PALETTES.

The house craft still shows: the technique and structure come from
`03_Business/Websites/index_4.html`, which is upstream of this file. Only the
hues are per-game.
"""
from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass, field


# --------------------------------------------------------------- per-game palettes
#
# Each entry is a complete world: ground, panels, borders, text, and the
# action colour that primary buttons wear. Status colours are tuned per world
# too, so a warning in Helldivers looks like Helldivers and not like a web app.

PALETTES: dict[str, dict] = {

    # Star Citizen: cockpit glass. Blue-black hull, cyan HUD, amber caution.
    "sc": dict(
        BG="#070b10", SURFACE="#0e151d", SURFACE_2="#161f2a", SURFACE_3="#1f2b39",
        BORDER="#24384a", BORDER_SOFT="#182432",
        TEXT="#dbe9f5", TEXT_DIM="#8fa8bd", TEXT_MUTE="#5b7186",
        ACTION="#4fb3e8", ACTION_BRIGHT="#7fcdf5", ACTION_INK="#04121c",
        GOOD="#4fc38a", GOOD_SOFT="#0c2a1e",
        WARN="#f0a63c", WARN_SOFT="#2e1f0a",
        CRIT="#e05545", CRIT_SOFT="#2f120e",
    ),

    # Helldivers 2: Super Earth. Stencil black, hazard yellow, blood red.
    "hd2": dict(
        BG="#0b0b08", SURFACE="#15150f", SURFACE_2="#1f1e15", SURFACE_3="#2b291c",
        BORDER="#403c25", BORDER_SOFT="#262418",
        TEXT="#f2ecd8", TEXT_DIM="#b0a889", TEXT_MUTE="#736c55",
        ACTION="#ffd400", ACTION_BRIGHT="#ffe250", ACTION_INK="#141200",
        GOOD="#8fbf3f", GOOD_SOFT="#20290c",
        WARN="#ff9d1e", WARN_SOFT="#2e1d06",
        CRIT="#d3382b", CRIT_SOFT="#320f0b",
    ),

    # Elite Dangerous: the orange cockpit. Almost no other hue, by design.
    "ed": dict(
        BG="#0a0705", SURFACE="#150e07", SURFACE_2="#1e150b", SURFACE_3="#2b1e10",
        BORDER="#452c12", BORDER_SOFT="#28190c",
        TEXT="#ffd9a8", TEXT_DIM="#c09257", TEXT_MUTE="#7d5f38",
        ACTION="#f07b05", ACTION_BRIGHT="#ff9a33", ACTION_INK="#170b00",
        GOOD="#c8a02a", GOOD_SOFT="#2a2109",
        WARN="#ffb648", WARN_SOFT="#2f2109",
        CRIT="#e04a1e", CRIT_SOFT="#331307",
    ),

    # Star Trek Bridge Crew: LCARS. True black, amber/violet/blue blocks.
    "stbc": dict(
        BG="#000000", SURFACE="#12101a", SURFACE_2="#1c1826", SURFACE_3="#282235",
        BORDER="#443a5c", BORDER_SOFT="#241f33",
        TEXT="#d7c4ee", TEXT_DIM="#cc99cc", TEXT_MUTE="#7d6a94",
        ACTION="#cc99cc", ACTION_BRIGHT="#e0b8e0", ACTION_INK="#140b1d",
        GOOD="#99ccff", GOOD_SOFT="#0e2033",
        WARN="#ffcc66", WARN_SOFT="#33280f",
        CRIT="#cc6666", CRIT_SOFT="#2e1414",
    ),
}


class Ink:
    """The ACTIVE palette. Rewritten by apply(); never edit these by hand."""
    BG = SURFACE = SURFACE_2 = SURFACE_3 = "#000000"
    BORDER = BORDER_SOFT = "#000000"
    TEXT = TEXT_DIM = TEXT_MUTE = "#ffffff"
    ACTION = ACTION_BRIGHT = ACTION_INK = "#ffffff"
    GOOD = GOOD_SOFT = WARN = WARN_SOFT = CRIT = CRIT_SOFT = "#ffffff"

    # Kept as aliases so older call sites that ask for GOLD/OBSIDIAN keep
    # working -- they now mean "this game's action colour" and "its ground".
    GOLD = ACTION
    GOLD_BRIGHT = ACTION_BRIGHT
    OBSIDIAN = BG
    CHAMPAGNE = TEXT


# The seven tokens a user is allowed to recolour, and what to call them.
# Deliberately not all of Ink -- status colours stay ours, because "make the
# critical colour green" is a foot-gun, not a preference.
EDITABLE = [
    ("BG",        "Background"),
    ("SURFACE",   "Panels"),
    ("SURFACE_2", "Inputs and rows"),
    ("BORDER",    "Borders"),
    ("TEXT",      "Text"),
    ("TEXT_MUTE", "Muted text"),
    ("ACTION",    "Accent"),
]


def apply(game_key: str, overrides: dict | None = None):
    """Load one game's world into Ink, then layer the user's colours on top.

    Overrides are the player's own choices and always win over ours -- this is
    their tool, and a preset they dislike should not be something they have to
    live with. Anything they have not touched keeps the game's value.
    """
    pal = dict(PALETTES.get((game_key or "").lower(), PALETTES["sc"]))
    for name, value in pal.items():
        setattr(Ink, name, value)
    for name, value in (overrides or {}).items():
        if name in pal or name in dict(EDITABLE):
            setattr(Ink, name, value)
    # Derived shades follow the accent so a recoloured accent stays coherent.
    if overrides and "ACTION" in overrides:
        Ink.ACTION_BRIGHT = overrides["ACTION"]
    if overrides and "SURFACE_2" in overrides:
        Ink.SURFACE_3 = overrides["SURFACE_2"]
    Ink.GOLD = Ink.ACTION
    Ink.GOLD_BRIGHT = Ink.ACTION_BRIGHT
    Ink.OBSIDIAN = Ink.BG
    Ink.CHAMPAGNE = Ink.TEXT
    return Ink


apply("sc")          # a sane default so importing alone never leaves it blank


# ---------------------------------------------------------------------- fonts
#
# The house faces are Cormorant Garamond / Petit Formal Script / Manrope /
# JetBrains Mono. On the web they come from Google Fonts; a Tk app can only use
# fonts installed on the machine, and none of the four are installed here.
# Drop the .ttf files into voiceui/assets/fonts/ and they get registered
# privately at startup -- no install, no admin, gone when the app closes.
# Otherwise the closest face Windows already ships stands in.

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "fonts")
FDR_PRIVATE = 0x10


def load_bundled_fonts() -> list:
    loaded = []
    if not os.path.isdir(_FONT_DIR):
        return loaded
    try:
        add = ctypes.windll.gdi32.AddFontResourceExW
    except (AttributeError, OSError):
        return loaded
    for fn in os.listdir(_FONT_DIR):
        if fn.lower().endswith((".ttf", ".otf")):
            try:
                if add(os.path.join(_FONT_DIR, fn), FDR_PRIVATE, 0):
                    loaded.append(fn)
            except OSError:
                pass
    return loaded


def _first_available(candidates, installed):
    for name in candidates:
        if name.lower() in installed:
            return name
    return candidates[-1]


class Type:
    DISPLAY = "Constantia"
    UI      = "Segoe UI"
    MONO    = "Consolas"
    SCRIPT  = "Segoe Script"
    resolved = False
    bundled: list = []


def resolve(tk_font_module, game_key: str = "sc"):
    """Pick the best available face per role. Call once, after Tk exists.

    The display face is game-flavoured too: Elite and Helldivers read as
    machine-stencilled, so they take a squarer face than Star Citizen's.
    """
    if Type.resolved:
        return Type
    Type.bundled = load_bundled_fonts()
    installed = {f.lower() for f in tk_font_module.families()}

    display_by_game = {
        "sc":   ["Cormorant Garamond", "Constantia", "Cambria", "Georgia"],
        "hd2":  ["Bahnschrift", "Segoe UI Semibold", "Franklin Gothic Medium",
                 "Segoe UI"],
        "ed":   ["Bahnschrift", "Segoe UI Semibold", "Consolas", "Segoe UI"],
        "stbc": ["Bahnschrift", "Segoe UI Semibold", "Segoe UI"],
    }
    Type.DISPLAY = _first_available(
        display_by_game.get(game_key, display_by_game["sc"]), installed)
    Type.UI = _first_available(
        ["Manrope", "Corbel", "Candara", "Segoe UI"], installed)
    Type.MONO = _first_available(
        ["JetBrains Mono", "Cascadia Code", "Consolas"], installed)
    Type.SCRIPT = _first_available(
        ["Petit Formal Script", "Segoe Script", "Segoe UI"], installed)
    Type.resolved = True
    return Type


# --------------------------------------------------------------------- metrics

class Metric:
    RADIUS      = 8
    RADIUS_SM   = 5
    PAD         = 16
    PAD_SM      = 8
    GAP         = 12
    SIDEBAR_W   = 214
    STATUSBAR_H = 34
    ROW_H       = 34
    GLOW_PERIOD_MS = 6000        # matches the website's glowPulse


# ------------------------------------------------------------------ per game

@dataclass(frozen=True)
class GameTheme:
    key:        str
    product:    str
    accent:     str
    accent_dim: str
    accent_ink: str
    tagline:    str
    glow:       str            # "r,g,b" for the backdrop glow
    icon:       str = ""

    ink: type = field(default=Ink, compare=False, repr=False)
    type: type = field(default=Type, compare=False, repr=False)
    metric: type = field(default=Metric, compare=False, repr=False)


def _theme(key, product, tagline, glow):
    p = PALETTES[key]
    return GameTheme(key=key, product=product, tagline=tagline, glow=glow,
                     accent=p["ACTION"], accent_dim=p["ACTION"],
                     accent_ink=p["ACTION_INK"])


THEMES: dict[str, GameTheme] = {
    "sc":   _theme("sc", "Star Citizen Voice Control",
                   "Offline voice control for the 'verse", "79,179,232"),
    "hd2":  _theme("hd2", "Helldivers 2 Voice Control",
                   "Call your stratagems out loud", "255,212,0"),
    "ed":   _theme("ed", "Elite Dangerous Voice Control",
                   "Hands on the stick, commands in the air", "240,123,5"),
    "stbc": _theme("stbc", "Star Trek Bridge Crew Voice Control",
                   "Speak to your bridge", "204,153,204"),
}


def get(key: str, overrides: dict | None = None) -> GameTheme:
    """Look up a title's theme AND load its palette. Unknown keys fall back.

    A missing theme must never be the reason a tool refuses to open -- the
    user came here to talk to a game, not to debug our registry.
    """
    k = (key or "").lower()
    if k not in THEMES:
        k = "sc"
    apply(k, overrides)
    return THEMES[k]
