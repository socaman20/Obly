"""Match Star Citizen names by how they sound, not how they are spelled.

WHY
---
These names are not English. Whisper writes down something English-shaped and
the letters come out wrong while the sound stays right:

    "art court"      ->  ArcCorp
    "terror gateway" ->  Terra Gateway
    "origin"         ->  Orison
    "new beverage"   ->  New Babbage

Character-level fuzzy matching scores those badly -- "art court" against
"arccorp" shares almost nothing letter for letter -- so a real destination was
being refused, or worse, swapped for a different place that happened to be
spelled more like the mistake. Comparing the sounds instead fixes the class of
problem rather than the individual cases.

This is a Metaphone-style key, kept deliberately small and readable so the
rules can be argued with. It is NOT a general English phoneticiser; it is
tuned to the sounds these names actually use, and every rule below earned its
place by fixing a real mis-hearing from his own recorded transcripts.
"""
from __future__ import annotations

import re

# Ordered: earlier rules win, so digraphs are consumed before single letters.
_DIGRAPHS = [
    ("ph", "F"), ("gh", "F"), ("ck", "K"), ("cc", "K"), ("ch", "K"),
    ("sh", "S"), ("th", "T"), ("wh", "W"), ("qu", "KW"), ("kn", "N"),
    ("wr", "R"), ("mb", "M"), ("dg", "J"), ("sc", "SK"),
]

_SINGLES = {
    "a": "A", "e": "A", "i": "A", "o": "A", "u": "A", "y": "A",
    "b": "B", "c": "K", "d": "T", "f": "F", "g": "K", "h": "",
    "j": "J", "k": "K", "l": "L", "m": "M", "n": "N", "p": "P",
    "q": "K", "r": "R", "s": "S", "t": "T", "v": "F", "w": "W",
    "x": "KS", "z": "S",
}


def key(text, keep_vowels=False):
    """A sound-shape for `text`.

    Vowels collapse to a single symbol rather than disappearing: dropping them
    entirely (as classic Soundex does) makes far too many short names collide
    -- Lo, Ita and Adir all reduce to almost nothing. Keeping one placeholder
    preserves the syllable count, which is most of what tells these names
    apart.

    Consonant choices worth knowing:
      c, k, q, g   -> K    microTech / microtake, ArcCorp / art court
      d, t         -> T    the pair Whisper confuses most in these names
      b, p         -> kept apart: Babbage vs passage stay distinct
      v, f         -> F    "beverage" and "Babbage" meet here
      s, z, soft c -> S
      h            -> dropped unless it starts a digraph
    """
    t = re.sub(r"[^a-z]", "", (text or "").lower())
    if not t:
        return ""

    out = []
    i = 0
    while i < len(t):
        pair = t[i:i + 2]
        for src, dst in _DIGRAPHS:
            if pair == src:
                out.append(dst)
                i += 2
                break
        else:
            out.append(_SINGLES.get(t[i], ""))
            i += 1

    k = "".join(out)
    k = re.sub(r"(.)\1+", r"\1", k)          # doubled sounds are one sound
    if not keep_vowels and k:
        # A leading vowel stays -- "Orison" and "Rison" are not the same word.
        # Interior ones go. Keeping them as a shared placeholder was tried and
        # was worse than useless: "origin" scored 85.7 against "Pyro - Cano"
        # and only 83.3 against "Orison", so the matcher offered a system in
        # another part of the 'verse. The consonant skeleton is the part
        # Whisper gets right, so it is the part that decides.
        k = k[0] + k[1:].replace("A", "")
    return k


def similarity(a, b):
    """0-100, how alike two strings sound. Uses whatever fuzz is available."""
    from rapidfuzz import fuzz
    ka, kb = key(a), key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 100.0
    return max(fuzz.ratio(ka, kb), fuzz.token_sort_ratio(ka, kb))


if __name__ == "__main__":
    # The corpus is his own transcripts, not invented examples.
    CASES = [
        ("art court", "ArcCorp"), ("terror gateway", "Terra Gateway"),
        ("origin", "Orison"), ("new beverage", "New Babbage"),
        ("laura ville", "Lorville"), ("loraville", "Lorville"),
        ("loreville", "Lorville"), ("orson", "Orison"),
        ("microtake", "microTech"), ("pyrogate way", "Pyro Gateway"),
        ("area eighteen", "Area 18"), ("yella", "Yela"),
    ]
    print("%-18s %-18s %-12s %-12s %s"
          % ("HEARD", "MEANT", "key(heard)", "key(meant)", "sounds-alike"))
    for said, meant in CASES:
        print("  %-16s %-18s %-12s %-12s %5.1f"
              % (said, meant, key(said), key(meant), similarity(said, meant)))
