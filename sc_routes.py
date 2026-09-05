"""
Routes: buy here, sell there — with the run drawn on a real star map.

WHAT THE MAP IS, AND WHAT IT IS NOT
-----------------------------------
The dots are REAL geometry. star-citizen.wiki publishes x/y/z for 30 star
systems, and this plots the galactic plane (x against z) straight from those
numbers. Stanton really is where it looks.

Inside a system there is nothing. No public source I could find carries
positions for planets, moons or stations -- UEX has hierarchy only. So this map
stops at the system, and a route's endpoints are named in text beneath it
rather than pinned to a fake dot on a fake planet. A map that invents positions
is worse than one that admits where it stops.

THE HONEST CAP
--------------
Profit is per SCU multiplied by what the run can ACTUALLY carry: the smaller of
your hold, the stock on the shelf, and what your budget affords. Tools that
quote a huge margin sitting on two units of stock are the main way this kind of
feature misleads people.
"""
from __future__ import annotations

import customtkinter as ctk

import sc_data
from voiceui.shell import Page
from voiceui.theme import Ink, Metric, Type
from voiceui.widgets import (Body, Card, EmptyState, Eyebrow, Heading, Pill,
                             ghost, primary)


class StarMap(ctk.CTkCanvas):
    """Top-down galactic plane. Click nothing; it reflects the selection."""

    PAD = 26

    def __init__(self, master, theme, **kw):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        kw.setdefault("bg", Ink.BG)
        kw.setdefault("height", 210)
        super().__init__(master, **kw)
        self.theme = theme
        self.systems = []
        self._route = None
        self.bind("<Configure>", lambda _e: self.redraw())

    def load(self, systems):
        self.systems = [s for s in systems if isinstance(s.get("position"), dict)]
        self.redraw()

    def show_route(self, frm_system, to_system):
        self._route = (str(frm_system or "").lower(), str(to_system or "").lower())
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10 or not self.systems:
            return

        xs = [s["position"]["x"] for s in self.systems]
        zs = [s["position"].get("z", 0) for s in self.systems]
        x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
        sx = (w - self.PAD * 2) / (x1 - x0 or 1)
        sz = (h - self.PAD * 2) / (z1 - z0 or 1)
        scale = min(sx, sz)

        def pt(s):
            return (self.PAD + (s["position"]["x"] - x0) * scale,
                    h - self.PAD - (s["position"].get("z", 0) - z0) * scale)

        frm = to = None
        for s in self.systems:
            name = str(s.get("name") or "")
            low = name.lower()
            px, py = pt(s)
            hot = self._route and low in self._route
            if self._route and low == self._route[0]:
                frm = (px, py, name)
            if self._route and low == self._route[1]:
                to = (px, py, name)

            r = 5 if hot else 2.5
            colour = self.theme.accent if hot else Ink.TEXT_MUTE
            self.create_oval(px - r, py - r, px + r, py + r,
                             fill=colour, outline="")
            if hot or name in ("Stanton", "Pyro", "Terra", "Sol", "Nyx"):
                self.create_text(px, py - 11, text=name, fill=(
                    Ink.TEXT if hot else Ink.TEXT_MUTE), anchor="s",
                    font=(Type.MONO, 8, "bold" if hot else "normal"))

        if frm and to:
            self.create_line(frm[0], frm[1], to[0], to[1],
                             fill=self.theme.accent, width=2, dash=(5, 3))
            mx, my = (frm[0] + to[0]) / 2, (frm[1] + to[1]) / 2
            self.create_text(mx, my - 8, text="%s → %s" % (frm[2], to[2]),
                             fill=self.theme.accent, anchor="s",
                             font=(Type.MONO, 8, "bold"))
        elif self._route:
            self.create_text(w / 2, h - 10,
                             text="both ends are inside the same system",
                             fill=Ink.TEXT_MUTE, anchor="s",
                             font=(Type.UI, 9))


