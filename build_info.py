"""
Build stamp for this copy.

FREE RELEASE
------------
This is given away, so the machinery that protected a paid product is gone:
no licence key, no one-PC activation, no per-recipient watermark to trace a
leak back to whoever leaked it. There is nothing to leak -- anyone who wants
a copy should have one.

What is left is a plain build stamp, so a bug report can say which version it
came from, and a name on the work.
"""

# Channels earlier than RELEASE get the loud "this will break" banner and
# a TESTER-tier license rather than a full one.
PRERELEASE_CHANNELS = ("PREALPHA", "ALPHA", "BETA")
CHANNEL_LABELS = {"PREALPHA": "PRE-ALPHA", "ALPHA": "ALPHA", "BETA": "BETA"}


def is_test_build() -> bool:
    """True for anything that is not a finished RELEASE build.

    Test builds (DEV / PREALPHA / ALPHA / BETA) never enforce the licence
    gate, the one-PC activation lock, or the integrity hard-stop. Those
    protect against strangers; a tester was handed this copy by us. The
    watermark and Copy ID still identify a leaked build, silently.
    """
    return CHANNEL != "RELEASE"

PRODUCT      = "Star Citizen Voice Control"
VERSION      = "4.4.0"
CHANNEL      = "FREE"             # nothing is gated on this any more
BUILD_ID     = "SCVC-FREE-4.4.0"
BUILD_DATE   = "2026-09-04"
COPY_ID      = "FREE"             # every copy is the same copy now
ISSUED_TO    = "Free release -- share it with anyone"
AUTHOR       = "Obly"
PUBLISHER    = "Obly"
COPYRIGHT    = "Made by Obly. Free to use and free to pass on."
SUPPORT      = ""                 # fill in before handing copies out

# Long-form watermark string. Embedded verbatim in the compiled exe, the
# shipped BUILD.txt, and config/commands.json's _build block, so stripping
# any one of them still leaves the others.
# A signature now, not a fingerprint. It used to encode which copy went to
# which person so a leak could be traced back; a free build has nothing to
# protect, so it just says who made it and which version this is.
WATERMARK = f"{PRODUCT} {VERSION} | by {AUTHOR} | free release"


def banner(lic: dict | None = None, days_left=None) -> str:
    """The stamped header printed at every startup."""
    bar = "=" * 62
    lines = [
        bar,
        f"  {PRODUCT.upper()}  v{VERSION}",
        bar,
        f"  Made by {AUTHOR}.  Free to use, free to pass on.",
        f"  Build     : {BUILD_ID}  ({BUILD_DATE})",
    ]
    lines += [
        bar,
        "  Star Citizen changes every patch, so some keys will be wrong.",
        "  Don't try a new command on a ship or cargo you'd hate to lose.",
    ]
    if SUPPORT:
        lines.append("  Something odd? " + SUPPORT)
    lines.append(bar)
    return "\n".join(lines)
