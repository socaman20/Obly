"""
First-launch experience.

The customer flow this serves: they unzip it, run it, and it should just
work -- no manual, no setup, no hunting. So the very first time it runs,
open the things that tell them what they've got:

  1. The Voice Command Reference card -- every command they can say.
  2. A generated "FIRST RUN" note -- what the program found in THEIR Star
     Citizen keybinds, which commands it adapted to their keys, which ones
     it can't drive, and where to change things by hand.

Only on the first run. Nobody wants three windows opening every launch, so
a marker file next to the program suppresses it afterwards. Deleting that
marker just shows it again, which is a harmless way to get it back.
"""

import os
import subprocess
from pathlib import Path

MARKER = ".firstrun_done"
NOTE_NAME = "FIRST RUN - START HERE.txt"

# Opened on first launch, in this order. Missing files are skipped rather
# than treated as an error -- a customer who deleted the reference card
# should still get a working program.
REFERENCE_CARD = "Voice Command Reference.jpg"


def already_ran(base_dir: Path) -> bool:
    return (base_dir / MARKER).exists()


def _write_note(base_dir: Path, keybind_lines, build_line: str, shortcut=None) -> Path:
    """The 'what did it do to my setup' note, written fresh each first run."""
    lines = [
        "STAR CITIZEN VOICE CONTROL -- FIRST RUN",
        "=" * 55,
        "",
        build_line,
        "",
        "HOW TO USE IT",
        "-" * 20,
    ]
    if shortcut:
        lines += [
            'A shortcut called "Star Citizen Voice Control" has been put on',
            "your Desktop -- use that to start it from now on.",
            "",
        ]
    else:
        lines += [
            "Couldn't create a Desktop shortcut automatically. You can make",
            'one by running "Create Desktop Shortcut.bat" in this folder.',
            "",
        ]
    lines += [
        "1. Launch Star Citizen and get in your ship.",
        "2. Hold RIGHT CTRL, say a command, let go.",
        "3. Watch the black console window -- it prints exactly what it",
        "   heard and which command it matched, so you always know whether",
        "   it registered.",
        "",
        "The picture that opened alongside this note is the full command",
        "list. That's everything you can say.",
        "",
        "WHAT IT FOUND IN *YOUR* STAR CITIZEN KEYBINDS",
        "-" * 46,
    ]
    lines.extend(keybind_lines or ["  (nothing read -- using Star Citizen's default keys)"])
    lines += [
        "",
        "Reading of that:",
        "  [OK] = it found your own key for that action and will send YOURS,",
        "         not the default. Nothing for you to do.",
        "  [X]  = it can't drive that one. Almost always because you've got",
        "         that action on a joystick/HOTAS button or cleared it --",
        "         there's no key for the program to press. Bind it to a",
        "         keyboard key in Star Citizen if you want voice to work it.",
        "",
        "IF A COMMAND DOES THE WRONG THING",
        "-" * 36,
        'Open "HOW TO CHANGE YOUR KEYBINDS.txt" in this folder. It walks',
        "through editing config\\commands.json so a command sends the key",
        "you actually use.",
        "",
        "This note only opens once. Delete the file named",
        f'"{MARKER}" in this folder to see it again.',
        "",
        "NOT AFFILIATED WITH CLOUD IMPERIUM GAMES.",
    ]
    path = base_dir / NOTE_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def create_desktop_shortcut(base_dir: Path):
    """Put a Desktop shortcut there automatically. Returns its path or None.

    There is no installer -- the customer unzips a folder and double-clicks an
    exe -- so first run IS the install, and this is where the icon has to come
    from. Leaving it to a .bat they have to notice and run is exactly the step
    people skip.

    Done through PowerShell rather than win32com: creating a .lnk needs COM,
    and shelling out avoids depending on pywin32's COM layer surviving the
    PyInstaller bundle. It also gets Desktop-folder redirection right for free
    -- GetFolderPath follows the OneDrive redirect that catches everyone out,
    where the raw %USERPROFILE%\\Desktop path does not.
    """
    exe = base_dir / "StarCitizenVoiceControl.exe"
    if not exe.exists():
        return None                      # running from source; nothing to link

    # The program, plus both command cards. The cards are the thing people
    # actually need open while flying, and hunting for a .jpg inside a
    # program folder is exactly the friction that stops them being used.
    # All three carry the app icon so they read as one product on the Desktop.
    wanted = [
        (exe, "Star Citizen Voice Control", "Voice commands for Star Citizen"),
        (base_dir / "Voice Command Reference.jpg",
         "SC Voice Commands - Quick Card", "The commands you'll use most"),
        (base_dir / "Voice Command Reference - Full.jpg",
         "SC Voice Commands - Full List", "Every command and every phrase"),
    ]

    def q(value):                        # PowerShell single-quote escaping
        return str(value).replace("'", "''")

    made = []
    for target, name, description in wanted:
        if not target.exists():
            continue
        script = (
            "$ErrorActionPreference='Stop';"
            "$d=[Environment]::GetFolderPath('Desktop');"
            "if(-not $d -or -not (Test-Path $d)){$d=Join-Path $env:USERPROFILE 'Desktop'};"
            f"$p=Join-Path $d '{q(name)}.lnk';"
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($p);"
            f"$s.TargetPath='{q(target)}';"
            f"$s.WorkingDirectory='{q(base_dir)}';"
            f"$s.IconLocation='{q(exe)},0';"
            f"$s.Description='{q(description)}';"
            "$s.Save();"
            "if(Test-Path $p){Write-Output $p}"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        out = (result.stdout or "").strip().splitlines()
        if out and Path(out[-1]).exists():
            made.append(Path(out[-1]))

    # First entry is the program shortcut; callers treat it as "the" shortcut.
    return made[0] if made else None


def show(base_dir: Path, keybind_lines, build_line: str):
    """Open the reference card and the first-run note. Returns what opened.

    Never raises: a customer whose PC has no default handler for .jpg
    should still end up with a running program, not a crash on launch.
    """
    opened = []

    # Do this first: an icon on the Desktop is the whole difference between
    # "where did it go?" and a customer who can relaunch it tomorrow.
    shortcut = create_desktop_shortcut(base_dir)

    try:
        note = _write_note(base_dir, keybind_lines, build_line, shortcut)
    except OSError:
        note = None

    for target in (base_dir / REFERENCE_CARD, note):
        if target is None or not target.exists():
            continue
        try:
            os.startfile(str(target))       # noqa: S606 - Windows-only by design
            opened.append(target.name)
        except OSError:
            pass

    if shortcut:
        opened.append(f"Desktop shortcut -> {shortcut.name}")

    try:
        (base_dir / MARKER).write_text(
            "Delete this file to see the first-run reference card and note again.\n",
            encoding="utf-8")
    except OSError:
        pass                                 # read-only folder: just show it again next time

    return opened
