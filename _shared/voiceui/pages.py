"""
The pages every title shares.

WHY THESE ARE HERE AND NOT IN THE GAME PROJECTS
-----------------------------------------------
"Browse my commands", "add a command of my own", "which mic", "what version am
I on" are the same job in all four tools. Written once, every game gets them --
including the three that have never had a window at all.

Anything that needs to know what a mobiGlas or a stratagem is stays in the
game's own project. These pages take data, not knowledge.

THE CONTROLLER
--------------
RunPage does not import the speech engine. It talks to a controller object the
game project passes in, which must provide:

    start()            -> begin listening
    stop()             -> stop listening
    is_running()       -> bool
    level()            -> float 0..1, current mic level
    drain()            -> list of (kind, text) events since the last call,
                          kind in {"heard", "fired", "miss", "info", "error"}

That keeps the engine swappable and lets the UI be opened and tested without a
microphone attached.
"""
from __future__ import annotations

import customtkinter as ctk

from .theme import Ink, Metric, Type
from .dialogs import CommandDialog, KeyEditDialog
from .shell import Page
from .widgets import (Body, Card, EmptyState, Eyebrow, Heading, KeyCaps,
                      LevelMeter, Pill, SearchBox, danger, ghost, primary)


# ============================================================== RUN / LISTEN

