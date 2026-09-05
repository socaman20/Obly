"""
The small pieces every page is built from.

WHY
---
So that a card on the Commands page and a card on the Settings page are the
same object with the same padding, and stay that way when one of them changes.
Pages compose these; pages do not draw their own boxes.

Nothing here knows which game it is running for -- each widget takes a
GameTheme and reads its accent from that.
"""
from __future__ import annotations

import customtkinter as ctk

from .theme import Ink, Metric, Type


# ------------------------------------------------------------------ text bits

class Eyebrow(ctk.CTkLabel):
    """Small uppercase label above a group. Letter-spaced by hand -- tk has no
    tracking property, so the spaces are the tracking."""

    def __init__(self, master, text: str, color: str = Ink.TEXT_MUTE, **kw):
        super().__init__(
            master,
            text=" ".join(text.upper()),
            font=ctk.CTkFont(family=Type.UI, size=10, weight="bold"),
            text_color=color,
            anchor="w",
            **kw,
        )


class Heading(ctk.CTkLabel):
    def __init__(self, master, text: str, size: int = 15, **kw):
        super().__init__(
            master,
            text=text,
            font=ctk.CTkFont(family=Type.UI, size=size, weight="bold"),
            text_color=Ink.TEXT,
            anchor="w",
            **kw,
        )


class Body(ctk.CTkLabel):
    def __init__(self, master, text: str, dim: bool = False, wrap: int = 0, **kw):
        super().__init__(
            master,
            text=text,
            font=ctk.CTkFont(family=Type.UI, size=12),
            text_color=Ink.TEXT_DIM if dim else Ink.TEXT,
            anchor="w",
            justify="left",
            wraplength=wrap,
            **kw,
        )


# ---------------------------------------------------------------------- card

class Card(ctk.CTkFrame):
    """A bordered surface. Optionally titled.

    Deliberately not every block gets one -- a border says "separate object".
    Use it where a group genuinely stands apart, not as default decoration.
    """

    def __init__(self, master, title: str = "", subtitle: str = "",
                 rim: str | None = None, **kw):
        # `rim` edge-lights the card in the game's hue -- the cockpit-glass
        # look. Tk cannot blur a widget border (no box-shadow), so this is a
        # crisp 1px stroke rather than a true halo; against the warm obsidian
        # ground it still reads as edge-lit rather than as a plain outline.
        kw.setdefault("fg_color", Ink.SURFACE)
        kw.setdefault("border_color", rim or Ink.BORDER)
        kw.setdefault("border_width", 1)
        kw.setdefault("corner_radius", Metric.RADIUS)
        super().__init__(master, **kw)

        self.body = self          # where callers pack content by default

        if title:
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD, 0))
            Heading(head, title).pack(anchor="w")
            if subtitle:
                Body(head, subtitle, dim=True).pack(anchor="w", pady=(2, 0))


# ----------------------------------------------------------------------- pill

_PILL = {
    "good":    (Ink.GOOD_SOFT, Ink.GOOD),
    "warn":    (Ink.WARN_SOFT, Ink.WARN),
    "crit":    (Ink.CRIT_SOFT, Ink.CRIT),
    "neutral": (Ink.SURFACE_2, Ink.TEXT_DIM),
}


class Pill(ctk.CTkLabel):
    """A status chip. Always carries a word -- colour on its own is not a
    message, and a colourblind user reads the same thing everyone else does."""

    def __init__(self, master, text: str, kind: str = "neutral",
                 accent: str | None = None, **kw):
        if kind == "accent" and accent:
            bg, fg = Ink.SURFACE_2, accent
        else:
            bg, fg = _PILL.get(kind, _PILL["neutral"])
        super().__init__(
            master,
            text=text.upper(),
            font=ctk.CTkFont(family=Type.UI, size=10, weight="bold"),
            text_color=fg,
            fg_color=bg,
            corner_radius=999,
            padx=9, pady=2,
            **kw,
        )

    def set(self, text: str, kind: str = "neutral", accent: str | None = None):
        if kind == "accent" and accent:
            bg, fg = Ink.SURFACE_2, accent
        else:
            bg, fg = _PILL.get(kind, _PILL["neutral"])
        self.configure(text=text.upper(), text_color=fg, fg_color=bg)


# --------------------------------------------------------------------- keycap