class RoutesPage(Page):
    NAV_LABEL = "Routes"
    TITLE = "Trade Routes"
    SUBTITLE = "Where to buy it, where to sell it, and what the run is worth."

    def build(self):
        self.cache = self.shell.data_cache
        self._rows = []

        # ---- filters
        f = Card(self.content, "Plan a run", rim=self.theme.accent)
        f.pack(fill="x")
        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, Metric.PAD))

        self.commodity = self._entry(grid, "Commodity", "any", 0)
        self.frm = self._entry(grid, "Buy in system", "any", 1)
        self.to = self._entry(grid, "Sell in system", "any", 2)
        self.hold = self._entry(grid, "Cargo SCU", "96", 3, "96")
        self.budget = self._entry(grid, "Budget aUEC", "any", 4)
        for i in range(5):
            grid.grid_columnconfigure(i, weight=1, uniform="f")

        act = ctk.CTkFrame(f, fg_color="transparent")
        act.pack(fill="x", padx=Metric.PAD, pady=(0, Metric.PAD))
        primary(act, "Find routes", self._find, Ink.ACTION, Ink.ACTION_BRIGHT,
                Ink.ACTION_INK, width=140).pack(side="left")
        ghost(act, "Clear", self._clear, width=90).pack(side="left",
                                                        padx=(Metric.PAD_SM, 0))
        self.note = Body(act, sc_data.DISCLAIMER, dim=True)
        self.note.pack(side="left", padx=(Metric.PAD, 0))

        # ---- the map
        mapcard = Card(self.content, "Star map",
                       "Real system positions. Click a route below to draw it.",
                       rim=self.theme.accent)
        mapcard.pack(fill="x", pady=(Metric.GAP, 0))
        self.map = StarMap(mapcard, self.theme)
        self.map.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, Metric.PAD))

        # ---- results
        self.results = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            scrollbar_button_color=Ink.SURFACE_3)
        self.results.pack(fill="both", expand=True, pady=(Metric.GAP, 0))
        EmptyState(self.results, "Press Find routes",
                   "Leave the fields empty for the best runs anywhere, or name "
                   "a system to plan a specific hop.").pack(fill="both", expand=True)

    def _entry(self, parent, label, placeholder, col, value=""):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=0, column=col, sticky="ew", padx=(0, Metric.PAD_SM))
        Eyebrow(box, label).pack(anchor="w", pady=(0, 3))
        e = ctk.CTkEntry(box, placeholder_text=placeholder, height=30,
                         font=ctk.CTkFont(family=Type.UI, size=11),
                         fg_color=Ink.SURFACE_2, border_color=Ink.BORDER,
                         border_width=1, corner_radius=Metric.RADIUS_SM,
                         text_color=Ink.TEXT,
                         placeholder_text_color=Ink.TEXT_MUTE)
        if value:
            e.insert(0, value)
        e.pack(fill="x")
        return e

    def on_show(self):
        if not self.map.systems:
            self.map.load(self.cache.get(sc_data.SYSTEM_MAP).rows)

    # ------------------------------------------------------------- actions

    @staticmethod
    def _num(entry):
        raw = "".join(c for c in entry.get() if c.isdigit())
        return int(raw) if raw else 0

    def _clear(self):
        for e in (self.commodity, self.frm, self.to, self.budget):
            e.delete(0, "end")
        self.hold.delete(0, "end")
        self.hold.insert(0, "96")

    def _find(self):
        for w in self.results.winfo_children():
            w.destroy()

        rows = sc_data.find_routes(
            self.cache,
            commodity=self.commodity.get(), from_system=self.frm.get(),
            to_system=self.to.get(), cargo_scu=self._num(self.hold),
            budget=self._num(self.budget), limit=12)
        self._rows = rows

        if not rows:
            EmptyState(self.results, "No profitable run found",
                       "Try widening the systems, clearing the commodity, or "
                       "pressing Update prices on the Market page."
                       ).pack(fill="both", expand=True)
            return

        for r in rows:
            self._route_row(r)
        self._select(rows[0])

    def _select(self, r):
        self.map.show_route(r["frm"]["system"], r["to"]["system"])

    def _route_row(self, r):
        row = ctk.CTkFrame(self.results, fg_color=Ink.SURFACE,
                           border_color=Ink.BORDER_SOFT, border_width=1,
                           corner_radius=Metric.RADIUS_SM)
        row.pack(fill="x", pady=2)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, 0))
        Heading(top, r["commodity"], size=13).pack(side="left")
        Pill(top, "%s aUEC profit" % format(r["total"], ","), "good").pack(
            side="right")
        ctk.CTkLabel(top, text="%s/SCU × %d SCU" % (format(r["margin"], ","),
                                                    r["units"]),
                     font=ctk.CTkFont(family=Type.MONO, size=11),
                     text_color=Ink.TEXT_DIM).pack(side="right",
                                                   padx=(0, Metric.PAD_SM))

        leg = ctk.CTkFrame(row, fg_color="transparent")
        leg.pack(fill="x", padx=Metric.PAD, pady=(3, Metric.PAD_SM))
        ctk.CTkLabel(
            leg,
            text="BUY  %s aUEC   %s · %s (%s)"
                 % (format(r["buy_price"], ","), r["frm"]["name"],
                    r["frm"]["body"], r["frm"]["system"]),
            font=ctk.CTkFont(family=Type.UI, size=11),
            text_color=Ink.TEXT_DIM, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            leg,
            text="SELL %s aUEC   %s · %s (%s)"
                 % (format(r["sell_price"], ","), r["to"]["name"],
                    r["to"]["body"], r["to"]["system"]),
            font=ctk.CTkFont(family=Type.UI, size=11),
            text_color=Ink.TEXT_DIM, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            leg, text="%d SCU in stock" % r["stock"],
            font=ctk.CTkFont(family=Type.UI, size=10),
            text_color=Ink.TEXT_MUTE, anchor="w").pack(anchor="w", pady=(2, 0))

        for w in [row, top, leg] + list(leg.winfo_children()):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda _e, rr=r: self._select(rr))
