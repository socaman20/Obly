"""MOVED. This lives in Products/_shared/voicecore/ now.

All four voice-control tools share it, so improving it improves all of them
instead of only this one. This file stays as a redirect so nothing that
imported the old name breaks.
"""
import os
import sys

_shared = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                       "..", "_shared"))
if os.path.isdir(_shared) and _shared not in sys.path:
    sys.path.insert(0, _shared)

from voicecore.phrase_grammar import *          # noqa: F401,F403,E402
from voicecore import phrase_grammar as _real   # noqa: E402

# re-export the names `import *` skips (leading underscore, and constants)
for _n in dir(_real):
    if _n not in globals():
        globals()[_n] = getattr(_real, _n)
