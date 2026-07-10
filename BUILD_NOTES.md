# A.T.L.A.S. build notes

Running log of problems found and their fixes while producing a launchable build.

## Phase 0 — environment check

**Finding (blocking for Phases 2–3): this session runs on Linux, not Windows.**

```
uname -a      → Linux vm 6.18.5 ... x86_64 GNU/Linux   (uname SUCCEEDS)
%OS%          → unset                                   (would be Windows_NT on Windows)
sys.platform  → linux
python        → 3.11.15, pip 24.0
Pillow        → 12.3.0 present
requests      → present
numpy         → MISSING
tkinter       → NOT importable (no _tkinter in this container)
iscc          → not installed
icon.png      → NOT present in repo root
xvfb          → present (but no tkinter to drive)
```

Consequences (facts, not opinions):
- **PyInstaller cannot cross-compile.** On Linux it emits an ELF binary, never a
  Windows `.exe`. A Windows exe must be built on Windows.
- **Inno Setup (`iscc`) is Windows-only.** No installer can be compiled here.
- **The HUD can't launch here.** pywebview needs Windows + WebView2; the tkinter
  fallback needs `_tkinter`, which isn't in this container.

So Phases 1–3 as written ("launch the HUD", "build the exe", "compile the
installer") require a Windows host — either the user's machine or the
`windows-latest` GitHub Actions runner, which already runs icon→PyInstaller→
Inno→checksums on tag push.

What IS done here (portable, verified on Linux; de-risks the Windows build):
- Integration smoke of `main()` wiring with unavailable deps stubbed → catches
  refactor bugs before they hit Windows.
- PyInstaller spec converted onefile → **onedir** (Phase 2 requirement) + a
  console-debug build toggle.
- Inno installer updated to install the onedir **folder tree**.
- `requirements.txt` pinned.
- `build.py` output paths updated for onedir.

---

## Fix log

### 1. Integration smoke of `main()` wiring — PASS
Ran `main.main()` headless with unavailable deps stubbed (pywebview→fake HUD,
numpy stub) under xvfb. Result: returned 0, no exceptions from the v0.3 refactor
(paths.py, singleton mutex, tray `controls` dict, updater signatures).
Verified `%APPDATA%\ATLAS` (XDG on Linux) is created with settings.json,
apps.json, plugins/, skills/, memory.db, models/, atlas.log. → Phase 1 config
migration / first-run bootstrap is correct as far as a headless box can prove.

### 2. PyInstaller spec → onedir (Phase 2 requirement)
Converted `atlas.spec` from onefile to **onedir**: `EXE(exclude_binaries=True)`
+ `COLLECT(...)` → `dist/ATLAS/ATLAS.exe`. Added `ATLAS_DEBUG_CONSOLE=1` env
toggle → console build for capturing tracebacks on silent failure, else windowed
(`console=False`). Icon wired via `icon="assets/atlas.ico"`.

### 3. Installer updated for onedir
`installer/atlas.iss` `[Files]` now installs the whole folder tree
(`..\dist\ATLAS\*` with `recursesubdirs createallsubdirs`) into `{app}`, not a
single exe. `{app}\ATLAS.exe` remains the launch target / shortcut / mutex.

### 4. build.py output path
`run_pyinstaller()` now looks for `dist/ATLAS/ATLAS.exe` and reports the folder
size.

### 5. requirements.txt pinned
Pinned to a coherent baseline; **numpy held at 1.26.4** (numpy-2 ABI mismatch vs
onnxruntime/faster-whisper is the classic silent frozen-app crash). Exact
cross-resolution must be confirmed on the Windows build host (couldn't `pip
install` the Windows-only stack here).

### Not doable in this environment (Linux container)
- Building `dist/ATLAS/ATLAS.exe` — PyInstaller cannot cross-compile to Windows.
- Compiling `ATLAS-Setup-v{version}.exe` — `iscc` is Windows-only.
- Launching/round-tripping the HUD — no `_tkinter`, no WebView2, no display.
These require a Windows host: the user's machine, or the `windows-latest` CI
runner (`.github/workflows/release.yml`, which already runs the full chain).

### 6. CI build failure (run #1) — webrtcvad hook — FIXED
`python build.py` on windows-latest failed at PyInstaller with:
`ImportErrorWhenRunningHook: hook-webrtcvad.py` ← `PackageNotFoundError: No
package metadata was found for webrtcvad`.

Root cause: I'd swapped `webrtcvad` → `webrtcvad-wheels` to dodge the C-compiler
requirement. That package installs the **module** `webrtcvad` but its
**distribution** is named `webrtcvad-wheels`, so the bundled contrib hook's
`copy_metadata('webrtcvad')` raised and aborted the whole build. (Icon step was
fine — `[icon] using icon.png (256x256)` — so this was never icon-related.)

Fix: dropped the webrtcvad dependency entirely. End-of-utterance silence
detection now uses a pure-stdlib **RMS energy gate** (`audioop.rms`) with an
adaptive noise floor in `voice/wake.py` — no wheel, no compiler, no fragile
hook. Removed webrtcvad from `requirements.txt` and the spec `hiddenimports`.
Verified `audioop` thresholds on synthetic loud/quiet frames.

### 7. Confirm panel visible from launch, unclickable — REAL root cause — FIXED
Symptom: "Deny/Allow shows at startup and nothing is pressable" (persisted
across reinstall; the earlier easy_drag fix was contributory but not the cause).

Root cause: the HTML `hidden` attribute maps to UA-level `display: none`, which
**any author `display` rule overrides**. `.modal-scrim { display: grid }`
(z-index 40, `position: fixed; inset: 0`) therefore ignored its `hidden`
attribute and covered the entire window from launch, swallowing every
click/tap. `.update-banner { display: flex }` and `.hud { display: grid }` had
the same latent bug.

Fix (styles.css): `[hidden] { display: none !important; }` — the attribute now
always wins. Hardening (app.js): `answer()` now always dismisses the scrim even
when no confirmation is pending, so a stray overlay can never trap the UI.
