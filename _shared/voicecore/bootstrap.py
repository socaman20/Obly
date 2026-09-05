"""
Make `import voicecore` work from a sibling product folder, with no install.

The four tools live side by side:

    Products/
        _shared/voicecore/                <- this package
        Star Citizen Voice Control (live build)/
        Helldivers 2 Voice Control/
        Elite Dangerous Voice Control/
        Star Trek Bridge Crew Voice Control/

Importing this module puts `Products/_shared` on sys.path, so `voicecore`
resolves. Import it FIRST in a product's main.py:

    from voicecore import bootstrap   # noqa: F401  -- must come first

PyInstaller follows the import at build time and bakes the modules into the
exe, so a shipped build does not need this folder to exist on the customer's
machine. This only matters when running from source.

Deliberately does nothing if it cannot find the folder -- a product that has
been copied somewhere else should fail on the real import with a clear
ModuleNotFoundError, not on a confusing path error from here.
"""
import os
import sys


def _shared_root():
    """Walk up looking for a folder that contains voicecore/."""
    here = os.path.dirname(os.path.abspath(__file__))
    # normal case: we ARE inside _shared/voicecore
    candidate = os.path.dirname(here)
    if os.path.isdir(os.path.join(candidate, "voicecore")):
        return candidate
    # running from a product folder: look for a sibling _shared
    d = here
    for _ in range(5):
        d = os.path.dirname(d)
        c = os.path.join(d, "_shared")
        if os.path.isdir(os.path.join(c, "voicecore")):
            return c
    return None


def install():
    root = _shared_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)
    return root


PATH = install()
