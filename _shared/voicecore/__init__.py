"""
voicecore -- the parts every one of the voice-control tools needs.

WHY THIS EXISTS
---------------
There are four of these tools now: Star Citizen, Helldivers 2, Elite
Dangerous, Star Trek Bridge Crew. Between them, 178 commands and 518
hand-written phrases. Every improvement made to one of them used to stop
there -- the phrase grammar, control schemes and swappable voice packs were
all built for Star Citizen and were invisible to the other three.

Nothing in here is game-specific. It is the machinery; the games bring the
commands.

WHAT IS IN HERE
---------------
    phrase_grammar   "[open;bring up] the mobiglas" -> every spoken variant
    control_scheme   what you SAY separated from what gets PRESSED
    voice_packs      swappable spoken acknowledgements, and real silence
    dictation        local speech-to-text, GPU, nothing leaves the machine
    vocabulary       the proper nouns a general recogniser has never heard

HOW A TOOL PICKS IT UP
----------------------
Each product's main.py does:

    from voicecore import bootstrap        # noqa
    from voicecore import phrase_grammar, control_scheme, voice_packs

`bootstrap` is what makes the import work from a sibling folder without
installing anything. PyInstaller resolves it at build time and bakes the
modules into the exe, so a shipped build has no dependency on this folder
existing on the customer's machine.

KEEP IT GAME-AGNOSTIC
---------------------
If something here needs to know about Star Citizen, it belongs in the Star
Citizen project, not here. `sc_keybinds.py` is the right example of what
stays out.
"""

__version__ = "1.0.0"

from . import phrase_grammar        # noqa: F401
from . import control_scheme        # noqa: F401

__all__ = ["phrase_grammar", "control_scheme", "voice_packs", "vocabulary"]


# voice_packs and vocabulary are the dictation half of this package, and the
# game tools never touch them. Importing them here meant every consumer paid
# for them -- including a published copy of a game tool, which has no business
# shipping a vocabulary of somebody's trading terms.
#
# Deferring costs nothing: `from voicecore import vocabulary` still works, the
# first time it is genuinely asked for.
def __getattr__(name):
    if name in ("voice_packs", "vocabulary", "dictation", "sidecar",
                "push_to_talk"):
        import importlib
        return importlib.import_module("." + name, __name__)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
