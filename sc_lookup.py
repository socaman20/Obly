"""
Market: look up ship and commodity prices, and refresh them with one button.

WHY THIS PAGE IS IN THE STAR CITIZEN PROJECT
--------------------------------------------
Same rule as voicecore and voiceui: the machinery is shared, the knowledge is
not. `voiceui/datacache.py` does the fetching, caching and fallback ladder and
knows nothing about the game. This file knows what a commodity is, what SCU
means, and that a ship has a rental price -- so it lives here.

THE UPDATE BUTTON
-----------------
Prices move every patch and the data behind them is crowd-reported, so the two
questions a player has are "what does it cost" and "how old is this". Both are
answered on screen: the button refreshes all six endpoints in about two and a
half seconds, and the line beside it always says how stale the copy is and
which game build UEX thinks it describes.

It refreshes on a background thread. A button that freezes the window is a
button people click three times.
"""
from __future__ import annotations

import threading

import customtkinter as ctk

import sc_data
from voiceui.datacache import DataCache
from voiceui.shell import Page
from voiceui.theme import Ink, Metric, Type
from voiceui.widgets import (Body, Card, EmptyState, Eyebrow, Heading, Pill,
                             SearchBox, ghost, primary)


class LookupPage(Page):
    NAV_LABEL = "Market"
    TITLE = "Market"
    SUBTITLE = "Ship and commodity prices, pulled from the community trade data."

    def build(self):
        self.cache: DataCache = self.shell.data_cache
        self._busy = False

        # ---- the update strip
        strip = Card(self.content, rim=self.theme.accent)
        strip.pack(fill="x")
        row = ctk.CTkFrame(strip, fg_color="transparent")
        row.pack(fill="x", padx=Metric.PAD, pady=Metric.PAD)

        self.btn = primary(row, "Update prices", self._refresh,
                           Ink.ACTION, Ink.ACTION_BRIGHT, Ink.ACTION_INK,
                           width=150)
        self.btn.pack(side="left")

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", padx=(Metric.PAD, 0), fill="x", expand=True)
        self.age = Body(info, "", dim=True)
        self.age.pack(anchor="w")
        self.src = ctk.CTkLabel(
            info, text=sc_data.ATTRIBUTION,
            font=ctk.CTkFont(family=Type.UI, size=10),
            text_color=Ink.TEXT_MUTE, anchor="w",
        )
        self.src.pack(anchor="w")

        self.ver = Pill(row, "—", "neutral")
        self.ver.pack(side="right")

        # ---- the honest line, on screen rather than buried
        ctk.CTkLabel(
            self.content, text=sc_data.DISCLAIMER,
            font=ctk.CTkFont(family=Type.UI, size=11),
            text_color=Ink.WARN, anchor="w", justify="left", wraplength=760,
        ).pack(anchor="w", pady=(Metric.PAD_SM, 0))

        # ---- search
        self.search = SearchBox(self.content, self._search,
                                placeholder="Search a ship, component or commodity — "
                                            "cutlass, cooler, iron…",
                                accent=self.theme.accent)
        self.search.pack(fill="x", pady=(Metric.PAD, 0))

        self.results = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            scrollbar_button_color=Ink.SURFACE_3,
            scrollbar_button_hover_color=Ink.BORDER,
        )
        self.results.pack(fill="both", expand=True, pady=(Metric.PAD_SM, 0))
        self._idle_state()

    # ------------------------------------------------------------- status

    def on_show(self):
        self._update_age()

    def _update_age(self):
        st = self.cache.status(sc_data.ENDPOINTS)
        have = [r for r in st.values() if r["have"]]
        if not have:
            self.age.configure(text="No price data yet — press Update prices.",
                               text_color=Ink.WARN)
            self.ver.set("no data", "warn")
            return
        newest = max(r["fetched"] for r in have)
        stale = [r for r in have if not r["fresh"]]
        from time import time
        mins = int((time() - newest) // 60)
        when = ("just now" if mins < 1 else
                "%d min ago" % mins if mins < 60 else
                "%d hr ago" % (mins // 60) if mins < 1440 else
                "%d days ago" % (mins // 1440))
        self.age.configure(
            text="Last updated %s · %d of %d sets cached%s"
                 % (when, len(have), len(sc_data.ENDPOINTS),
                    " · %d stale" % len(stale) if stale else ""),
            text_color=Ink.WARN if stale else Ink.TEXT_DIM)
        self.ver.set("game " + sc_data.game_version(self.cache),
                     "warn" if stale else "good")

    # ------------------------------------------------------------ refresh

    def _refresh(self):
        if self._busy:
            return
        self._busy = True
        self.btn.configure(text="Updating…", state="disabled")
        self.age.configure(text="Contacting UEX Corp…", text_color=Ink.TEXT_DIM)
        # Off the UI thread: six requests is ~2.5s, and a frozen window during
        # it reads as a crash.
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        report = []
        try:
            for res in self.cache.refresh_all(sc_data.ENDPOINTS):
                report.append(res)
        except Exception as exc:                       # never lose the button
            report.append(exc)
        self.after(0, lambda: self._done(report))

    def _done(self, report):
        self._busy = False
        self.btn.configure(text="Update prices", state="normal")
        live = sum(1 for r in report if getattr(r, "is_live", False))
        failed = [r for r in report if getattr(r, "origin", "") in ("none", "stale")]
        self._update_age()
        if failed:
            self.age.configure(
                text="Updated %d of %d. %d could not be reached — showing the "
                     "last copy instead." % (live, len(report), len(failed)),
                text_color=Ink.WARN)
        self._search(self.search.get())

    # ------------------------------------------------------------- search

    def _idle_state(self):
        for w in self.results.winfo_children():
            w.destroy()
        EmptyState(self.results, "Search a ship, component or commodity",
                   "Try “cutlass” for where to buy and rent it, “cooler” for "
                   "ship components, or “iron” for what it sells at.").pack(fill="both", expand=True)

    def _search(self, text):
        q = (text or "").strip()
        for w in self.results.winfo_children():
            w.destroy()
        if not q:
            self._idle_state()
            return

        ships = sc_data.find_ship(self.cache, q, 5)
        comms = sc_data.find_commodity(self.cache, q, 5)
        parts = sc_data.find_component(self.cache, q, 6)

        if not ships and not comms and not parts:
            EmptyState(self.results, "Nothing found for “%s”" % q,
                       "Prices may just be out of date — try Update prices."
                       ).pack(fill="both", expand=True)
            return

        if ships:
            Eyebrow(self.results, "Ships", color=self.theme.accent).pack(
                anchor="w", pady=(2, Metric.PAD_SM))
            for s in ships:
                self._ship_row(s)

        if comms:
            Eyebrow(self.results, "Commodities", color=self.theme.accent).pack(
                anchor="w", pady=(Metric.PAD, Metric.PAD_SM))
            for c in comms:
                self._commodity_row(c)

        if parts:
            Eyebrow(self.results, "Ship components", color=self.theme.accent).pack(
                anchor="w", pady=(Metric.PAD, Metric.PAD_SM))
            for p in parts:
                self._part_row(p)

    def _part_row(self, p):
        row = ctk.CTkFrame(self.results, fg_color=Ink.SURFACE,
                           border_color=Ink.BORDER_SOFT, border_width=1,
                           corner_radius=Metric.RADIUS_SM)
        row.pack(fill="x", pady=2)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, 0))
        Heading(top, p["name"], size=13).pack(side="left")
        if p.get("category"):
            Pill(top, p["category"], "neutral").pack(side="left",
                                                     padx=(Metric.PAD_SM, 0))
        at = p.get("at") or []
        if at:
            ctk.CTkLabel(top, text="from %s aUEC" % format(at[0]["price"], ","),
                         font=ctk.CTkFont(family=Type.MONO, size=11),
                         text_color=Ink.TEXT).pack(side="right")
        ctk.CTkLabel(
            row,
            text=("  ·  ".join(a["where"] for a in at[:3])
                  + ("  +%d more" % (len(at) - 3) if len(at) > 3 else ""))
            if at else "No shop currently reported.",
            font=ctk.CTkFont(family=Type.UI, size=11),
            text_color=Ink.TEXT_MUTE, anchor="w", justify="left",
            wraplength=720,
        ).pack(anchor="w", padx=Metric.PAD, pady=(2, Metric.PAD_SM))

    def _ship_row(self, s):
        row = ctk.CTkFrame(self.results, fg_color=Ink.SURFACE,
                           border_color=Ink.BORDER_SOFT, border_width=1,
                           corner_radius=Metric.RADIUS_SM)
        row.pack(fill="x", pady=2)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, 0))
        Heading(top, s["name"] or "?", size=13).pack(side="left")
        if s.get("scu"):
            Pill(top, "%s SCU" % s["scu"], "neutral").pack(side="right")

        # Name the places. "buy at 3 locations" is not something a player can
        # fly to; "New Deal, Lorville, Hurston" is.
        body = ctk.CTkFrame(row, fg_color="transparent")
        body.pack(fill="x", padx=Metric.PAD, pady=(4, Metric.PAD_SM))

        def line(tag, tag_colour, entry):
            r = ctk.CTkFrame(body, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=tag, width=44, anchor="w",
                         font=ctk.CTkFont(family=Type.MONO, size=9,
                                          weight="bold"),
                         text_color=tag_colour).pack(side="left")
            ctk.CTkLabel(r, text="%12s aUEC" % format(entry["price"] or 0, ","),
                         width=110, anchor="e",
                         font=ctk.CTkFont(family=Type.MONO, size=11),
                         text_color=Ink.TEXT).pack(side="left")
            ctk.CTkLabel(r, text="  " + entry["where"], anchor="w",
                         font=ctk.CTkFont(family=Type.UI, size=11),
                         text_color=Ink.TEXT_DIM, justify="left").pack(side="left")

        buy, rent = s.get("buy") or [], s.get("rent") or []
        for b in buy[:3]:
            line("BUY", self.theme.accent, b)
        for r_ in rent[:3]:
            line("RENT", Ink.TEXT_MUTE, r_)
        extra = max(0, len(buy) - 3) + max(0, len(rent) - 3)
        if extra:
            ctk.CTkLabel(body, text="+%d more location%s" % (extra, "" if extra == 1 else "s"),
                         font=ctk.CTkFont(family=Type.UI, size=10),
                         text_color=Ink.TEXT_MUTE, anchor="w").pack(anchor="w", pady=(2, 0))
        if not buy and not rent:
            ctk.CTkLabel(body, text="No purchase or rental data reported.",
                         font=ctk.CTkFont(family=Type.UI, size=11),
                         text_color=Ink.TEXT_MUTE, anchor="w").pack(anchor="w")

    def _commodity_row(self, c):
        row = ctk.CTkFrame(self.results, fg_color=Ink.SURFACE,
                           border_color=Ink.BORDER_SOFT, border_width=1,
                           corner_radius=Metric.RADIUS_SM)
        row.pack(fill="x", pady=2)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM, 0))
        Heading(top, c.get("name", "?"), size=13).pack(side="left")
        if c.get("is_extractable"):
            Pill(top, "mineable", "good").pack(side="left",
                                               padx=(Metric.PAD_SM, 0))

        b, s = c.get("price_buy") or 0, c.get("price_sell") or 0
        ctk.CTkLabel(
            top,
            text="buy %s   sell %s  aUEC/SCU" % (format(b, ","), format(s, ",")),
            font=ctk.CTkFont(family=Type.MONO, size=11),
            text_color=Ink.TEXT if s else Ink.TEXT_MUTE,
        ).pack(side="right")

        ctk.CTkLabel(
            row, text="%s%s" % (c.get("kind") or "commodity",
                                "  ·  %s SCU/unit" % c["weight_scu"]
                                if c.get("weight_scu") else ""),
            font=ctk.CTkFont(family=Type.UI, size=11),
            text_color=Ink.TEXT_MUTE, anchor="w",
        ).pack(anchor="w", padx=Metric.PAD, pady=(2, Metric.PAD_SM))
