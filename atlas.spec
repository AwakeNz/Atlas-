# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for A.T.L.A.S. Build with:  pyinstaller atlas.spec
#
# Notes that matter:
# - onefile + console=False (windowed): no console window ever appears.
# - Plugins are loaded FROM DISK at runtime, so PyInstaller's import tracer
#   never sees their dependencies — every library a built-in plugin lazily
#   imports must be listed in hiddenimports below, or the frozen exe will
#   raise ImportError the first time that plugin runs.
# - plugins/ and skills/ are bundled as data; on first run
#   config.ensure_user_files() copies both NEXT TO the exe so users can
#   edit/add their own.
# - excludes trims libraries Pillow/others drag in that we never use; this is
#   most of how we stay far under the 100 MB budget.

block_cipher = None

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    # web/ ships the FUI; wake/ ships the wake-word docs (and atlas.onnx once
    # trained). Heavy voice/ONNX models are NOT bundled — they download to
    # models/ on first run (see core/models.py) to keep the exe small.
    datas=[("plugins", "plugins"), ("skills", "skills"),
           ("src/ui/web", "ui/web"), ("wake", "wake")],
    hiddenimports=[
        # lazily imported by core/ui at runtime
        "requests", "edge_tts", "pystray", "pystray._win32", "webview",
        # voice pipeline (lazy)
        "onnxruntime", "openwakeword", "openwakeword.model", "faster_whisper",
        "webrtcvad", "numpy",
        # lazily imported by plugins loaded from disk
        "keyboard", "pygetwindow", "pydirectinput", "sounddevice",
        "PIL.ImageGrab", "PIL.Image", "PIL.ImageDraw",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "unittest", "pydoc", "doctest", "test",
        "matplotlib", "scipy",                    # never ours; block accidental pulls
        "PIL.ImageTk", "PIL.ImageQt", "PIL.ImageShow",
        "setuptools", "pip", "wheel",
        "xmlrpc", "curses", "lib2to3",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ATLAS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,               # harmless if UPX absent; ~30% smaller if present
    upx_exclude=["vcruntime140.dll", "python3*.dll"],
    runtime_tmpdir=None,
    console=False,          # HARD REQUIREMENT: no console window
    disable_windowed_traceback=False,
    icon=None,              # drop an atlas.ico here when you have one
)
