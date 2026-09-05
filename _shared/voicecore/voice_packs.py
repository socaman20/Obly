"""
Swappable spoken acknowledgements -- and real silence when that is what is wanted.

A voice pack is a folder of `<command_id>.wav` files. That is the whole format.
Making one is filling a folder: no code, no rebuild, and no API key at runtime,
because the clips are rendered ahead of time and shipped as audio.

    voice_acks/                 <- the default voice (flat, original layout)
    voice_acks/Roxie/           <- a pack
    voice_acks/Grandad/         <- another

WHY PRE-RENDERED, NOT LIVE TTS
------------------------------
Calling a speech API at runtime would mean an API key inside a program we hand
to other people (extractable, and we would pay for their usage), plus latency
before every line and a hard dependency on someone else's service staying up.
Rendering once and shipping the audio removes all three. It is also how the
commercial voice-pack products do it, for the same reasons.

SILENCE IS A CHOICE, NOT AN ABSENCE
-----------------------------------
Testers asked for some commands not to talk back. Before this, "no clip
recorded yet" and "meant to stay quiet" were the same state, and both came out
as the robot fallback voice. They are now different things:

    command["silent"] = True     never makes a sound, ever
    settings.fallback_tts=False  no clip -> stay quiet, do not read it aloud
"""
import os


class VoicePacks:
    """Resolves which clip to play, if any.

    Kept as an object rather than module globals so a program can hold more
    than one (a test harness, or a tool that previews packs side by side).
    """

    def __init__(self, acks_dir):
        self.acks_dir = str(acks_dir)
        self.pack = ""
        self.fallback_tts = True

    # -- selection ---------------------------------------------------------
    def available(self):
        """Every subfolder that actually contains clips. Empty ones are noise."""
        if not os.path.isdir(self.acks_dir):
            return []
        out = []
        for name in sorted(os.listdir(self.acks_dir)):
            d = os.path.join(self.acks_dir, name)
            if os.path.isdir(d) and any(f.endswith(".wav") for f in os.listdir(d)):
                out.append(name)
        return out

    def select(self, name):
        """Point playback at a pack. Falls back to the default if it is missing.

        Returns the name actually selected, so the caller can report honestly
        rather than claiming a pack is active when it is not.
        """
        name = (name or "").strip()
        if name and not os.path.isdir(os.path.join(self.acks_dir, name)):
            name = ""
        self.pack = name
        return name

    def set_fallback_tts(self, enabled):
        self.fallback_tts = bool(enabled)

    # -- lookup ------------------------------------------------------------
    def clip_for(self, command_id):
        """Selected pack first, then the default folder. None if neither has it.

        The fallthrough is deliberate: a pack only needs to record the lines it
        wants to change. Anything it skips still speaks in the default voice
        instead of going silent, so a half-finished pack is usable.
        """
        if self.pack:
            p = os.path.join(self.acks_dir, self.pack, command_id + ".wav")
            if os.path.exists(p):
                return p
        p = os.path.join(self.acks_dir, command_id + ".wav")
        return p if os.path.exists(p) else None

    def missing(self, command_ids):
        """Which commands have no clip -- i.e. what a pack still needs recording."""
        return [c for c in command_ids if self.clip_for(c) is None]

    def should_speak_aloud(self, command_id, text, silent=False):
        """(play_clip_path, use_tts_text). Either may be None.

        One place decides, so callers cannot drift apart on what silence means.
        """
        if silent:
            return None, None
        if not (text or "").strip():
            return None, None
        clip = self.clip_for(command_id)
        if clip:
            return clip, None
        if self.fallback_tts:
            return None, text
        return None, None
