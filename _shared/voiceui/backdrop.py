"""
The layered backdrop: a slow gold glow, and optional art you can still read over.

WHAT THIS IS PORTING
--------------------
The website builds its hero out of three stacked layers:

    .dragon-glow    a huge radial gold gradient, pulsing on a 6s loop
    .hero-dragon    the artwork, animated to settle at opacity 0.34
    .hero h1 ...    the content, at z-index 1, with a dark text-shadow halo

The 0.34 and the halo are the whole trick -- the art reads as atmosphere, the
words stay legible on top. Same idea here.

WHAT A DESKTOP APP CANNOT COPY
------------------------------
Tk has no backdrop-filter, no mix-blend-mode, and no CSS keyframes. So instead
of animating a live element, Pillow pre-renders the glow at a handful of
opacities once, and we cycle those frames on a timer. Same 6s period as the
website, a fraction of the cost, and it degrades to a plain panel if Pillow is
missing rather than failing to open.
"""
from __future__ import annotations

import os
import tkinter as tk

from .theme import Ink, Metric

try:
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
except ImportError:                       # never a reason not to start
    HAVE_PIL = False


FRAMES = 12                # pre-rendered steps around the pulse
ART_OPACITY = 0.34         # the website's settled dragon opacity, verbatim


def _hex(rgb_csv: str) -> tuple:
    r, g, b = (int(v) for v in rgb_csv.split(","))
    return r, g, b


def _rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Backdrop(tk.Canvas):
    """A canvas that sits behind a page and paints atmosphere.

    Place it first, then pack the real content over it. It never takes events,
    so clicks fall through to whatever is on top.
    """

    def __init__(self, master, theme, art_path: str | None = None, **kw):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        kw.setdefault("bg", Ink.OBSIDIAN)
        super().__init__(master, **kw)

        self.theme = theme
        self._art_path = art_path if art_path and os.path.exists(art_path) else None
        self._frames: list = []
        self._idx = 0
        self._size = (0, 0)
        self._item = None
        self._after = None

        self.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------- rendering

    def _on_resize(self, event):
        size = (max(1, event.width), max(1, event.height))
        if size == self._size:
            return
        self._size = size
        self._render(*size)

    def _render(self, w, h):
        if not HAVE_PIL:
            return
        self._frames = []

        glow_rgb = _hex(self.theme.glow)
        base = Image.new("RGB", (w, h), _rgb(Ink.OBSIDIAN))

        # The glow is a soft radial, centred like the website's (44% down).
        cx, cy = w // 2, int(h * 0.44)
        radius = int(min(w, h) * 1.15) or 1

        # Build it once at full strength, then reuse per frame with a scaled
        # alpha -- drawing 12 gradients would be pointlessly slow.
        glow = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(glow)
        steps = 44
        for i in range(steps, 0, -1):
            frac = i / steps
            r = int(radius * frac)
            # matches the website's rgba(...,0.16) 0% -> transparent 68% falloff
            a = int(255 * 0.16 * (1.0 - frac / 0.68) if frac < 0.68 else 0)
            if a <= 0:
                continue
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)

        art_layer = None
        if self._art_path:
            try:
                art = Image.open(self._art_path).convert("RGBA")
                scale = min((w * 0.62) / art.width, (h * 0.9) / art.height)
                if scale > 0:
                    art = art.resize((max(1, int(art.width * scale)),
                                      max(1, int(art.height * scale))),
                                     Image.LANCZOS)
                alpha = art.split()[3].point(lambda v: int(v * ART_OPACITY))
                art.putalpha(alpha)
                art_layer = (art, (cx - art.width // 2,
                                   int(h * 0.5) - art.height // 2))
            except Exception:
                art_layer = None          # bad art is not a reason to fail

        for f in range(FRAMES):
            # glowPulse: 0.7 -> 1.0 -> 0.7, a smooth there-and-back
            t = f / FRAMES
            strength = 0.7 + 0.3 * (1 - abs(2 * t - 1))
            frame = base.copy()
            tinted = Image.new("RGB", (w, h), glow_rgb)
            frame.paste(tinted, (0, 0),
                        glow.point(lambda v, s=strength: int(v * s)))
            if art_layer:
                art, pos = art_layer
                frame.paste(art, pos, art)
            self._frames.append(ImageTk.PhotoImage(frame))

        self._idx = 0
        self._paint()
        if self._after is None:
            self._tick()

    def _paint(self):
        if not self._frames:
            return
        img = self._frames[self._idx % len(self._frames)]
        if self._item is None:
            self._item = self.create_image(0, 0, anchor="nw", image=img)
        else:
            self.itemconfigure(self._item, image=img)
        self._keep = img              # Tk drops images it thinks are unused

    def _tick(self):
        if self._frames:
            self._idx = (self._idx + 1) % len(self._frames)
            self._paint()
        self._after = self.after(Metric.GLOW_PERIOD_MS // FRAMES, self._tick)

    def stop(self):
        if self._after is not None:
            self.after_cancel(self._after)
            self._after = None