class RunPage(Page):
    NAV_LABEL = "Listen"
    TITLE = "Voice Control"
    SUBTITLE = "Hold your push-to-talk key and speak a command."

    POLL_MS = 100

    def build(self):
        t = self.theme
        ctrl = ctk.CTkFrame(self.content, fg_color="transparent")
        ctrl.pack(fill="x")

        self.btn = primary(ctrl, "Start Listening", self._toggle,
                           Ink.GOLD, Ink.GOLD_BRIGHT, Ink.OBSIDIAN,
                           width=170, height=42)
        self.btn.pack(side="left")

        meter_box = ctk.CTkFrame(ctrl, fg_color="transparent")
        meter_box.pack(side="left", padx=(Metric.PAD * 1.5, 0))
        Eyebrow(meter_box, "Microphone").pack(anchor="w", pady=(0, 5))
        self.meter = LevelMeter(meter_box, t.accent)
        self.meter.pack(anchor="w")

        # --- the two panels: what it heard, what it did
        panes = ctk.CTkFrame(self.content, fg_color="transparent")
        panes.pack(fill="both", expand=True, pady=(Metric.PAD * 1.25, 0))
        panes.grid_columnconfigure(0, weight=3, uniform="p")
        panes.grid_columnconfigure(1, weight=2, uniform="p")
        panes.grid_rowconfigure(0, weight=1)

        heard = Card(panes, "Transcript", "Everything the recogniser returned",
                     rim=t.accent)
        heard.grid(row=0, column=0, sticky="nsew", padx=(0, Metric.GAP // 2))
        self.log = ctk.CTkTextbox(
            heard, fg_color=Ink.BG, border_width=0, wrap="word",
            font=ctk.CTkFont(family=Type.MONO, size=11),
            text_color=Ink.TEXT_DIM,
        )
        self.log.pack(fill="both", expand=True,
                      padx=Metric.PAD, pady=(Metric.PAD_SM, Metric.PAD))
        self.log.configure(state="disabled")

        last = Card(panes, "Last Command", "What was actually sent to the game",
                    rim=t.accent)
        last.grid(row=0, column=1, sticky="nsew", padx=(Metric.GAP // 2, 0))
        inner = ctk.CTkFrame(last, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=Metric.PAD,
                   pady=(Metric.PAD_SM, Metric.PAD))
        self.last_name = Heading(inner, "--", size=16)
        self.last_name.pack(anchor="w", pady=(6, 2))
        self.last_phrase = Body(inner, "Nothing yet.", dim=True, wrap=260)
        self.last_phrase.pack(anchor="w")
        Eyebrow(inner, "Keys sent").pack(anchor="w", pady=(Metric.PAD, 4))
        self.last_keys = KeyCaps(inner, [], empty="--")
        self.last_keys.pack(anchor="w")

        self._polling = False

    # -- controller plumbing ------------------------------------------------

    @property
    def controller(self):
        return getattr(self.shell, "controller", None)

    def _toggle(self):
        c = self.controller
        if c is None:
            self.shell.set_status("No speech engine attached.", "Error", "crit")
            return
        if c.is_running():
            c.stop()
            self.btn.configure(text="Start Listening")
            self.shell.set_status("Stopped.", "Idle", "neutral")
        else:
            c.start()
            self.btn.configure(text="Stop Listening")
            self.shell.set_status("Listening for your push-to-talk key.",
                                  "Listening", "good")
            self._ensure_poll()

    def on_show(self):
        self._ensure_poll()

    def _ensure_poll(self):
        if not self._polling:
            self._polling = True
            self._poll()

    def _poll(self):
        c = self.controller
        if c is not None:
            try:
                self.meter.set_level(c.level())
                for kind, text in c.drain():
                    self._on_event(kind, text)
            except Exception as exc:                       # never kill the UI
                self._append("! %s" % exc)
        self.after(self.POLL_MS, self._poll)

    def _on_event(self, kind, text):
        if kind == "heard":
            self._append("  %s" % text)
        elif kind == "fired":
            name, phrase, keys = text
            self.last_name.configure(text=name)
            self.last_phrase.configure(text='heard: "%s"' % phrase)
            self.last_keys.render(keys)
            self._append("> %s" % name)
            self.shell.set_status("Sent %s" % name, "Listening", "good")
        elif kind == "miss":
            self._append("  (no match) %s" % text)
        elif kind == "error":
            self._append("! %s" % text)
            self.shell.set_status(str(text), "Error", "crit")
        else:
            self._append("  %s" % text)

    def _append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


# ================================================================= COMMANDS

class CommandsPage(Page):
    NAV_LABEL = "Commands"
    TITLE = "Commands"
    SUBTITLE = "Everything you can say, and the key each one sends."

    def build(self):
        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.pack(fill="x")
        self.search = SearchBox(top, self._filter, accent=self.theme.accent)
        self.search.pack(side="left", fill="x", expand=True)
        primary(top, "+ Add command", self._add, Ink.GOLD, Ink.GOLD_BRIGHT,
                Ink.OBSIDIAN, width=140, height=34).pack(side="left",
                                                          padx=(Metric.PAD_SM, 0))

        self.count = Body(self.content, "", dim=True)
        self.count.pack(anchor="w", pady=(Metric.PAD_SM, 0))

        self.list = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            scrollbar_button_color=Ink.SURFACE_3,
            scrollbar_button_hover_color=Ink.BORDER,
        )
        self.list.pack(fill="both", expand=True, pady=(Metric.PAD_SM, 0))
        self._rows = []

    def on_show(self):
        self._filter(self.search.get())

    def _commands(self):
        return getattr(self.shell, "commands", []) or []

    def _filter(self, text):
        q = (text or "").strip().lower()
        for w in self.list.winfo_children():
            w.destroy()

        matched = []
        for cmd in self._commands():
            if not q or self._matches(cmd, q):
                matched.append(cmd)

        all_cmds = self._commands()
        total = len(all_cmds)
        off = sum(1 for c in all_cmds if not self._is_on(c))
        if q:
            summary = "%d of %d commands" % (len(matched), total)
        else:
            summary = "%d commands, %d phrases" % (
                total, sum(len(c.get("phrases") or []) for c in all_cmds))
        if off:
            # Say it plainly. A switched-off command that silently does nothing
            # is the most confusing possible state.
            summary += "   ·   %d switched off and cannot fire" % off
        self.count.configure(text=summary)

        if not matched:
            EmptyState(self.list, "Nothing matches “%s”" % text,
                       "Try a key like F1, part of a phrase, or a category "
                       "name such as Flight.").pack(fill="both", expand=True)
            return

        last_cat = None
        for cmd in matched:
            cat = cmd.get("category") or "Other"
            if cat != last_cat:
                Eyebrow(self.list, cat, color=self.theme.accent).pack(
                    anchor="w", pady=(Metric.PAD, Metric.PAD_SM))
                last_cat = cat
            self._row(cmd)

    @staticmethod
    def _matches(cmd, q):
        hay = [cmd.get("display_name", ""), cmd.get("category", ""),
               cmd.get("id", ""), " ".join(cmd.get("phrases") or []),
               " ".join(str(k) for k in (cmd.get("keys") or [])),
               str(cmd.get("key_label") or "")]
        return q in " ".join(hay).lower()

    @property
    def store(self):
        return getattr(self.shell, "custom_store", None)

    def _is_on(self, cmd) -> bool:
        store = self.store
        return store.is_enabled(cmd.get("id")) if store else True

    def _toggle(self, cmd, var):
        """Switch one command on or off, and persist it immediately.

        No Save button on purpose: a switch that needs confirming somewhere
        else is a switch people get wrong. It writes on the spot.
        """
        store = self.store
        if store is None:
            return
        store.set_enabled(cmd.get("id"), bool(var.get()))
        self._filter(self.search.get())

    def _add(self):
        """Pop out the builder, and put the new command straight into the list."""
        store = self.store
        if store is None:
            return
        cats = sorted({c.get("category") for c in self._commands() if c.get("category")})
        new = CommandDialog(self.winfo_toplevel(), self.theme, cats).show()
        if not new:
            return
        store.add(new)
        self.shell.commands = [c for c in self.shell.commands
                               if c.get("id") != new["id"]] + [new]
        self._filter(self.search.get())
        self.shell.set_status("Added “%s”." % new["display_name"], "Idle", "neutral")

    def _edit_key(self, cmd):
        """Rebind one command. The override is the player's, so it goes in
        their file, not into the shipped scheme."""
        store = self.store
        if store is None:
            return
        had = store.key_override(cmd.get("id")) is not None
        out = KeyEditDialog(self.winfo_toplevel(), self.theme, cmd, had).show()
        if not out:
            return
        if out.get("reset"):
            store.clear_key_override(cmd.get("id"))
            self.shell.set_status(
                "“%s” is back to its shipped key. Restart to reload it."
                % (cmd.get("display_name") or cmd.get("id")), "Idle", "neutral")
        else:
            store.set_key_override(cmd.get("id"), out["keys"], out["type"])
            cmd["keys"] = out["keys"]
            cmd["type"] = out["type"]
            cmd["key_label"] = " + ".join(k.upper() for k in out["keys"])
            cmd["_rebound"] = True
            self.shell.set_status(
                "“%s” now sends %s." % (cmd.get("display_name"),
                                        cmd["key_label"]), "Idle", "good")
        self._filter(self.search.get())

    def _row(self, cmd):
        on = self._is_on(cmd)

        row = ctk.CTkFrame(self.list,
                           fg_color=Ink.SURFACE if on else Ink.BG,
                           border_color=self.theme.accent if on else Ink.BORDER_SOFT,
                           border_width=1,
                           corner_radius=Metric.RADIUS_SM)
        row.pack(fill="x", pady=2)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=Metric.PAD, pady=(Metric.PAD_SM + 2, 0))

        # The switch sits first, on the left, where the eye lands. It is the
        # control most likely to be wanted in a hurry -- "stop that one firing".
        var = ctk.BooleanVar(value=on)
        ctk.CTkSwitch(
            top, text="", variable=var, width=38, height=18,
            switch_width=34, switch_height=16,
            progress_color=self.theme.accent,
            button_color=Ink.TEXT, button_hover_color=Ink.TEXT,
            fg_color=Ink.SURFACE_3,
            command=lambda c=cmd, v=var: self._toggle(c, v),
        ).pack(side="left", padx=(0, Metric.PAD_SM))

        ctk.CTkLabel(
            top, text=cmd.get("display_name") or cmd.get("id", "?"),
            font=ctk.CTkFont(family=Type.UI, size=13, weight="bold"),
            text_color=Ink.TEXT if on else Ink.TEXT_MUTE, anchor="w",
        ).pack(side="left")

        caps = KeyCaps(top, cmd.get("keys"), label=cmd.get("key_label"))
        caps.pack(side="right")
        # The key is the thing people most want to change, so it is the thing
        # they can click. A display-only keycap invites the question "how do I
        # change this?" -- which is exactly the question that got asked.
        for w in [caps] + list(caps.winfo_children()):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", lambda _e, c=cmd: self._edit_key(c))

        if cmd.get("_rebound"):
            Pill(top, "yours", "accent", accent=self.theme.accent).pack(
                side="right", padx=(0, Metric.PAD_SM))

        if not on:
            Pill(top, "off", "neutral").pack(side="right",
                                             padx=(0, Metric.PAD_SM))
        # verified/notes is our own honesty metadata -- it is unusual and it is
        # the reason a user trusts the rest. Surface it, do not bury it.
        elif cmd.get("verified") is False:
            Pill(top, "unverified", "warn").pack(side="right",
                                                 padx=(0, Metric.PAD_SM))

        phrases = cmd.get("phrases") or []
        if phrases:
            ctk.CTkLabel(
                row, text="   ".join('“%s”' % p for p in phrases[:4])
                + ("   +%d more" % (len(phrases) - 4) if len(phrases) > 4 else ""),
                font=ctk.CTkFont(family=Type.UI, size=11),
                text_color=Ink.TEXT_MUTE, anchor="w", justify="left",
                wraplength=680,
            ).pack(anchor="w", padx=(Metric.PAD + 46, Metric.PAD),
                   pady=(2, Metric.PAD_SM + 2))


# =================================================================== CUSTOM

class CustomPage(Page):
    NAV_LABEL = "My Commands"
    TITLE = "My Commands"
    SUBTITLE = ("Add your own. These live in your own file and survive "
                "updates to the built-in set.")

    def build(self):
        wrap = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1, uniform="c")
        wrap.grid_columnconfigure(1, weight=1, uniform="c")
        wrap.grid_rowconfigure(0, weight=1)

        # ---- left: the builder
        form = Card(wrap, "New command", rim=self.theme.accent)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, Metric.GAP // 2))
        f = ctk.CTkFrame(form, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=Metric.PAD,
               pady=(Metric.PAD_SM, Metric.PAD))

        self.f_name = self._field(f, "Name", "Deploy landing gear")
        self.f_cat = self._field(f, "Category", "Flight & Navigation")
        self.f_keys = self._field(f, "Keys", "n   or   alt+f4")

        Eyebrow(f, "Mode").pack(anchor="w", pady=(Metric.PAD_SM, 4))
        self.f_mode = ctk.CTkSegmentedButton(
            f, values=["Tap", "Hold"],
            font=ctk.CTkFont(family=Type.UI, size=11),
            selected_color=self.theme.accent,
            selected_hover_color=self.theme.accent_dim,
            unselected_color=Ink.SURFACE_2,
            unselected_hover_color=Ink.SURFACE_3,
            text_color=Ink.TEXT, fg_color=Ink.SURFACE_2,
        )
        self.f_mode.set("Tap")
        self.f_mode.pack(anchor="w", fill="x")

        Eyebrow(f, "Trigger phrases  (one per line)").pack(
            anchor="w", pady=(Metric.PAD_SM, 4))
        self.f_phrases = ctk.CTkTextbox(
            f, height=96, fg_color=Ink.SURFACE_2, border_color=Ink.BORDER,
            border_width=1, corner_radius=Metric.RADIUS_SM, wrap="word",
            font=ctk.CTkFont(family=Type.UI, size=12), text_color=Ink.TEXT,
        )
        self.f_phrases.pack(fill="x")

        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(fill="x", pady=(Metric.PAD, 0))
        primary(btns, "Save Command", self._save, Ink.GOLD,
                Ink.GOLD_BRIGHT, Ink.OBSIDIAN).pack(side="left")
        ghost(btns, "Clear", self._clear).pack(side="left",
                                               padx=(Metric.PAD_SM, 0))

        self.msg = Body(f, "", dim=True, wrap=340)
        self.msg.pack(anchor="w", pady=(Metric.PAD_SM, 0))

        # ---- right: what already exists
        existing = Card(wrap, "Saved commands", rim=self.theme.accent)
        existing.grid(row=0, column=1, sticky="nsew", padx=(Metric.GAP // 2, 0))
        self.saved = ctk.CTkScrollableFrame(
            existing, fg_color="transparent",
            scrollbar_button_color=Ink.SURFACE_3,
        )
        self.saved.pack(fill="both", expand=True, padx=Metric.PAD,
                        pady=(Metric.PAD_SM, Metric.PAD))

    def _field(self, parent, label, placeholder):
        Eyebrow(parent, label).pack(anchor="w", pady=(Metric.PAD_SM, 4))
        e = ctk.CTkEntry(
            parent, placeholder_text=placeholder, height=32,
            font=ctk.CTkFont(family=Type.UI, size=12),
            fg_color=Ink.SURFACE_2, border_color=Ink.BORDER, border_width=1,
            corner_radius=Metric.RADIUS_SM, text_color=Ink.TEXT,
            placeholder_text_color=Ink.TEXT_MUTE,
        )
        e.pack(fill="x")
        return e

    def on_show(self):
        self._refresh()

    def _store(self):
        return getattr(self.shell, "custom_store", None)

    def _refresh(self):
        for w in self.saved.winfo_children():
            w.destroy()
        store = self._store()
        items = store.all() if store else []
        if not items:
            EmptyState(self.saved, "No custom commands yet",
                       "Anything you add on the left shows up here, and joins "
                       "the normal matching list straight away."
                       ).pack(fill="both", expand=True)
            return
        for cmd in items:
            row = ctk.CTkFrame(self.saved, fg_color=Ink.SURFACE_2,
                               corner_radius=Metric.RADIUS_SM)
            row.pack(fill="x", pady=2)
            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=Metric.PAD_SM + 2, pady=(Metric.PAD_SM, 0))
            Heading(top, cmd.get("display_name", "?"), size=12).pack(side="left")
            KeyCaps(top, cmd.get("keys"), label=cmd.get("key_label")).pack(side="right")
            ctk.CTkLabel(
                row, text="  ".join('“%s”' % p
                                    for p in (cmd.get("phrases") or [])),
                font=ctk.CTkFont(family=Type.UI, size=10),
                text_color=Ink.TEXT_MUTE, anchor="w", wraplength=320,
                justify="left",
            ).pack(anchor="w", padx=Metric.PAD_SM + 2, pady=(0, 4))
            danger(row, "Delete", lambda c=cmd: self._delete(c),
                   width=70, height=26).pack(anchor="e",
                                             padx=Metric.PAD_SM + 2,
                                             pady=(0, Metric.PAD_SM))

    def _save(self):
        store = self._store()
        if store is None:
            self.msg.configure(text="No storage attached.", text_color=Ink.CRIT)
            return

        name = self.f_name.get().strip()
        keys = [k.strip() for k in self.f_keys.get().replace("+", " ").split()
                if k.strip()]
        phrases = [p.strip() for p in
                   self.f_phrases.get("1.0", "end").splitlines() if p.strip()]

        # Say what is wrong and how to fix it -- never just refuse.
        if not name:
            self.msg.configure(text="Give the command a name first.",
                               text_color=Ink.WARN)
            return
        if not keys:
            self.msg.configure(
                text="Enter the key to press, e.g. n or alt+f4.",
                text_color=Ink.WARN)
            return
        if not phrases:
            self.msg.configure(
                text="Add at least one phrase you want to say out loud.",
                text_color=Ink.WARN)
            return

        try:
            store.add({
                "id": "custom_" + "_".join(name.lower().split()),
                "display_name": name,
                "category": self.f_cat.get().strip() or "My Commands",
                "phrases": phrases,
                "keys": keys,
                "type": "hold" if self.f_mode.get() == "Hold" else "tap",
                "verified": True,
                "notes": "Created by you.",
            })
        except Exception as exc:
            self.msg.configure(text="Could not save: %s" % exc,
                               text_color=Ink.CRIT)
            return

        self.msg.configure(text="Saved. “%s” is live now."
                                % phrases[0], text_color=Ink.GOOD)
        self._clear(keep_message=True)
        self._refresh()

    def _delete(self, cmd):
        store = self._store()
        if store:
            store.remove(cmd.get("id"))
            self._refresh()

    def _clear(self, keep_message=False):
        for e in (self.f_name, self.f_cat, self.f_keys):
            e.delete(0, "end")
        self.f_phrases.delete("1.0", "end")
        self.f_mode.set("Tap")
        if not keep_message:
            self.msg.configure(text="")


# ==================================================================== ABOUT

class AboutPage(Page):
    NAV_LABEL = "About"
    TITLE = "About"

    def build(self):
        info = getattr(self.shell, "about_info", {}) or {}
        card = Card(self.content)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=Metric.PAD * 1.25, pady=Metric.PAD * 1.25)

        Heading(inner, self.theme.product, size=18).pack(anchor="w")
        Body(inner, self.theme.tagline, dim=True).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(inner, height=1, fg_color=Ink.BORDER_SOFT).pack(
            fill="x", pady=Metric.PAD)

        for label, value in info.items():
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, width=130, anchor="w",
                         font=ctk.CTkFont(family=Type.UI, size=11),
                         text_color=Ink.TEXT_MUTE).pack(side="left")
            ctk.CTkLabel(row, text=str(value), anchor="w",
                         font=ctk.CTkFont(family=Type.MONO, size=11),
                         text_color=Ink.TEXT, justify="left",
                         wraplength=560).pack(side="left")
