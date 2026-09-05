"""
The window every tool opens into: sidebar, page area, status bar.

WHY
---
The shell is the part that must be identical across all four titles. A player
who learns where "Commands" lives in Star Citizen finds it in the same place in
Helldivers. Only the accent and the page list change.

A page never touches the window, the sidebar or the status bar directly -- it
gets a `shell` reference and calls `shell.set_status(...)`. That keeps the
chrome in one file, so fixing it fixes it everywhere.
"""
from __future__ import annotations

import tkinter.font as tkfont

import customtkinter as ctk

from . import theme as theme_mod
from .backdrop import Backdrop
from .theme import GameTheme, Ink, Metric, Type
from .widgets import Body, Eyebrow, Heading, Pill


class Page(ctk.CTkFrame):
    """One screen in the sidebar.

    Subclasses set NAV_LABEL and TITLE, then build in `build()`. `on_show()`
    fires every time the page is navigated to -- put refresh logic there, not
    in build(), or the page shows stale data the second time it is opened.
    """

    NAV_LABEL = "Page"
    TITLE = ""
    SUBTITLE = ""

    def __init__(self, master, shell: "AppShell", **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self.shell = shell
        self.theme = shell.theme
        self._built = False

    def ensure_built(self):
        if self._built:
            return
        self._built = True
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=Metric.PAD * 1.5, pady=(Metric.PAD * 1.25, 0))
        Heading(header, self.TITLE or self.NAV_LABEL, size=22).pack(anchor="w")
        if self.SUBTITLE:
            Body(header, self.SUBTITLE, dim=True).pack(anchor="w", pady=(4, 0))

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True,
                          padx=Metric.PAD * 1.5, pady=Metric.PAD)
        self.build()

    def build(self):
        """Construct the page body into self.content. Override."""

    def on_show(self):
        """Called each time this page becomes visible. Override to refresh."""


class _NavButton(ctk.CTkButton):
    def __init__(self, master, text, command, accent, **kw):
        self._accent = accent
        super().__init__(
            master, text=text, command=command,
            anchor="w", height=36,
            font=ctk.CTkFont(family=Type.UI, size=12),
            fg_color="transparent", hover_color=Ink.SURFACE_2,
            text_color=Ink.TEXT_DIM, corner_radius=Metric.RADIUS_SM, **kw,
        )

    def set_active(self, active: bool):
        if active:
            self.configure(fg_color=Ink.SURFACE_2, text_color=self._accent,
                           font=ctk.CTkFont(family=Type.UI, size=12, weight="bold"))
        else:
            self.configure(fg_color="transparent", text_color=Ink.TEXT_DIM,
                           font=ctk.CTkFont(family=Type.UI, size=12))


