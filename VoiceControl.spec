# -*- mode: python ; coding: utf-8 -*-
"""Package the window, not the console.

WHY A SECOND SPEC
-----------------
StarCitizenVoiceControl.spec builds main.py: a single-file console program,
which is what testers were given before there was a window. This builds app.py
-- the actual app -- and differs in three ways that matter:

  windowed      console=False, so double-clicking opens the app and not a
                black box behind it.

  one folder    not one file. A one-file build unpacks 200 MB of Whisper model
                to a temp directory on every launch, which is several seconds
                of nothing happening before the window appears. A folder
                starts immediately, and zips just as well.

  data included webui/ (the interface and the starmap), config/ (commands,
                places, schemes, cached prices) and whisper_model/ all ship
                inside it, so there is nothing to install and nothing to
                download on first run.
"""
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['win32timezone', 'winsound', 'clr_loader', 'pythonnet',
                 'clr', 'voiceui', 'voiceui.store', 'voiceui.datacache']

# pythonnet is not optional here even though nothing imports it by name:
# pywebview's edgechromium backend reaches WebView2 through .NET, so a build
# without it opens a window and renders an empty page -- which is exactly what
# the first build did.
# cryptography was here for the licence signing. The free build has no
# licence, so it was 10 MB of a download nobody needs.
for pkg in ('faster_whisper', 'ctranslate2', 'tokenizers', 'pyttsx3',
            'pygame', 'webview', 'clr_loader', 'pythonnet'):
    got = collect_all(pkg)
    datas += got[0]
    binaries += got[1]
    hiddenimports += got[2]

# Everything the program reads at runtime, kept in the same shape it has in
# the source tree so the paths in the code do not change between running from
# source and running the packaged copy.
datas += [
    ('webui', 'webui'),
    ('config', 'config'),
    # ONLY the model the config actually selects. Both were shipping --
    # base.en at 141 MB sat unused next to tiny.en at 75 MB, because nothing
    # in the interface can switch to it. That was 141 MB of every download
    # for a file that never opened.
    ('whisper_model/tiny.en', 'whisper_model/tiny.en'),
    ('voice_acks', 'voice_acks'),
    ('app_icon.ico', '.'),
    # Shipped so the reference card is in the folder people receive, not
    # somewhere they have to be sent separately.
    ('Voice Command Reference.jpg', '.'),

]

a = Analysis(
    ['app.py'],
    pathex=['../_shared'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PyQt5', 'PySide2', 'PySide6',
              # Nothing in the running program imports these. PIL was pulled
              # in by a build script, cryptography by the licence code that
              # is gone, hf_xet by a model downloader we never call because
              # the model ships inside.
              'PIL', 'cryptography', 'hf_xet', 'huggingface_hub'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StarCitizenVoiceControl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX stays off. A packed binary is one of the strongest antivirus
    # heuristics there is, and we are already unsigned and sending
    # keystrokes -- we do not need a third strike.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon='app_icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='StarCitizenVoiceControl',
)
