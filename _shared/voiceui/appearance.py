"""
Appearance: let the player recolour the whole app.

WHY
---
Learned from the competitor teardown on 2026-09-04. Kabutopz's app ships a
CUSTOMIZE page with six named presets and a full colour picker on every token,
saved per user -- and that is the right instinct. Our four tools each wear their
own game's colours, which is a better *default* than one generic theme, but a
default is not the same as a choice. Someone playing at 3am who wants the whole
thing darker, or who is colourblind on our accent, should not have to accept our
taste.

So: presets, plus a picker on every token, applied live, saved in the player's
own file. Their choice always wins over ours.

WHAT IS NOT EDITABLE, AND WHY
-----------------------------
Status colours -- good / warn / critical -- stay ours. "Make the critical colour
green" is not a preference, it is a way to miss a warning about a command that
is about to fire Backspace at your ship. Everything structural is editable;
the four colours that mean something are not.
"""
from __future__ import annotations

from tkinter import colorchooser

import customtkinter as ctk

from . import theme as theme_mod
from .shell import Page
from .theme import EDITABLE, PALETTES, Ink, Metric, Type
from .widgets import Body, Card, Heading, ghost, primary


# Named starting points. The four game palettes are already available as the
# product default, so these are the "I want something else" options.
PRESETS = {
    "Game default":    None,                      # whatever this title ships
    "Midnight":        dict(BG="#0b0f14", SURFACE="#111821", SURFACE_2="#151f2b",
                            BORDER="#263341", TEXT="#edf3f8", TEXT_MUTE="#8493a3",
                            ACTION="#4da3ff"),
    "Blackout":        dict(BG="#050505", SURFACE="#0d0d0d", SURFACE_2="#151515",
                            BORDER="#303030", TEXT="#f4f4f4", TEXT_MUTE="#8e8e8e",
                            ACTION="#e8e8e8"),
    "Nebula":          dict(BG="#0d0913", SURFACE="#171021", SURFACE_2="#21172f",
                            BORDER="#3a2851", TEXT="#f4edff", TEXT_MUTE="#9d8caf",
                            ACTION="#a970ff"),
    "Signal":          dict(BG="#061014", SURFACE="#0b1b22", SURFACE_2="#102831",
                            BORDER="#204452", TEXT="#ebfbff", TEXT_MUTE="#82a7b0",
                            ACTION="#34d7ff"),
    "Ember":           dict(BG="#120d08", SURFACE="#1c150e", SURFACE_2="#291e13",
                            BORDER="#4b3824", TEXT="#fff4e8", TEXT_MUTE="#ad9984",
                            ACTION="#ffad42"),
    "High contrast":   dict(BG="#000000", SURFACE="#0a0a0a", SURFACE_2="#171717",
                            BORDER="#6a6a6a", TEXT="#ffffff", TEXT_MUTE="#c4c4c4",
                            ACTION="#ffd400"),
}


