"""
Optional HOTAS / gamepad button as extra push-to-talk triggers.

The keyboard PTT is untouched. These are additive: any configured trigger
opens the mic, so a keyboard-and-mouse player is unaffected and unplugged
hardware simply reads as "not held".

WHY pygame AND NOT ctypes: the first version used Windows' legacy joystick
API through winmm.dll -- no dependency, and fine for a plain stick. It could
not see an X56 THROTTLE at all: winmm reported one device with 17 buttons and
two devices with zero, while the throttle really has 36 buttons. SDL (via
pygame) enumerates both X56 halves correctly, with real device names. winmm
is kept as a fallback for the case where pygame is missing.

DEVICES ARE MATCHED BY NAME, not index. SDL's ordering changes when hardware
is plugged in or powered on in a different order, so an index saved today can
point at the wrong device tomorrow. The name is stored and the index is only
a fallback.

LATCHED SWITCHES ARE THE REAL HAZARD. An X56 has toggle switches that report
as a permanently-held button. Binding one to push-to-talk wedges the mic open
forever. Both the capture wizard and the config check refuse them -- this is
not theoretical, it happened during development with throttle button 34.
"""

import ctypes
import ctypes.wintypes as wt
import os
import time

# --- pygame backend (preferred) --------------------------------------------

_pygame = None
_sticks = []


def _init_pygame():
    """Bring up SDL's joystick subsystem headlessly. Safe to call repeatedly."""
    global _pygame, _sticks
    if _pygame is not None:
        return _pygame

    try:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # no window, ever
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"      # no console spam
        import pygame
        pygame.init()
        pygame.joystick.init()
        _pygame = pygame
        _sticks = []
        for i in range(pygame.joystick.get_count()):
            js = pygame.joystick.Joystick(i)
            js.init()
            _sticks.append(js)
    except Exception:
        _pygame = False          # tried and failed; don't retry every poll
    return _pygame


def _pump():
    if _pygame:
        _pygame.event.pump()


# --- winmm fallback ---------------------------------------------------------

JOYERR_NOERROR = 0
JOY_RETURNBUTTONS = 0x00000080

try:
    _winmm = ctypes.WinDLL("winmm")
except OSError:                                  # pragma: no cover
    _winmm = None


class _JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("dwFlags", wt.DWORD),
        ("dwXpos", wt.DWORD), ("dwYpos", wt.DWORD), ("dwZpos", wt.DWORD),
        ("dwRpos", wt.DWORD), ("dwUpos", wt.DWORD), ("dwVpos", wt.DWORD),
        ("dwButtons", wt.DWORD), ("dwButtonNumber", wt.DWORD),
        ("dwPOV", wt.DWORD), ("dwReserved1", wt.DWORD), ("dwReserved2", wt.DWORD),
    ]


def _winmm_mask(device: int):
    if _winmm is None:
        return None
    info = _JOYINFOEX()
    info.dwSize = ctypes.sizeof(info)
    info.dwFlags = JOY_RETURNBUTTONS
    if _winmm.joyGetPosEx(int(device), ctypes.byref(info)) != JOYERR_NOERROR:
        return None
    return info.dwButtons


# --- public API -------------------------------------------------------------

def devices():
    """[(index, name, button_count)] for every joystick we can see."""
    if _init_pygame():
        return [(i, js.get_name(), js.get_numbuttons()) for i, js in enumerate(_sticks)]
    found = []
    for dev in range(4):
        if _winmm_mask(dev) is not None:
            found.append((dev, "joystick", 32))
    return found


def _resolve(device, name):
    """Pick a stick by stored name first, falling back to index."""
    if not _sticks:
        return None
    if name:
        wanted = str(name).strip().lower()
        for js in _sticks:
            if js.get_name().strip().lower() == wanted:
                return js
        for js in _sticks:                        # partial match, e.g. renamed driver
            if wanted in js.get_name().strip().lower():
                return js
    if device is not None and 0 <= int(device) < len(_sticks):
        return _sticks[int(device)]
    return None


