"""
Where a player's own commands live.

WHY A SEPARATE FILE
-------------------
User-authored commands do NOT go into config/commands.json. That file ships
with the product and gets replaced on every update -- writing to it means an
update silently eats everything the player added. Their commands live in
config/my_commands.json, which we never overwrite.

WHY THE WRITE LOOKS LIKE THIS
-----------------------------
`open(path, "w")` truncates the file the instant it is called. If anything goes
wrong between that moment and the write completing -- an exception, a crash, a
power cut -- the file is gone, not stale. That is exactly how the Business
Meeting Log was destroyed once already.

So: serialise fully, write to a temporary file beside the target, flush to
disk, then `os.replace()` it over the original. On every OS we care about that
last step is atomic -- the reader sees the old file or the new one, never a
half-written one, and a failure anywhere earlier leaves the original intact.
"""
from __future__ import annotations

import io
import json
import os
import tempfile


def atomic_write_json(path, doc, indent=2):
    """Write a JSON document without ever leaving a truncated file behind.

    Same temp-file + os.replace discipline as CustomStore.save, exposed so a
    product can write back its own config the safe way. Keeps LF endings to
    match the config files that ship beside it.
    """
    text = json.dumps(doc, indent=indent, ensure_ascii=False)
    folder = os.path.dirname(os.path.abspath(str(path))) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cfg.", suffix=".tmp", dir=folder)
    try:
        with io.open(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class CustomStore:
    """A player's own commands and their on/off choices, saved atomically.

    Two things live here, and both for the same reason -- they are the user's,
    not ours, so an update must never touch them:

        commands   the ones they wrote themselves
        disabled   the built-in ones they have switched OFF

    Disabling matters more than it sounds. `self_destruct` fires on Backspace
    and answers to "blow yourself up"; `cut_all_power` answers to "go dark".
    A player who never wants those reachable by voice should be able to say so
    once, rather than hoping the recogniser never mishears.
    """

    def __init__(self, path):
        self.path = str(path)
        self._items: list[dict] = []
        self._disabled: set[str] = set()
        self._theme: dict = {}
        self._keys: dict = {}
        self.load()

    # ------------------------------------------------------------- reading

    def load(self):
        if not os.path.exists(self.path):
            # Reset everything, not just commands -- load() can be called again
            # after the file is gone, and stale overrides would survive it.
            self._items = []
            self._disabled = set()
            self._theme = {}
            self._keys = {}
            return
        try:
            with io.open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
        except (ValueError, OSError):
            # A corrupt file must not stop the app opening. Keep it on disk so
            # it can be recovered by hand, and carry on with none loaded.
            self._items = []
            self._disabled = set()
            self._theme = {}
            self._keys = {}
            return
        if isinstance(doc, dict):
            items = doc.get("commands", [])
            self._disabled = set(doc.get("disabled") or [])
            self._theme = dict(doc.get("theme") or {})
            self._keys = dict(doc.get("keys") or {})
        else:
            items = doc
            self._disabled = set()
            self._theme = {}
            self._keys = {}
        self._items = [c for c in items if isinstance(c, dict)]

    def all(self) -> list[dict]:
        return list(self._items)

    def __len__(self):
        return len(self._items)

    # ------------------------------------------------------- on/off state

    def is_enabled(self, command_id: str) -> bool:
        return command_id not in self._disabled

    def set_enabled(self, command_id: str, enabled: bool):
        if enabled:
            self._disabled.discard(command_id)
        else:
            self._disabled.add(command_id)
        self.save()

    def disabled_ids(self) -> set[str]:
        return set(self._disabled)

    # ------------------------------------------------------ colour overrides

    def theme(self) -> dict:
        """The user's colour overrides, layered over the game palette."""
        return dict(self._theme)

    def set_theme(self, overrides: dict):
        self._theme = {k: v for k, v in (overrides or {}).items() if v}
        self.save()

    def clear_theme(self):
        self._theme = {}
        self.save()

    # ----------------------------------------------------- keybind overrides

    def key_override(self, command_id: str):
        """The player's own binding for one command, or None for the default."""
        return self._keys.get(command_id)

    def set_key_override(self, command_id: str, keys: list, kind: str = "tap"):
        self._keys[command_id] = {"keys": list(keys), "type": kind}
        self.save()

    def clear_key_override(self, command_id: str):
        self._keys.pop(command_id, None)
        self.save()

    def apply_key_overrides(self, commands):
        """Layer the player's rebinds onto the loaded commands, in place.

        Called AFTER the control scheme, so their choice wins over the shipped
        binding. Their rebinds live in their own file rather than in the scheme,
        because a scheme file ships with the product and gets replaced -- the
        exact reason a player's work must never be stored in one.
        """
        changed = 0
        for cmd in commands:
            over = self._keys.get(cmd.get("id"))
            if not over:
                continue
            cmd["keys"] = list(over.get("keys") or [])
            cmd["type"] = over.get("type", "tap")
            cmd["key_label"] = " + ".join(k.upper() for k in cmd["keys"])
            cmd["_rebound"] = True          # so the UI can mark it
            changed += 1
        return changed

    def enabled_only(self, commands) -> list[dict]:
        """Filter a command list down to what should actually be matchable.

        The engine gets this, never the raw list -- a command switched off must
        not be able to fire at all, not merely be hidden from the page.
        """
        return [c for c in commands if c.get("id") not in self._disabled]

    # ------------------------------------------------------------- writing

    def add(self, cmd: dict):
        """Add or replace by id, then persist."""
        cid = cmd.get("id")
        self._items = [c for c in self._items if c.get("id") != cid]
        self._items.append(cmd)
        self.save()

    def remove(self, cid: str):
        self._items = [c for c in self._items if c.get("id") != cid]
        self.save()

    def save(self):
        payload = {
            "_readme": (
                "This file is yours. Product updates never overwrite it. "
                "You can edit it here in Notepad, or use the app -- both end "
                "up in the same place, and the app is easier. "
                "'commands' are voice commands you created: each needs a "
                "display_name, at least one phrase, and the keys to press. "
                "'disabled' is a list of command ids you have switched OFF, "
                "including built-in ones -- anything listed there is not "
                "matched at all and cannot fire. Remove an id from that list "
                "to turn the command back on. "
                "'theme' holds any colours you changed on the Appearance "
                "page; delete that block to go back to the built-in look. "
                "'keys' holds any command you rebound yourself: "
                "{\"command_id\": {\"keys\": [\"n\"], \"type\": \"tap\"}}. "
                "Remove an entry to go back to the shipped key."
            ),
            "commands": self._items,
            "disabled": sorted(self._disabled),
            "keys": self._keys,
            "theme": self._theme,
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)

        folder = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(folder, exist_ok=True)

        fd, tmp = tempfile.mkstemp(prefix=".my_commands.", suffix=".tmp",
                                   dir=folder)
        try:
            with io.open(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())      # survive a power cut, not just a crash
            os.replace(tmp, self.path)    # atomic: old or new, never half
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
