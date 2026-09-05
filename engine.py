"""The listening engine, off the console and behind a window.

WHAT THIS IS
------------
main.py's loop, lifted into a thread that a UI can start, stop and watch. It
does not reimplement anything: the model, the matcher, the key sending and the
spoken acknowledgements are all main.py's own functions, imported. What is new
is that the loop can be told to stop, can be switched between two ways of
listening, and reports each moment instead of only printing it.

TWO WAYS TO LISTEN
------------------
push-to-talk   Hold a key, a HOTAS button or a gamepad button and speak. What
               you say between press and release is one command. Nothing is
               ever transcribed while the button is up, so a conversation on
               Discord cannot reach the game.

open mic       No button. The engine watches the microphone's loudness, takes
               everything between "you started talking" and "you stopped", and
               treats that as one command. Convenient, and riskier -- anything
               said in the room is a candidate. A wake word narrows it back
               down: set one and only speech that starts with it is acted on.

Both modes obey the same focus rule as the console: with
`require_focused_window` on, nothing fires unless Star Citizen is in front.
"""
from __future__ import annotations

import queue
import threading
import time

import numpy as np
import sounddevice as sd

import joystick_ptt
import main as engine_core


class Engine:
    """One microphone, one model, one worker thread.

    `on_event(kind, detail)` is called from the worker thread, so a UI must
    marshal to its own thread if it needs to. Kinds:

        state    the engine's own status changed (loading, ready, listening…)
        level    microphone loudness, for a meter
        heard    a transcript came back
        fired    a command was matched and sent
        nomatch  speech that matched nothing
        blocked  matched, but the game was not in front
        error    something went wrong; the message is for a person to read
    """

    def __init__(self, base_dir, on_event=None):
        self.base_dir = base_dir
        self.on_event = on_event or (lambda k, d: None)
        self._thread = None
        self._stop = threading.Event()
        self._model = None
        self._mode = "ptt"
        self._live = None
        self._lock = threading.Lock()
        self.status = "stopped"

    # ------------------------------------------------------------- plumbing
    def _emit(self, kind, **detail):
        try:
            self.on_event(kind, detail)
        except Exception:
            pass

    def _set_status(self, status, message="", tone="neutral"):
        self.status = status
        self._emit("state", status=status, message=message, tone=tone)

    # --------------------------------------------------------------- config
    def _load(self):
        """Config, matchers and the player's own bindings -- as main.py does."""
        config = engine_core.load_config()
        settings = config["settings"]
        engine_core.set_fallback_tts(settings.get("fallback_tts", True))
        engine_core.set_voice_pack(settings.get("voice_pack", ""))
        commands = config["commands"]
        plain, wildcard = engine_core.build_matchers(commands)
        return {"settings": settings, "commands": commands,
                "plain": plain, "wildcard": wildcard}

    def reload(self):
        """Pick up an edited commands.json without stopping the microphone."""
        try:
            fresh = self._load()
        except Exception as exc:
            self._emit("error", message="Could not reload your commands: %s" % exc)
            return False
        with self._lock:
            self._live = fresh
        self._emit("state", status=self.status,
                   message="Reloaded %d commands." % len(fresh["commands"]),
                   tone="good")
        return True

    # ------------------------------------------------------------------ PTT
    def _ptt_parts(self):
        s = self._live["settings"]
        return (s.get("ptt_key", "right ctrl"), s.get("ptt_joystick_device"),
                s.get("ptt_joystick_button"), s.get("ptt_joystick_name"),
                s.get("ptt_gamepad_button"))

    def _ptt_held(self):
        key, dev, btn, name, pad = self._ptt_parts()
        # Cheapest first: the keyboard state is already in memory, each
        # controller check costs a driver call.
        try:
            if engine_core.keyboard.is_pressed(key):
                return True
        except Exception:
            pass                       # an unknown key name must not kill the loop
        if joystick_ptt.is_held(dev, btn, name):
            return True
        return joystick_ptt.gamepad_is_held(pad)

    def triggers(self):
        """Plain English for what you hold, for the window to show."""
        if not self._live:
            try:
                self._live = self._load()
            except Exception:
                return "push-to-talk"
        key, dev, btn, name, pad = self._ptt_parts()
        out = ["'%s'" % key]
        if btn is not None and (name or dev is not None):
            out.append("%s button %s" % (name or ("device %s" % dev), btn))
        if pad:
            out.append("gamepad %s%s" % (
                pad, "" if joystick_ptt.gamepad_present() else " (not plugged in)"))
        return " or ".join(out)

    def capture_hotas(self, timeout_s=30.0):
        """Wait for a stick button to be pressed and return what it was.

        Returns (device, name, button) or None. The caller writes it to the
        config -- this only watches, so a cancelled capture changes nothing.
        """
        self._emit("state", status=self.status,
                   message="Press and hold the button you want, on the stick.",
                   tone="warn")
        return joystick_ptt.capture(timeout_s=timeout_s)

    # ---------------------------------------------------------------- start
    def start(self, mode="ptt"):
        if self._thread and self._thread.is_alive():
            self.set_mode(mode)
            return True
        self._mode = mode
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="voice-engine",
                                        daemon=True)
        self._thread.start()
        return True

    def stop(self, wait=True):
        self._stop.set()
        if wait and self._thread:
            self._thread.join(timeout=4.0)
        self._set_status("stopped", "Stopped listening.")

    def set_mode(self, mode):
        if mode not in ("ptt", "open"):
            return False
        self._mode = mode
        self._emit("state", status=self.status, tone="neutral",
                   message=("Hold %s to speak." % self.triggers()) if mode == "ptt"
                           else "Open mic: just talk.")
        return True

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------ the loop
    def _run(self):
        try:
            self._live = self._load()
        except Exception as exc:
            self._emit("error", message="Could not read your commands: %s" % exc)
            self._set_status("stopped", str(exc), "crit")
            return

        settings = self._live["settings"]
        sample_rate = settings.get("sample_rate", 16000)

        # Star Citizen is the priority process on this machine, not us. The
        # same reasoning as main.py: our work comes in short bursts, and a
        # burst that preempts the game mid-fight gets blamed on the game.
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        except Exception:
            pass

        self._set_status("loading", "Loading the recogniser…")
        try:
            root = engine_core.WHISPER_MODEL_ROOT / settings["whisper_model"]
            source = str(root) if root.exists() else settings["whisper_model"]
            self._model = engine_core.WhisperModel(
                source,
                device=settings["whisper_device"],
                compute_type=settings["whisper_compute_type"],
                cpu_threads=settings.get("whisper_cpu_threads", 4))
        except Exception as exc:
            self._emit("error", message="Whisper would not load: %s" % exc)
            self._set_status("stopped", "Recogniser failed to load.", "crit")
            return

        audio_q = queue.Queue()
        armed = {"on": False}
        level = {"rms": 0.0, "sent": 0.0}

        def callback(indata, frames, time_info, status):
            # Loudness is always measured -- the meter has to move before you
            # press anything, or you cannot tell a dead microphone from a
            # quiet one. Audio is only *kept* when armed.
            rms = float(np.sqrt(np.mean(np.square(indata))))
            level["rms"] = rms
            now = time.monotonic()
            if now - level["sent"] > 0.08:
                level["sent"] = now
                self._emit("level", rms=rms)
            if armed["on"]:
                audio_q.put(indata.copy())

        try:
            stream = sd.InputStream(samplerate=sample_rate, channels=1,
                                    dtype="float32", callback=callback)
            stream.start()
        except Exception as exc:
            self._emit("error", message="No microphone: %s" % exc)
            self._set_status("stopped", "Could not open the microphone.", "crit")
            return

        self.set_mode(self._mode)
        self._set_status("ready", "Ready.", "good")

        try:
            while not self._stop.is_set():
                if self._mode == "ptt":
                    self._ptt_pass(audio_q, armed, sample_rate)
                else:
                    self._open_pass(audio_q, armed, level, sample_rate)
        finally:
            armed["on"] = False
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self._set_status("stopped", "Stopped listening.")

    # ---------------------------------------------------------- push to talk
    def _ptt_pass(self, audio_q, armed, sample_rate):
        while not self._ptt_held():
            if self._stop.is_set() or self._mode != "ptt":
                return
            time.sleep(0.01)            # 100 Hz, imperceptible next to the game

        while not audio_q.empty():      # drop anything stale
            audio_q.get_nowait()
        armed["on"] = True
        self._set_status("listening", "Listening…", "good")
        chunks = []
        while self._ptt_held() and not self._stop.is_set():
            try:
                chunks.append(audio_q.get(timeout=0.1))
            except queue.Empty:
                pass
        armed["on"] = False
        self._set_status("thinking", "Working it out…")
        self._consume(chunks, sample_rate)

    # -------------------------------------------------------------- open mic
    # No button, so the engine has to decide for itself where a sentence
    # starts and stops. Loudness is enough for that: speech is far above room
    # noise, and a short tail of quiet is what ends a sentence. Thresholds are
    # deliberately conservative -- a missed command is a nuisance, a command
    # fired from someone else's voice on Discord is a scuttled ship.
    OPEN_START_RMS = 0.006     # measured: his idle is 0.0002, speech 0.013
    OPEN_STOP_RMS = 0.003      # below this for the hang time = they stopped
    OPEN_HANG_S = 0.65         # quiet needed to call it the end of a sentence
    OPEN_MIN_S = 0.35          # shorter than this is a cough, not a command
    OPEN_MAX_S = 8.0           # a hard ceiling, so a noisy room cannot run on

    def _open_pass(self, audio_q, armed, level, sample_rate):
        while level["rms"] < self.OPEN_START_RMS:
            if self._stop.is_set() or self._mode != "open":
                return
            time.sleep(0.01)

        while not audio_q.empty():
            audio_q.get_nowait()
        armed["on"] = True
        self._set_status("listening", "Listening…", "good")
        chunks = []
        started = time.monotonic()
        quiet_since = None
        while not self._stop.is_set() and self._mode == "open":
            try:
                chunks.append(audio_q.get(timeout=0.1))
            except queue.Empty:
                pass
            now = time.monotonic()
            if level["rms"] < self.OPEN_STOP_RMS:
                quiet_since = quiet_since or now
                if now - quiet_since >= self.OPEN_HANG_S:
                    break
            else:
                quiet_since = None
            if now - started >= self.OPEN_MAX_S:
                break
        armed["on"] = False
        self._set_status("thinking", "Working it out…")
        self._consume(chunks, sample_rate, open_mic=True)

    # ------------------------------------------------------------- handling
    def _consume(self, chunks, sample_rate, open_mic=False):
        if not chunks:
            self._set_status("ready", "Ready.", "good")
            return
        audio = np.concatenate(chunks, axis=0).flatten()
        if len(audio) < sample_rate * (self.OPEN_MIN_S if open_mic else 0.3):
            self._set_status("ready", "Too short — say it again.", "neutral")
            return

        with self._lock:
            live = self._live

        wake = (live["settings"].get("open_mic_wake_word") or "").strip().lower()

        def report(kind, detail):
            # An open mic with a wake word only acts on speech that starts
            # with it. The transcript is still shown either way -- silently
            # ignoring what someone said is how a tool feels broken.
            self._emit(kind, **detail)

        try:
            if open_mic and wake:
                text = engine_core.transcribe(self._model, audio)
                if not text:
                    self._set_status("ready", "Ready.", "good")
                    return
                stripped = text.lower().lstrip(" ,.!?")
                if not stripped.startswith(wake):
                    self._emit("heard", text=text, ignored=True, wake=wake)
                    self._set_status("ready",
                                     "Ignored — start with “%s”." % wake, "neutral")
                    return
                # Hand the matcher the command without the wake word in front.
                cut = len(wake)
                rest = stripped[cut:].lstrip(" ,.")
                cmd, slots = engine_core.match_command(
                    rest, live["plain"], live["wildcard"],
                    live["settings"]["match_threshold"])
                self._emit("heard", text=text)
                if cmd is None:
                    self._emit("nomatch", text=rest)
                    self._set_status("ready", "Nothing matched that.", "neutral")
                    return
                self._dispatch(cmd, slots, live["settings"], rest)
            else:
                engine_core.process_command(
                    self._model, live["plain"], live["wildcard"],
                    live["settings"], audio, report=report)
        except Exception as exc:
            self._emit("error", message="That command failed: %s" % exc)
        self._set_status("ready", "Ready.", "good")

    def _dispatch(self, cmd, slots, settings, text):
        """The wake-word path's own send, mirroring process_command's."""
        if settings["require_focused_window"]:
            title = engine_core.foreground_window_title()
            if settings["target_window_title"].lower() not in title.lower():
                self._emit("blocked", text=text, window=title)
                return
        self._emit("fired", text=text, id=cmd["id"],
                   name=cmd.get("display_name") or cmd["id"],
                   keys=cmd.get("keys") or [], key_label=cmd.get("key_label", ""),
                   action=cmd["type"], destination=slots.get("destination", ""))
        if cmd["type"] == "keypress":
            engine_core.press_combo(cmd["keys"])
        elif cmd["type"] == "keyhold":
            engine_core.press_combo(cmd["keys"], cmd.get("hold_ms", 1500))
        elif cmd["type"] == "mousehold":
            engine_core.mouse_hold(cmd["button"], cmd.get("hold_ms", 1500))
        elif cmd["type"] in ("route", "macro"):
            engine_core.run_steps(cmd["steps"], slots.get("destination", ""),
                                  settings["default_step_wait_ms"])
        ack = cmd.get("ack", "").format(**slots)
        if cmd.get("silent"):
            engine_core.speak(cmd["id"], "", silent=True)
        elif ack:
            engine_core.speak(cmd["id"], ack)