class AppShell(ctk.CTk):
    """The application window.

    Construct, `add_page(...)` each screen in nav order, then `start()`.
    """

    def __init__(self, theme: GameTheme, version: str = "", build_id: str = "",
                 size=(1120, 720), min_size=(940, 600), art: str | None = None):
        super().__init__()
        self.theme = theme
        self.art = art
        ctk.set_appearance_mode("dark")

        # Fonts can only be resolved once a Tk root exists. Bundled brand faces
        # are registered here too, so everything built below asks for the real
        # family name and gets the closest available one.
        theme_mod.resolve(tkfont, theme.key)

        self.title(theme.product)
        self.geometry("%dx%d" % size)
        self.minsize(*min_size)
        self.configure(fg_color=Ink.BG)

        self._pages: dict[str, Page] = {}
        self._buttons: dict[str, _NavButton] = {}
        self._registered: list = []            # (page_cls, key), for restyle()
        self._current: str | None = None
        self._version = version
        self._build_id = build_id

        self._build_sidebar(version, build_id)
        self._build_body()
        self._build_statusbar()

    # ------------------------------------------------------------- chrome

    def _build_sidebar(self, version, build_id):
        bar = ctk.CTkFrame(self, width=Metric.SIDEBAR_W, corner_radius=0,
                           fg_color=Ink.SURFACE)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)

        head = ctk.CTkFrame(bar, fg_color="transparent")
        head.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD * 1.25, Metric.PAD))

        # Gold rule: the house mark, identical on every title. The game's own
        # hue appears just below it, so the brand reads first and the game second.
        ctk.CTkFrame(head, height=2, width=38, corner_radius=1,
                     fg_color=Ink.GOLD).pack(anchor="w", pady=(0, 12))

        short = self.theme.product.replace(" Voice Control", "")
        # Wraps: "Star Trek Bridge Crew" does not fit the rail on one line,
        # and a clipped product name is the first thing a user sees.
        ctk.CTkLabel(
            head, text=short,
            font=ctk.CTkFont(family=Type.DISPLAY,
                             size=21 if len(short) < 16 else 17),
            text_color=Ink.CHAMPAGNE, anchor="w", justify="left",
            wraplength=Metric.SIDEBAR_W - Metric.PAD * 2,
        ).pack(anchor="w")
        ctk.CTkLabel(
            head, text=" ".join("VOICE CONTROL"),
            font=ctk.CTkFont(family=Type.MONO, size=9, weight="bold"),
            text_color=self.theme.accent, anchor="w",
        ).pack(anchor="w", pady=(3, 0))
        ctk.CTkLabel(
            head, text=self.theme.tagline,
            font=ctk.CTkFont(family=Type.UI, size=10),
            text_color=Ink.TEXT_MUTE, anchor="w",
            wraplength=Metric.SIDEBAR_W - Metric.PAD * 2, justify="left",
        ).pack(anchor="w", pady=(6, 0))

        ctk.CTkFrame(bar, height=1, fg_color=Ink.BORDER_SOFT).pack(
            fill="x", padx=Metric.PAD)

        self._nav = ctk.CTkFrame(bar, fg_color="transparent")
        self._nav.pack(fill="both", expand=True, padx=Metric.PAD_SM,
                       pady=Metric.PAD_SM)

        foot = ctk.CTkFrame(bar, fg_color="transparent")
        foot.pack(fill="x", padx=Metric.PAD, pady=Metric.PAD)
        if version:
            ctk.CTkLabel(
                foot, text="v%s" % version,
                font=ctk.CTkFont(family=Type.MONO, size=10),
                text_color=Ink.TEXT_MUTE, anchor="w",
            ).pack(anchor="w")
        if build_id:
            # The watermark is not hidden from the user. It identifies a leaked
            # copy; it costs the legitimate owner nothing to see it.
            ctk.CTkLabel(
                foot, text=build_id,
                font=ctk.CTkFont(family=Type.MONO, size=9),
                text_color=Ink.TEXT_MUTE, anchor="w",
            ).pack(anchor="w")

    def _build_body(self):
        self._body = ctk.CTkFrame(self, fg_color=Ink.OBSIDIAN)
        self._body.pack(side="top", fill="both", expand=True)

        # Atmosphere first, content over it. Pages are children OF the canvas,
        # not siblings placed above it: a CustomTkinter frame set to
        # "transparent" paints its PARENT's colour, so a sibling canvas would
        # simply be covered up. Parented to the canvas, the glow shows through
        # the gaps between cards, which is the whole point of it.
        self.backdrop = Backdrop(self._body, self.theme, art_path=self.art)
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self._page_host = self.backdrop

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=Metric.STATUSBAR_H, corner_radius=0,
                           fg_color=Ink.SURFACE)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)

        ctk.CTkFrame(bar, height=1, fg_color=Ink.BORDER_SOFT).place(
            relwidth=1, y=0)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=Metric.PAD, pady=Metric.PAD_SM)

        self.state_pill = Pill(left, "Idle", "neutral")
        self.state_pill.pack(side="left")

        self._status = ctk.CTkLabel(
            left, text="Ready.",
            font=ctk.CTkFont(family=Type.UI, size=11),
            text_color=Ink.TEXT_DIM, anchor="w",
        )
        self._status.pack(side="left", padx=(Metric.GAP, 0))

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=Metric.PAD, pady=Metric.PAD_SM)
        self._meta = ctk.CTkLabel(
            right, text="",
            font=ctk.CTkFont(family=Type.MONO, size=10),
            text_color=Ink.TEXT_MUTE, anchor="e",
        )
        self._meta.pack(side="right")

    # --------------------------------------------------------------- pages

    def add_page(self, page_cls, key: str | None = None) -> Page:
        page = page_cls(self._page_host, self)
        key = key or page_cls.NAV_LABEL
        if (page_cls, key) not in self._registered:
            self._registered.append((page_cls, key))
        self._pages[key] = page

        btn = _NavButton(self._nav, page_cls.NAV_LABEL,
                         lambda k=key: self.show(k), self.theme.accent)
        btn.pack(fill="x", pady=1)
        self._buttons[key] = btn

        if self._current is None:
            self.show(key)
        return page

    def show(self, key: str):
        if key not in self._pages:
            return
        if self._current:
            self._pages[self._current].pack_forget()
            self._buttons[self._current].set_active(False)
        page = self._pages[key]
        page.ensure_built()
        page.pack(fill="both", expand=True)
        self._buttons[key].set_active(True)
        self._current = key
        page.on_show()

    def page(self, key: str) -> Page | None:
        return self._pages.get(key)

    # -------------------------------------------------------------- status

    def set_status(self, text: str, state: str | None = None,
                   kind: str = "neutral"):
        """One place the whole app reports what it is doing."""
        self._status.configure(text=text)
        if state is not None:
            self.state_pill.set(state, kind, accent=self.theme.accent)

    def set_meta(self, text: str):
        """Right-hand corner: mic, model, scheme -- the standing facts."""
        self._meta.configure(text=text)

    def restyle(self):
        """Rebuild the window against the current palette, in place.

        CustomTkinter widgets take their colours as constructor arguments and
        do not re-read them, so a live re-theme means building them again.
        Rebuilding is cheap here (a few hundred widgets) and it guarantees
        nothing is left wearing the old palette -- which is exactly the bug a
        hand-written "walk every widget and reconfigure it" pass produces the
        first time someone adds a widget and forgets to update the walker.
        """
        was = self._current
        status = self._status.cget("text")
        meta = self._meta.cget("text")
        pages, registered = self._pages, list(self._registered)

        for child in list(self.winfo_children()):
            child.destroy()

        self.configure(fg_color=Ink.BG)
        self._pages, self._buttons, self._registered = {}, {}, []
        self._current = None

        self._build_sidebar(self._version, self._build_id)
        self._build_body()
        self._build_statusbar()

        for page_cls, key in registered:
            self.add_page(page_cls, key)
        if was in self._pages:
            self.show(was)
        self.set_status(status)
        self.set_meta(meta)

    def start(self):
        self.mainloop()
