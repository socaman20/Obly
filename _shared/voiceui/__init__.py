"""
voiceui -- the window every voice-control tool opens into.

WHY THIS EXISTS
---------------
`voicecore` made the engine shared. This does the same for the interface.

Until 2026-09-04 none of the four tools had a GUI at all: they were console
apps driven by a push-to-talk key, which meant the only person who could really
operate one was the person who built it. Every improvement to how a tool
*looks* would have stopped at one title, the same way the phrase grammar and
control schemes used to.

WHAT IS IN HERE
---------------
    theme      one palette, one accent per game -- the only file with hex codes
    widgets    cards, pills, keycaps, search, meters -- the small pieces
    shell      the window: sidebar, page area, status bar
    pages      the screens every title shares: Listen, Commands, My Commands, About

HOW A TOOL PICKS IT UP
----------------------
    from voicecore import bootstrap            # puts _shared on sys.path
    from voiceui import AppShell, theme
    from voiceui.pages import RunPage, CommandsPage, CustomPage, AboutPage

    shell = AppShell(theme.get("sc"), version="4.4.0")
    shell.commands = my_commands               # data the pages read
    shell.controller = my_engine_adapter
    shell.add_page(RunPage); shell.add_page(CommandsPage)
    shell.start()

KEEP IT GAME-AGNOSTIC
---------------------
Same rule as voicecore: if something in here needs to know what a mobiGlas or a
stratagem is, it belongs in that game's project. These pages take data, not
knowledge. Adding a fifth title should mean one entry in `theme.THEMES` and a
`gui.py` that wires it up -- nothing in this package should have to change.
"""

__version__ = "1.0.0"

from . import theme                  # noqa: F401

__all__ = ["theme", "AppShell", "Page", "pages", "widgets"]


# AppShell and Page live in shell.py, which imports CustomTkinter, which
# imports tkinter. Importing them here meant that ANY use of this package --
# `from voiceui.store import CustomStore`, `from voiceui.datacache import
# DataCache` -- pulled in the whole Tk interface. Harmless from source; fatal
# in a packaged build that has no Tk in it, and it is why the webview app had
# to load store.py by file path to avoid the package entirely.
#
# Deferring the import costs nothing: `from voiceui import AppShell` still
# works exactly as before, the first time it is actually asked for.
def __getattr__(name):
    if name in ("AppShell", "Page"):
        from . import shell
        return getattr(shell, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
