"""
Control schemes -- the middle layer between what you SAY and what gets PRESSED.

WHY
---
Commands used to weld the spoken phrase straight to a keystroke. That meant one
command set could only ever serve one physical layout: Obly's own X56 HOTAS
breaks 10 of 12 checked commands, and every player who moved an action onto a
stick button was unreachable. Adding a second device would have meant rewriting
all 50 commands.

VoiceAttack/HCS solve this by separating the layers, and ship 9+ device
schemes against one trigger set. This is that idea, with one difference that
matters: their schemes are pre-baked for hardware they chose, ours can be
GENERATED from the player's own Star Citizen bindings (see sc_keybinds.py).
They partner with the game. We partner with the player.

THE LAYERS
----------
    1. config/commands.json      what you say      phrases, grammar
    2. config/commands.json      what it means     display_name, category, ack
    3. config/schemes/*.json     what gets pressed type, keys, hold_ms, button

A scheme maps command id -> binding. Commands carry NO keys of their own, so
there is exactly one place a binding can live and it cannot drift out of sync
with a second copy.
"""
import io
import json
import os

# The fields a scheme owns. Anything here belongs in a scheme file, never in
# commands.json -- that split is what makes multiple layouts possible.
BINDING_FIELDS = ("type", "keys", "hold_ms", "button", "steps",
                  "key_label", "verified")

# A game may own an input shape nobody else has. Helldivers 2's stratagem
# "code" (the W/A/S/D sequence you tap out) is a physical input, so it
# belongs in a scheme -- but it means nothing to Star Citizen. Rather than
# growing BINDING_FIELDS with every game's private vocabulary, callers pass
# their own extras in. Nothing here has to know what a stratagem is.
def _fields(extra=None):
    return BINDING_FIELDS + tuple(extra or ())

DEFAULT_SCHEME = "keyboard_default"


class SchemeError(Exception):
    """Message reaches the user, so say what to do about it."""


def schemes_dir(base_dir):
    return os.path.join(str(base_dir), "config", "schemes")


def available(base_dir):
    d = schemes_dir(base_dir)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def load(base_dir, name):
    """Load one scheme file. Returns {command_id: {binding fields}}."""
    name = (name or DEFAULT_SCHEME).strip() or DEFAULT_SCHEME
    path = os.path.join(schemes_dir(base_dir), name + ".json")
    if not os.path.exists(path):
        have = available(base_dir)
        raise SchemeError(
            "control scheme '%s' not found.\n"
            "  Looked for: %s\n"
            "  Available : %s\n"
            "  Fix settings.control_scheme in config/commands.json."
            % (name, path, ", ".join(have) if have else "(none)"))
    try:
        doc = json.load(io.open(path, encoding="utf-8"))
    except ValueError as e:
        raise SchemeError("control scheme '%s' is not valid JSON: %s" % (name, e))
    return doc.get("bindings", {})


def apply(commands, bindings, scheme_name, extra_fields=None):
    """Merge a scheme's bindings onto the commands. Returns list of unbound ids.

    An unbound command is not an error -- it is a command this device layout
    genuinely cannot reach (the honest answer for a stick-only binding). It is
    dropped from matching so it cannot half-fire, and reported so the player
    knows why it did nothing.
    """
    unbound = []
    for cmd in commands:
        b = bindings.get(cmd["id"])
        if not b:
            unbound.append(cmd["id"])
            cmd["_unbound"] = True
            continue
        for f in _fields(extra_fields):
            if f in b:
                cmd[f] = b[f]
    return unbound


def extract(commands, extra_fields=None):
    """Pull the binding fields out of a command list into a scheme dict."""
    out = {}
    for cmd in commands:
        b = {f: cmd[f] for f in _fields(extra_fields) if f in cmd}
        if b:
            out[cmd["id"]] = b
    return out


def write(base_dir, name, bindings, description=""):
    d = schemes_dir(base_dir)
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, name + ".json")
    doc = {
        "_what_this_is": (
            "A control scheme: which physical input each voice command sends. "
            "Command ids and spoken phrases live in commands.json; only the "
            "bindings live here. Copy this file, edit the keys, and point "
            "settings.control_scheme at your copy to make the tool fit YOUR "
            "layout without touching a single phrase."),
        "name": name,
        "description": description,
        "bindings": bindings,
    }
    tmp = path + ".tmp"
    io.open(tmp, "w", encoding="utf-8", newline="").write(
        json.dumps(doc, indent=2, ensure_ascii=False))
    os.replace(tmp, path)
    return path
