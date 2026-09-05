"""
Phrase grammar -- write one line, get every way a player might say it.

Borrowed from how VoiceAttack/HCS author their voice triggers, because
hand-writing every phrasing does not scale and always misses some. See
`Products/VoiceAttack-HCS Competitive Analysis 2026-08-22.md`.

    [a;b;c]     alternatives      -> a, b, c
    [a;b;]      alternatives, and OPTIONAL (empty trailing branch)
    [word;]     just optional     -> "word", ""
    ;           at top level, separates whole alternative phrasings

So:

    "[open;bring up;pull up] [the;] mobiglas"

expands to 6 phrases, and:

    "[what is;whats] my [current;] speed; how fast am I going"

expands to 5.

Groups may nest. A phrase with no brackets and no top-level ';' comes back
unchanged, so every phrase written before this existed still works exactly
as it did -- this is additive, nothing had to be rewritten.

The '*' wildcard (prefix capture, see build_matchers in main.py) survives
expansion untouched: it is ordinary text as far as this module is concerned.
"""

MAX_EXPANSIONS = 400   # a single pattern producing more than this is a typo


class GrammarError(ValueError):
    """Raised with a human-readable reason -- the message reaches the user."""


def _split_top_level(text, sep):
    """Split on `sep`, ignoring any occurrence inside [ ] brackets."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "[":
            depth += 1
            current.append(ch)
        elif ch == "]":
            depth -= 1
            if depth < 0:
                raise GrammarError("a ']' has no matching '[' in: " + text)
            current.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if depth != 0:
        raise GrammarError("a '[' was never closed in: " + text)
    parts.append("".join(current))
    return parts


def _expand_one(pattern):
    """Expand a single pattern (no top-level ';') into a list of strings."""
    start = pattern.find("[")
    if start == -1:
        return [pattern]

    depth, end = 0, -1
    for i in range(start, len(pattern)):
        if pattern[i] == "[":
            depth += 1
        elif pattern[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise GrammarError("a '[' was never closed in: " + pattern)

    head = pattern[:start]
    body = pattern[start + 1:end]
    tail = pattern[end + 1:]

    branches = _split_top_level(body, ";")
    out = []
    for branch in branches:
        for rest in _expand_one(tail):
            for sub in _expand_one(branch):
                out.append(head + sub + rest)
                if len(out) > MAX_EXPANSIONS:
                    raise GrammarError(
                        "pattern expands to more than %d phrases, which is "
                        "almost always a typo: %s" % (MAX_EXPANSIONS, pattern))
    return out


def _tidy(s):
    """Collapse the double spaces an empty optional branch leaves behind."""
    return " ".join(s.split()).strip()


def expand(pattern):
    """Expand one authored phrase into every spoken variant, de-duplicated."""
    if not isinstance(pattern, str):
        raise GrammarError("a phrase must be text, got: %r" % (pattern,))
    seen, out = set(), []
    for chunk in _split_top_level(pattern, ";"):
        for variant in _expand_one(chunk):
            v = _tidy(variant)
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def expand_all(phrases):
    """Expand a list of authored phrases. Order preserved, duplicates dropped."""
    seen, out = set(), []
    for p in phrases:
        for v in expand(p):
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def expand_commands(commands):
    """Expand every command's phrases in place. Returns (before, after) counts.

    Errors name the command id, because 'a bracket is unclosed' is useless
    without knowing which of 50 commands it is in.
    """
    before = after = 0
    for cmd in commands:
        raw = cmd.get("phrases") or []
        before += len(raw)
        try:
            cmd["phrases"] = expand_all(raw)
        except GrammarError as e:
            raise GrammarError("command '%s': %s" % (cmd.get("id", "?"), e))
        after += len(cmd["phrases"])
    return before, after