class KeyCaps(ctk.CTkFrame):
    """Renders a binding as physical keys: Alt + F4, not the string "alt+f4".

    Players think in keys they can see on the keyboard. Showing the raw token
    makes them translate; showing caps means they can just look down.

    Not every binding is a list of keys. A macro is a sequence, and a mousehold
    is a button held for a duration -- both have an empty `keys` list while
    being perfectly bound. The scheme already carries a written form for those
    in `key_label` ("Right Alt + H -> Y", "Hold Mouse 1 (3s)"), so pass it as
    `label`. Without it these render as "unbound", which is a lie.
    """

    def __init__(self, master, keys, empty: str = "unbound",
                 label: str | None = None, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self.render(keys, empty, label)

    def render(self, keys, empty: str = "unbound", label: str | None = None):
        for child in self.winfo_children():
            child.destroy()

        keys = [k for k in (keys or []) if k]

        if not keys and label:
            ctk.CTkLabel(
                self, text=str(label),
                font=ctk.CTkFont(family=Type.MONO, size=11),
                text_color=Ink.TEXT_DIM,
                fg_color=Ink.SURFACE_3, corner_radius=Metric.RADIUS_SM,
                padx=7, pady=1,
            ).pack(side="left")
            return

        if not keys:
            ctk.CTkLabel(
                self, text=empty,
                font=ctk.CTkFont(family=Type.UI, size=11, slant="italic"),
                text_color=Ink.TEXT_MUTE,
            ).pack(side="left")
            return

        for i, key in enumerate(keys):
            if i:
                ctk.CTkLabel(
                    self, text="+",
                    font=ctk.CTkFont(family=Type.UI, size=11),
                    text_color=Ink.TEXT_MUTE,
                ).pack(side="left", padx=3)
            ctk.CTkLabel(
                self,
                text=str(key).upper(),
                font=ctk.CTkFont(family=Type.MONO, size=11, weight="bold"),
                text_color=Ink.TEXT,
                fg_color=Ink.SURFACE_3,
                corner_radius=Metric.RADIUS_SM,
                padx=7, pady=1,
            ).pack(side="left")


# ------------------------------------------------------------------ searchbox

class SearchBox(ctk.CTkFrame):
    """Entry + clear button. Calls `on_change(text)` as the user types."""

    def __init__(self, master, on_change, placeholder="Search commands, phrases, keys...",
                 accent: str = Ink.TEXT_DIM, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self._on_change = on_change

        # No textvariable here on purpose: CTkEntry hides its placeholder the
        # moment one is attached, so the box renders as an unexplained empty
        # rectangle. Bind to key events and read the widget instead.
        self.entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            font=ctk.CTkFont(family=Type.UI, size=12),
            height=34,
            fg_color=Ink.SURFACE_2,
            border_color=Ink.BORDER,
            border_width=1,
            corner_radius=Metric.RADIUS_SM,
            text_color=Ink.TEXT,
            placeholder_text_color=Ink.TEXT_MUTE,
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<KeyRelease>", lambda _e: self._fire())

        ctk.CTkButton(
            self, text="Clear", width=62, height=34,
            font=ctk.CTkFont(family=Type.UI, size=11),
            fg_color=Ink.SURFACE_2, hover_color=Ink.SURFACE_3,
            text_color=Ink.TEXT_DIM, border_color=Ink.BORDER, border_width=1,
            corner_radius=Metric.RADIUS_SM,
            command=self.clear,
        ).pack(side="left", padx=(Metric.PAD_SM, 0))

    def _fire(self):
        self._on_change(self.get())

    def get(self) -> str:
        return self.entry.get()

    def clear(self):
        self.entry.delete(0, "end")
        self._fire()


# --------------------------------------------------------------- empty state

class EmptyState(ctk.CTkFrame):
    """What a list says when it has nothing. Never leave a blank rectangle --
    a user cannot tell an empty result from a broken page."""

    def __init__(self, master, title: str, detail: str = "", **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.place(relx=0.5, rely=0.42, anchor="center")
        Heading(inner, title, size=13).pack()
        if detail:
            ctk.CTkLabel(
                inner, text=detail,
                font=ctk.CTkFont(family=Type.UI, size=11),
                text_color=Ink.TEXT_MUTE, wraplength=380, justify="center",
            ).pack(pady=(6, 0))


# --------------------------------------------------------------- level meter

class LevelMeter(ctk.CTkFrame):
    """Mic input level. The point is not precision -- it is answering "is this
    thing hearing me at all", which is the first question every user has."""

    SEGMENTS = 24

    def __init__(self, master, accent: str, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self._accent = accent
        self._bars = []
        for i in range(self.SEGMENTS):
            b = ctk.CTkFrame(self, width=6, height=18, corner_radius=2,
                             fg_color=Ink.SURFACE_3)
            b.pack(side="left", padx=1)
            b.pack_propagate(False)
            self._bars.append(b)

    def set_level(self, level: float):
        """level: 0.0 - 1.0"""
        lit = int(max(0.0, min(1.0, level)) * self.SEGMENTS)
        for i, bar in enumerate(self._bars):
            if i >= lit:
                bar.configure(fg_color=Ink.SURFACE_3)
            elif i > self.SEGMENTS * 0.88:
                bar.configure(fg_color=Ink.CRIT)      # clipping
            elif i > self.SEGMENTS * 0.70:
                bar.configure(fg_color=Ink.WARN)
            else:
                bar.configure(fg_color=self._accent)


# ------------------------------------------------------------------- buttons

def primary(master, text, command, accent: str, accent_dim: str,
            accent_ink: str, width: int = 140, height: int = 38, **kw):
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=height,
        font=ctk.CTkFont(family=Type.UI, size=12, weight="bold"),
        fg_color=accent, hover_color=accent_dim, text_color=accent_ink,
        corner_radius=Metric.RADIUS_SM, **kw,
    )


def ghost(master, text, command, width: int = 120, height: int = 34, **kw):
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=height,
        font=ctk.CTkFont(family=Type.UI, size=12),
        fg_color=Ink.SURFACE_2, hover_color=Ink.SURFACE_3,
        text_color=Ink.TEXT, border_color=Ink.BORDER, border_width=1,
        corner_radius=Metric.RADIUS_SM, **kw,
    )


def danger(master, text, command, width: int = 120, height: int = 34, **kw):
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=height,
        font=ctk.CTkFont(family=Type.UI, size=12),
        fg_color=Ink.CRIT_SOFT, hover_color="#4A211B",
        text_color=Ink.CRIT, border_color=Ink.CRIT, border_width=1,
        corner_radius=Metric.RADIUS_SM, **kw,
    )
