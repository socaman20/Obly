# Star Citizen Voice Control

**Hold a button, say what you want, and it presses the key for you.**

> "Landing gear." &nbsp;·&nbsp; "Power to shields." &nbsp;·&nbsp; "Set route to Lorville."

Free. Made by **Obly**.

![Voice Command Reference](Voice%20Command%20Reference.jpg)

---

## Download

**[Get the latest release &rarr;](../../releases/latest)**

**Windows 10 or 11 only.** Not Mac, not Linux, and that is not an oversight --
see [Why Windows only](#why-windows-only) below.

1. Right-click the zip, choose **Extract All**
2. Open the folder
3. Double-click **START HERE**

That is the whole install: nothing goes into Program Files, nothing touches the
Windows registry. To uninstall, delete the folder.

It checks for Microsoft's WebView2 runtime -- part of Windows 11, often absent
on Windows 10 -- and installs it for you if it is missing. Microsoft's own
installer ships inside the download, so it works even if that download would
have been blocked on your network.

**"There is no .exe in here."** There is. Windows hides file extensions by
default, so the program shows up as `StarCitizenVoiceControl` with a ship icon
rather than `StarCitizenVoiceControl.exe`. If there is genuinely no such file,
either you ran it from inside the zip without extracting, or your antivirus
removed it -- this is unsigned and it types on your keyboard for you, which is
exactly what antivirus software watches for. Check your quarantine.

Windows may say **"Windows protected your PC"** the first time. That appears
for every unsigned program. More info &rarr; Run anyway.

---

## It listens on your PC

There is no account, no server and no sign-up. Speech recognition runs locally
through Whisper, and the model ships inside the download — with the internet
off, everything except price updates still works. Nothing you say leaves your
machine.

## Two ways to talk to it

**Push to talk** — hold a key, a HOTAS button, or a gamepad button. All three
work at once, so use whichever is under your hand. Press your stick button on
the Listen page and it learns it.

**Open mic** — no button at all. Set a wake word so only speech that starts
with it counts; without one, every sentence in the room is a candidate,
including whatever is coming out of Discord.

Either way, nothing fires unless Star Citizen is the window in front.

## Plotting a route by voice

```
"open map"                opens the starmap
"set route to Lorville"   clicks the search box, types it, presses Enter, stops
"set GPS"                 confirms it
"close map"               done
```

It corrects what it heard against every place in the game *before* typing, so
"laura ville" becomes **Lorville** and "new beverage" becomes **New Babbage**.
Name somewhere that isn't in the current build and it tells you, instead of
typing a name the game has never heard of.

It matches by sound as well as spelling, because these names aren't English
words and speech recognition mangles them in predictable ways — "art court"
finds **ArcCorp**.

## When a command does nothing

Almost always this is the game's keybind, not the program. Star Citizen lets
you clear a binding or move it to a joystick, and a cleared binding has no key
for anything to send.

**How To → "Read my keybinds"** reads your own `actionmaps.xml` and lists which
commands can't work on your layout and why. It only looks; it changes nothing.

## What else is in there

| | |
|---|---|
| **Starmap** | every system, moon and landing zone at its real orbital distance — and where you are, read from the game's own log |
| **Routes** | every destination you plotted. Star Citizen forgets these when you log out; this doesn't |
| **Market** | ship and commodity prices, updated from live community data |
| **Commands** | all 52, each with an on/off switch and the key it sends |
| **My Commands** | your own, kept safe from updates |

---

## Why Windows only

Star Citizen is a Windows game. There is no Mac version, so a Mac build would
be a voice controller for a game that cannot be on the machine.

Beyond that, this program is Windows-bound by what it does, not by how it was
written:

- it **sends keystrokes into a running game**, through a Windows input layer
- it **reads your HOTAS** through Windows' own joystick APIs
- it **draws its window** with WebView2, a Microsoft component
- it **reads your keybinds** out of Star Citizen's own `actionmaps.xml`

The download is a Windows executable. On a Mac it will not open at all.

**Linux is the arguable one**, because plenty of people run Star Citizen
through Proton. That is a real port -- a different input layer, a different
window toolkit, a different joystick API -- and it would be a separate build
rather than a setting. If enough people want it, say so in an issue.

## Building it yourself

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m PyInstaller VoiceControl.spec --noconfirm
```

Two things aren't in this repository and you'll need them to build:

- **`whisper_model/tiny.en/`** — the speech model, ~75 MB, from
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper). It's a
  third-party model, so it ships in the release rather than in git.
- **`config/datacache/`** — cached price data. Rebuilds itself on first run.

Run from source with `python app.py`.

## Credits and data

Place and route data comes from Roberts Space Industries' own starmap service.
Prices and terminals come from [UEX](https://uexcorp.space/). This is a fan
tool: not affiliated with, endorsed by, or connected to Cloud Imperium Games.

---

## Thanks

It's free and always will be. If it saved you some hassle and you want to throw
something in the hat, that's the hat: **[cash.app/$Obly](https://cash.app/$Obly)**