def is_held(device, button, name=None) -> bool:
    """True while the configured joystick button is down."""
    if device is None and name is None:
        return False
    if button is None:
        return False

    if _init_pygame():
        js = _resolve(device, name)
        if js is None:
            return False
        _pump()
        index = int(button) - 1                   # config is 1-based, SDL is 0-based
        if 0 <= index < js.get_numbuttons():
            return bool(js.get_button(index))
        return False

    mask = _winmm_mask(device if device is not None else 0)
    if mask is None:
        return False
    return bool(mask & (1 << (int(button) - 1)))


def held_now():
    """{(index, name): {buttons}} for everything currently pressed."""
    out = {}
    if not _init_pygame():
        return out
    _pump()
    for i, js in enumerate(_sticks):
        pressed = {b + 1 for b in range(js.get_numbuttons()) if js.get_button(b)}
        if pressed:
            out[(i, js.get_name())] = pressed
    return out


# --- Xbox / XInput gamepad --------------------------------------------------

GAMEPAD_BUTTONS = {
    "DPAD_UP": 0x0001, "DPAD_DOWN": 0x0002,
    "DPAD_LEFT": 0x0004, "DPAD_RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020,
    "LEFT_THUMB": 0x0040, "RIGHT_THUMB": 0x0080,
    "LB": 0x0100, "RB": 0x0200,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}

_xinput = None
for _dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        _xinput = ctypes.WinDLL(_dll)
        break
    except OSError:
        continue


class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wt.WORD),
        ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wt.DWORD), ("Gamepad", _XINPUT_GAMEPAD)]


def gamepad_buttons(pad: int = 0):
    if _xinput is None:
        return None
    state = _XINPUT_STATE()
    if _xinput.XInputGetState(int(pad), ctypes.byref(state)) != 0:
        return None
    return state.Gamepad.wButtons


def gamepad_present(pad: int = 0) -> bool:
    return gamepad_buttons(pad) is not None


def gamepad_is_held(button, pad: int = 0) -> bool:
    if not button:
        return False
    mask = GAMEPAD_BUTTONS.get(str(button).strip().upper())
    if mask is None:
        return False
    buttons = gamepad_buttons(pad)
    if buttons is None:
        return False
    return bool(buttons & mask)


# --- capture wizard ---------------------------------------------------------

def capture(timeout_s: float = 30.0, settle_s: float = 2.0):
    """Ask the player to hold a button. Returns (index, name, button) or None.

    Buttons already down when this starts are latched switches and are
    excluded -- picking one would leave the mic permanently open.
    """
    if not _init_pygame():
        print("  Could not start the joystick system.")
        return None
    if not _sticks:
        print("  No joystick or HOTAS detected.")
        return None

    print("  Detected:")
    for i, js in enumerate(_sticks):
        print(f"    [{i}] {js.get_name()}  ({js.get_numbuttons()} buttons)")

    _pump()
    latched = {i: {b for b in range(js.get_numbuttons()) if js.get_button(b)}
               for i, js in enumerate(_sticks)}
    for i, held in latched.items():
        if held:
            print(f"    note: [{i}] already holds button(s) "
                  f"{sorted(b + 1 for b in held)} -- latched switch, ignoring.")

    print()
    print(f"  Hold the button you want, for about two seconds.")
    print(f"  Waiting up to {int(timeout_s)}s...")

    # Require the button to stay down, so a momentary blip doesn't win.
    seen = {}
    deadline = time.time() + timeout_s
    tick = 0.05
    while time.time() < deadline:
        _pump()
        for i, js in enumerate(_sticks):
            for b in range(js.get_numbuttons()):
                if not js.get_button(b) or b in latched[i]:
                    continue
                key = (i, js.get_name(), b + 1)
                seen[key] = seen.get(key, 0) + tick
                if seen[key] >= settle_s:
                    print(f"\n  Got it: {js.get_name()}  button {b + 1}")
                    return key
        time.sleep(tick)

    print("\n  Nothing held long enough. Try again and hold it steady.")
    return None
