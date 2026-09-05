"""
Pop-out editors: rebind a key, or add a command, without leaving the page.

WHY MODALS AND NOT A PAGE
-------------------------
Editing a command is something you do *to a row you are looking at*. Sending
someone to another page to do it loses their place, their search, and their
scroll position, and they have to find the row again afterwards. A pop-out
keeps the list underneath and puts them back exactly where they were.

WHERE THE EDITS GO
------------------
Never into config/commands.json or a scheme file. Both ship with the product
and get replaced on update, so anything a player put there would vanish. Their
rebinds and their own commands live in their own file -- same rule as their
disabled list and their colours.
"""
from __future__ import annotations

import customtkinter as ctk

from .theme import Ink, Metric, Type
from .widgets import Body, Eyebrow, Heading, KeyCaps, danger, ghost, primary


# Tk reports keysyms; the engine wants the names pydirectinput/keyboard use.
_KEYSYM = {
    "Control_L": "ctrlleft", "Control_R": "ctrlright",
    "Alt_L": "altleft", "Alt_R": "altright",
    "Shift_L": "shiftleft", "Shift_R": "shiftright",
    "space": "space", "Return": "enter", "Escape": "esc",
    "Prior": "pageup", "Next": "pagedown", "BackSpace": "backspace",
    "Delete": "delete", "Tab": "tab", "Up": "up", "Down": "down",
    "Left": "left", "Right": "right",
}


def keysym_to_name(keysym: str) -> str:
    return _KEYSYM.get(keysym, keysym.lower())


class Modal(ctk.CTkToplevel):
    """A themed pop-out that owns focus until it is answered."""

    WIDTH = 460
    HEIGHT = 380

    def __init__(self, parent, theme, title: str):
        super().__init__(parent)
        self.theme = theme
        self.result = None

        self.title(title)
        self.configure(fg_color=Ink.BG)
        self.resizable(False, False)

        # Centre on the parent window, not the screen -- on a multi-monitor
        # setup a screen-centred dialog can open on the wrong display.
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.WIDTH) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.HEIGHT) // 3
        self.geometry("%dx%d+%d+%d" % (self.WIDTH, self.HEIGHT, max(0, x), max(0, y)))

        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=Metric.PAD * 1.25, pady=(Metric.PAD * 1.25, 0))
        ctk.CTkFrame(head, height=2, width=30, corner_radius=1,
                     fg_color=theme.accent).pack(anchor="w", pady=(0, 8))
        Heading(head, title, size=17).pack(anchor="w")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True,
                       padx=Metric.PAD * 1.25, pady=Metric.PAD)

        self.foot = ctk.CTkFrame(self, fg_color="transparent")
        self.foot.pack(fill="x", padx=Metric.PAD * 1.25,
                       pady=(0, Metric.PAD * 1.25))

        self.msg = Body(self.body, "", dim=True, wrap=self.WIDTH - 60)

    def _cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()

    def _done(self, value):
        self.result = value
        self.grab_release()
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result

    # -- shared field helpers ------------------------------------------------

    def field(self, label, placeholder="", value=""):
        Eyebrow(self.body, label).pack(anchor="w", pady=(Metric.PAD_SM, 4))
        e = ctk.CTkEntry(
            self.body, placeholder_text=placeholder, height=32,
            font=ctk.CTkFont(family=Type.UI, size=12),
            fg_color=Ink.SURFACE_2, border_color=Ink.BORDER, border_width=1,
            corner_radius=Metric.RADIUS_SM, text_color=Ink.TEXT,
            placeholder_text_color=Ink.TEXT_MUTE,
        )
        if value:
            e.insert(0, value)
        e.pack(fill="x")
        return e

    def key_capture(self, label, keys):
        """A button that listens for the next key combination pressed."""
        Eyebrow(self.body, label).pack(anchor="w", pady=(Metric.PAD_SM, 4))
        wrap = ctk.CTkFrame(self.body, fg_color="transparent")
        wrap.pack(fill="x")

        state = {"keys": list(keys or [])}
        btn = ctk.CTkButton(
            wrap, height=34, width=250,
            text=" + ".join(k.upper() for k in state["keys"]) or "click, then press a key",
            font=ctk.CTkFont(family=Type.MONO, size=12),
            fg_color=Ink.SURFACE_2, hover_color=Ink.SURFACE_3,
            text_color=Ink.TEXT, border_color=Ink.BORDER, border_width=1,
            corner_radius=Metric.RADIUS_SM,
        )

        def listen():
            btn.configure(text="press a key…", text_color=self.theme.accent)
            held = []

            def grab(event):
                name = keysym_to_name(event.keysym)
                # Modifiers first, then the key -- "ALT + Y", not "Y + ALT".
                if name in ("ctrlleft", "ctrlright", "altleft", "altright",
                            "shiftleft", "shiftright"):
                    if name not in held:
                        held.append(name)
                    btn.configure(text=" + ".join(k.upper() for k in held) + " + …")
                    return "break"
                state["keys"] = held + [name]
                btn.configure(text=" + ".join(k.upper() for k in state["keys"]),
                              text_color=Ink.TEXT)
                self.unbind("<KeyPress>")
                self.unbind("<KeyRelease>")
                return "break"

            self.bind("<KeyPress>", grab)
            self.focus_set()

        btn.configure(command=listen)
        btn.pack(side="left")
        return state