class AppearancePage(Page):
    NAV_LABEL = "Appearance"
    TITLE = "Appearance"
    SUBTITLE = ("Every colour here is yours to change. Your choices are saved "
                "in your own file and survive updates.")

    def build(self):
        self._draft = dict(self._store_theme())

        # ---- presets
        pcard = Card(self.content, "Start from a preset", rim=self.theme.accent)
        pcard.pack(fill="x")
        prow = ctk.CTkFrame(pcard, fg_color="transparent")
        prow.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, Metric.PAD))

        self.preset = ctk.CTkOptionMenu(
            prow, values=list(PRESETS.keys()), command=self._use_preset,
            width=200, height=32,
            font=ctk.CTkFont(family=Type.UI, size=11),
            fg_color=Ink.SURFACE_2, button_color=Ink.SURFACE_3,
            button_hover_color=Ink.BORDER, text_color=Ink.TEXT,
            dropdown_fg_color=Ink.SURFACE_2, dropdown_hover_color=Ink.SURFACE_3,
            dropdown_text_color=Ink.TEXT, corner_radius=Metric.RADIUS_SM,
        )
        self.preset.set("Game default" if not self._draft else "Custom"
                        if "Custom" in PRESETS else "Game default")
        self.preset.pack(side="left")
        Body(prow, "  Then fine-tune any single colour below.",
             dim=True).pack(side="left")

        # ---- the swatches
        ccard = Card(self.content, "Colours", rim=self.theme.accent)
        ccard.pack(fill="x", pady=(Metric.GAP, 0))
        self._grid = ctk.CTkFrame(ccard, fg_color="transparent")
        self._grid.pack(fill="x", padx=Metric.PAD,
                        pady=(Metric.PAD_SM, Metric.PAD))
        self._swatches = {}
        for token, label in EDITABLE:
            self._swatch_row(self._grid, token, label)

        # ---- actions
        act = ctk.CTkFrame(self.content, fg_color="transparent")
        act.pack(fill="x", pady=(Metric.PAD, 0))
        primary(act, "Apply", self._apply, Ink.ACTION, Ink.ACTION_BRIGHT,
                Ink.ACTION_INK, width=130).pack(side="left")
        ghost(act, "Reset to game colours", self._reset,
              width=180).pack(side="left", padx=(Metric.PAD_SM, 0))
        self.msg = Body(act, "", dim=True)
        self.msg.pack(side="left", padx=(Metric.PAD, 0))

    # ------------------------------------------------------------- plumbing

    def _store(self):
        return getattr(self.shell, "custom_store", None)

    def _store_theme(self) -> dict:
        st = self._store()
        return st.theme() if st else {}

    def _current(self, token) -> str:
        return self._draft.get(token) or getattr(Ink, token)

    def _swatch_row(self, parent, token, label):
        # One line per colour, not two. Seven stacked two-line rows pushed the
        # accent swatch and the Apply button below the window -- a control you
        # cannot reach is worse than one that looks cramped.
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)

        ctk.CTkLabel(
            row, text=label, width=130, anchor="w",
            font=ctk.CTkFont(family=Type.UI, size=12, weight="bold"),
            text_color=Ink.TEXT,
        ).pack(side="left")

        chip = ctk.CTkButton(
            row, text="", width=56, height=26,
            fg_color=self._current(token), hover_color=self._current(token),
            border_color=Ink.BORDER, border_width=1,
            corner_radius=Metric.RADIUS_SM,
        )
        chip.configure(command=lambda t=token: self._pick(t))
        chip.pack(side="right")

        code = ctk.CTkLabel(
            row, text=self._current(token), width=76, anchor="e",
            font=ctk.CTkFont(family=Type.MONO, size=10),
            text_color=Ink.TEXT_MUTE,
        )
        code.pack(side="right", padx=(0, Metric.PAD_SM))

        self._swatches[token] = (chip, code)

    def _pick(self, token):
        # The OS picker, not one we drew. It is the control people already know,
        # it has an eyedropper, and it accepts a pasted hex from a brand sheet.
        rgb, hex_value = colorchooser.askcolor(
            color=self._current(token), title="Choose a colour", parent=self)
        if not hex_value:
            return
        self._draft[token] = hex_value
        chip, code = self._swatches[token]
        chip.configure(fg_color=hex_value, hover_color=hex_value)
        code.configure(text=hex_value)
        self.msg.configure(text="Not applied yet — press Apply.",
                           text_color=Ink.WARN)

    def _use_preset(self, name):
        self._draft = dict(PRESETS.get(name) or {})
        for token, _ in EDITABLE:
            chip, code = self._swatches[token]
            value = self._draft.get(token) or getattr(Ink, token)
            chip.configure(fg_color=value, hover_color=value)
            code.configure(text=value)
        self.msg.configure(text="Not applied yet — press Apply.",
                           text_color=Ink.WARN)

    # ---------------------------------------------------------------- apply

    def _apply(self):
        store = self._store()
        if store is None:
            self.msg.configure(text="No storage attached.", text_color=Ink.CRIT)
            return
        store.set_theme(self._draft)
        theme_mod.apply(self.theme.key, self._draft)
        self.shell.restyle()

    def _reset(self):
        store = self._store()
        if store:
            store.clear_theme()
        self._draft = {}
        theme_mod.apply(self.theme.key, None)
        self.shell.restyle()
