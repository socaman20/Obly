"""
Settings, as controls instead of a text file.

WHY
---
Every one of these tools kept its settings in config/commands.json, which meant
changing your push-to-talk key was: find the folder, open a JSON file in
Notepad, find the right line, edit it without breaking a comma, save. That is
fine for the person who wrote it and hostile to everybody else. A missing comma
gives them a parse error instead of a working app.

So: real controls. Checkboxes, dropdowns, a slider, and a key-capture button
that just listens for the key you press. The JSON file stays exactly where it
was and stays readable -- it is the fallback for someone who wants it, not the
interface for someone who doesn't.

SIMPLE vs ADVANCED
------------------
Two tiers, because the settings genuinely split in two:

  SIMPLE    what a player changes on purpose -- push-to-talk key, mic,
            spoken acknowledgements, recognition model
  ADVANCED  what only gets touched to diagnose something -- match threshold,
            compute type, thread count, step timing

Hiding the second group is not dumbing down. It is telling the truth about
which dials are meant for them, so they can find the two that are without
reading past twelve that aren't. Advanced is one click away, never hidden.

GAME-AGNOSTIC
-------------
This module renders a schema; it does not know what any setting means. Each
product declares its own list of `Setting` objects and passes them in, so
Helldivers can expose a stratagem timing that Star Citizen has never heard of
without a line changing here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import customtkinter as ctk

from .shell import Page
from .theme import Ink, Metric, Type
from .widgets import Body, Card, Eyebrow, Heading, ghost, primary

SIMPLE = "simple"
ADVANCED = "advanced"


@dataclass
class Setting:
    """One control. `key` is the settings dict key it reads and writes."""
    key: str
    label: str
    kind: str                      # bool | choice | int | text | key
    help: str = ""
    tier: str = SIMPLE
    group: str = "General"
    choices: list = field(default_factory=list)
    minimum: int = 0
    maximum: int = 100
    suffix: str = ""


class SettingsPage(Page):
    NAV_LABEL = "Settings"
    TITLE = "Settings"
    SUBTITLE = "Change how it listens. Everything here is also in your config file."

    def build(self):
        self._widgets: dict[str, Any] = {}
        self._tier = SIMPLE

        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.pack(fill="x")

        self.tier_btn = ctk.CTkSegmentedButton(
            top, values=["Simple", "Advanced"], command=self._switch_tier,
            font=ctk.CTkFont(family=Type.UI, size=11),
            selected_color=self.theme.accent,
            selected_hover_color=self.theme.accent_dim,
            unselected_color=Ink.SURFACE_2,
            unselected_hover_color=Ink.SURFACE_3,
            text_color=Ink.TEXT, fg_color=Ink.SURFACE_2,
        )
        self.tier_btn.set("Simple")
        self.tier_btn.pack(side="left")

        self.saved = Body(top, "", dim=True)
        self.saved.pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            scrollbar_button_color=Ink.SURFACE_3,
            scrollbar_button_hover_color=Ink.BORDER,
        )
        self.scroll.pack(fill="both", expand=True, pady=(Metric.PAD, 0))

        actions = ctk.CTkFrame(self.content, fg_color="transparent")
        actions.pack(fill="x", pady=(Metric.PAD, 0))
        primary(actions, "Save Settings", self._save, Ink.GOLD,
                Ink.GOLD_BRIGHT, Ink.OBSIDIAN,
                width=160).pack(side="left")
        ghost(actions, "Reload", self._render).pack(side="left",
                                                    padx=(Metric.PAD_SM, 0))
        self.note = Body(actions, "", dim=True)
        self.note.pack(side="left", padx=(Metric.PAD, 0))

        self._render()

    # ------------------------------------------------------------ plumbing

    @property
    def schema(self) -> list:
        return getattr(self.shell, "settings_schema", []) or []

    @property
    def values(self) -> dict:
        return getattr(self.shell, "settings", {}) or {}

    @property
    def on_save(self) -> Callable | None:
        return getattr(self.shell, "settings_save", None)

    def on_show(self):
        self._render()

    def _switch_tier(self, choice):
        self._tier = ADVANCED if choice == "Advanced" else SIMPLE
        self._render()

    # ------------------------------------------------------------ rendering

    def _render(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._widgets.clear()
        self.saved.configure(text="")

        shown = [s for s in self.schema
                 if self._tier == ADVANCED or s.tier == SIMPLE]
        if not shown:
            Body(self.scroll, "No settings declared for this tool.",
                 dim=True).pack(anchor="w")
            return

        groups: dict[str, list] = {}
        for s in shown:
            groups.setdefault(s.group, []).append(s)

        for group, items in groups.items():
            card = Card(self.scroll, group, rim=self.theme.accent)
            card.pack(fill="x", pady=(0, Metric.GAP))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=Metric.PAD,
                       pady=(Metric.PAD_SM, Metric.PAD))
            for s in items:
                self._row(inner, s)

        if self._tier == SIMPLE:
            self.note.configure(
                text="Showing the settings most people change. "
                     "Advanced has the diagnostic ones.")
        else:
            self.note.configure(
                text="Advanced: only change these if something is misbehaving.")

    def _row(self, parent, s: Setting):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        Heading(left, s.label, size=12).pack(anchor="w")
        if s.help:
            ctk.CTkLabel(
                left, text=s.help,
                font=ctk.CTkFont(family=Type.UI, size=11),
                text_color=Ink.TEXT_MUTE, anchor="w", justify="left",
                wraplength=520,
            ).pack(anchor="w", pady=(1, 0))

        value = self.values.get(s.key)
        holder = ctk.CTkFrame(row, fg_color="transparent")
        holder.pack(side="right", padx=(Metric.PAD, 0))

        if s.kind == "bool":
            var = ctk.BooleanVar(value=bool(value))
            ctk.CTkSwitch(
                holder, text="", variable=var, width=44,
                progress_color=self.theme.accent,
                button_color=Ink.TEXT, button_hover_color=Ink.TEXT,
                fg_color=Ink.SURFACE_3,
            ).pack()
            self._widgets[s.key] = ("bool", var)

        elif s.kind == "choice":
            var = ctk.StringVar(value=str(value) if value is not None else "")
            ctk.CTkOptionMenu(
                holder, values=[str(c) for c in s.choices], variable=var,
                width=190, height=32,
                font=ctk.CTkFont(family=Type.UI, size=11),
                fg_color=Ink.SURFACE_2, button_color=Ink.SURFACE_3,
                button_hover_color=Ink.BORDER, text_color=Ink.TEXT,
                dropdown_fg_color=Ink.SURFACE_2,
                dropdown_hover_color=Ink.SURFACE_3,
                dropdown_text_color=Ink.TEXT,
                corner_radius=Metric.RADIUS_SM,
            ).pack()
            self._widgets[s.key] = ("choice", var)

        elif s.kind == "int":
            box = ctk.CTkFrame(holder, fg_color="transparent")
            box.pack()
            readout = ctk.CTkLabel(
                box, text="%s%s" % (value, s.suffix), width=64,
                font=ctk.CTkFont(family=Type.MONO, size=11),
                text_color=Ink.TEXT,
            )
            slider = ctk.CTkSlider(
                box, from_=s.minimum, to=s.maximum, width=180,
                number_of_steps=max(1, s.maximum - s.minimum),
                progress_color=self.theme.accent,
                button_color=self.theme.accent,
                button_hover_color=self.theme.accent_dim,
                fg_color=Ink.SURFACE_3,
                command=lambda v, r=readout, suf=s.suffix:
                    r.configure(text="%d%s" % (int(v), suf)),
            )
            try:
                slider.set(int(value))
            except (TypeError, ValueError):
                slider.set(s.minimum)
            slider.pack(side="left")
            readout.pack(side="left", padx=(Metric.PAD_SM, 0))
            self._widgets[s.key] = ("int", slider)

        elif s.kind == "key":
            # Press-the-key capture. Typing "right ctrl" correctly is a thing
            # we should never have asked anyone to do.
            btn = ctk.CTkButton(
                holder, text=str(value or "click, then press a key"),
                width=190, height=32,
                font=ctk.CTkFont(family=Type.MONO, size=11),
                fg_color=Ink.SURFACE_2, hover_color=Ink.SURFACE_3,
                text_color=Ink.TEXT, border_color=Ink.BORDER, border_width=1,
                corner_radius=Metric.RADIUS_SM,
            )
            btn.configure(command=lambda b=btn, k=s.key: self._capture(b, k))
            btn.pack()
            self._widgets[s.key] = ("key", btn)

        else:                                              # text
            entry = ctk.CTkEntry(
                holder, width=190, height=32,
                font=ctk.CTkFont(family=Type.UI, size=11),
                fg_color=Ink.SURFACE_2, border_color=Ink.BORDER,
                border_width=1, corner_radius=Metric.RADIUS_SM,
                text_color=Ink.TEXT,
            )
            if value is not None:
                entry.insert(0, str(value))
            entry.pack()
            self._widgets[s.key] = ("text", entry)

    # -------------------------------------------------------- key capture

    def _capture(self, btn, key):
        btn.configure(text="press a key...", text_color=self.theme.accent)

        def done(event):
            name = _keysym_to_name(event.keysym)
            btn.configure(text=name, text_color=Ink.TEXT)
            self.winfo_toplevel().unbind("<Key>", binding)
            btn._captured = name

        binding = self.winfo_toplevel().bind("<Key>", done)
        self.winfo_toplevel().focus_set()

    # --------------------------------------------------------------- save

    def _save(self):
        save = self.on_save
        if save is None:
            self.saved.configure(text="Nothing to save to.",
                                 text_color=Ink.CRIT)
            return

        new = {}
        for key, (kind, w) in self._widgets.items():
            if kind == "bool":
                new[key] = bool(w.get())
            elif kind == "choice":
                new[key] = w.get()
            elif kind == "int":
                new[key] = int(w.get())
            elif kind == "key":
                new[key] = getattr(w, "_captured", None) or w.cget("text")
            else:
                new[key] = w.get()

        try:
            save(new)
        except Exception as exc:
            self.saved.configure(text="Could not save: %s" % exc,
                                 text_color=Ink.CRIT)
            return

        self.values.update(new)
        self.saved.configure(text="Saved. Restart listening to apply.",
                             text_color=Ink.GOOD)


# Tk reports keysyms; the engine wants the names pydirectinput/keyboard use.
_KEYSYM = {
    "Control_L": "left ctrl", "Control_R": "right ctrl",
    "Alt_L": "left alt", "Alt_R": "right alt",
    "Shift_L": "left shift", "Shift_R": "right shift",
    "space": "space", "Return": "enter", "Escape": "esc",
    "Prior": "page up", "Next": "page down",
    "BackSpace": "backspace", "Delete": "delete", "Tab": "tab",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
}


def _keysym_to_name(keysym: str) -> str:
    if keysym in _KEYSYM:
        return _KEYSYM[keysym]
    if len(keysym) == 1:
        return keysym.lower()
    return keysym.lower()