class KeyEditDialog(Modal):
    """Rebind one existing command."""

    HEIGHT = 330

    def __init__(self, parent, theme, cmd, has_override):
        super().__init__(parent, theme, "Change key")
        self.cmd = cmd

        Body(self.body, cmd.get("display_name") or cmd.get("id", "?"),
             wrap=self.WIDTH - 60).pack(anchor="w")
        Body(self.body,
             "Set the key this command should press. Use the key your game is "
             "actually bound to.",
             dim=True, wrap=self.WIDTH - 60).pack(anchor="w", pady=(2, 0))

        self.keys = self.key_capture("Key", cmd.get("keys"))

        Eyebrow(self.body, "Mode").pack(anchor="w", pady=(Metric.PAD_SM, 4))
        self.mode = ctk.CTkSegmentedButton(
            self.body, values=["Tap", "Hold"],
            font=ctk.CTkFont(family=Type.UI, size=11),
            selected_color=theme.accent, selected_hover_color=theme.accent_dim,
            unselected_color=Ink.SURFACE_2, unselected_hover_color=Ink.SURFACE_3,
            text_color=Ink.TEXT, fg_color=Ink.SURFACE_2,
        )
        self.mode.set("Hold" if cmd.get("type") == "hold" else "Tap")
        self.mode.pack(anchor="w", fill="x")

        self.msg.pack(anchor="w", pady=(Metric.PAD_SM, 0))

        primary(self.foot, "Save", self._save, Ink.ACTION, Ink.ACTION_BRIGHT,
                Ink.ACTION_INK, width=110).pack(side="left")
        ghost(self.foot, "Cancel", self._cancel, width=90).pack(
            side="left", padx=(Metric.PAD_SM, 0))
        if has_override:
            # Only offered when there is something to undo. A "reset" that does
            # nothing is a button that teaches people not to trust buttons.
            danger(self.foot, "Reset to default",
                   lambda: self._done({"reset": True}), width=150).pack(side="right")

    def _save(self):
        if not self.keys["keys"]:
            self.msg.configure(text="Press a key first — click the button above, "
                                    "then press the key you want.",
                               text_color=Ink.WARN)
            return
        self._done({"keys": self.keys["keys"],
                    "type": "hold" if self.mode.get() == "Hold" else "tap"})


class CommandDialog(Modal):
    """Create a command of your own, in one pop-out."""

    HEIGHT = 560

    def __init__(self, parent, theme, categories=None, cmd=None):
        editing = cmd is not None
        super().__init__(parent, theme,
                         "Edit command" if editing else "Add a command")
        cmd = cmd or {}

        self.name = self.field("Name", "Deploy landing gear",
                               cmd.get("display_name", ""))
        self.cat = self.field("Category", (categories or ["My Commands"])[0],
                              cmd.get("category", ""))
        self.keys = self.key_capture("Key to press", cmd.get("keys"))

        Eyebrow(self.body, "Mode").pack(anchor="w", pady=(Metric.PAD_SM, 4))
        self.mode = ctk.CTkSegmentedButton(
            self.body, values=["Tap", "Hold"],
            font=ctk.CTkFont(family=Type.UI, size=11),
            selected_color=theme.accent, selected_hover_color=theme.accent_dim,
            unselected_color=Ink.SURFACE_2, unselected_hover_color=Ink.SURFACE_3,
            text_color=Ink.TEXT, fg_color=Ink.SURFACE_2,
        )
        self.mode.set("Hold" if cmd.get("type") == "hold" else "Tap")
        self.mode.pack(anchor="w", fill="x")

        Eyebrow(self.body, "What you say  (one phrase per line)").pack(
            anchor="w", pady=(Metric.PAD_SM, 4))
        self.phrases = ctk.CTkTextbox(
            self.body, height=92, fg_color=Ink.SURFACE_2,
            border_color=Ink.BORDER, border_width=1,
            corner_radius=Metric.RADIUS_SM, wrap="word",
            font=ctk.CTkFont(family=Type.UI, size=12), text_color=Ink.TEXT,
        )
        self.phrases.pack(fill="x")
        if cmd.get("phrases"):
            self.phrases.insert("1.0", "\n".join(cmd["phrases"]))

        self.msg.pack(anchor="w", pady=(Metric.PAD_SM, 0))

        primary(self.foot, "Save command", self._save, Ink.ACTION,
                Ink.ACTION_BRIGHT, Ink.ACTION_INK, width=150).pack(side="left")
        ghost(self.foot, "Cancel", self._cancel, width=90).pack(
            side="left", padx=(Metric.PAD_SM, 0))

    def _save(self):
        name = self.name.get().strip()
        phrases = [p.strip() for p in
                   self.phrases.get("1.0", "end").splitlines() if p.strip()]

        # Say what is wrong and how to fix it -- never just refuse.
        if not name:
            self.msg.configure(text="Give the command a name first.",
                               text_color=Ink.WARN); return
        if not self.keys["keys"]:
            self.msg.configure(text="Click the key button, then press the key "
                                    "this command should send.",
                               text_color=Ink.WARN); return
        if not phrases:
            self.msg.configure(text="Add at least one phrase you would say "
                                    "out loud.", text_color=Ink.WARN); return

        self._done({
            "id": "custom_" + "_".join(name.lower().split()),
            "display_name": name,
            "category": self.cat.get().strip() or "My Commands",
            "phrases": phrases,
            "keys": self.keys["keys"],
            "type": "hold" if self.mode.get() == "Hold" else "tap",
            "key_label": " + ".join(k.upper() for k in self.keys["keys"]),
            "verified": True,
            "notes": "Created by you.",
        })
