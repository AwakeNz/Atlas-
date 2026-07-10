# A.T.L.A.S. — Architecture (Phase 1: Architect)

A plugin-based AI desktop assistant for Windows, shipped as a single PyInstaller `.exe`.

---

## 1. Module diagram

```
                                   ┌──────────────────────────────┐
                                   │          main.py             │
                                   │  bootstrap / wiring / paths  │
                                   └──────────────┬───────────────┘
                                                  │
        ┌───────────────────┬─────────────────────┼───────────────────┬──────────────────┐
        ▼                   ▼                     ▼                   ▼                  ▼
┌───────────────┐  ┌────────────────┐  ┌──────────────────┐  ┌───────────────┐  ┌──────────────┐
│  ui/hud.py    │  │ core/agent.py  │  │ core/plugins.py  │  │ core/memory.py│  │ core/llm.py  │
│  tkinter HUD  │  │ ReAct loop     │  │ hot-loader +     │  │ MemoryStore   │  │ LLMProvider  │
│  orb, stream, │◄─┤ (worker thread)│─►│ registry +       │  │ (SQLite impl) │  │ (Groq impl)  │
│  confirm modal│  │ max 8 steps    │  │ sandboxed calls  │  └───────┬───────┘  └──────┬───────┘
└──────┬────────┘  └───────┬────────┘  └────────┬─────────┘          │                 │
       │ EventBus (queue)  │                    │                    ▼                 ▼
       │◄──────────────────┘                    ▼               memory.db         Groq API
       ▼                                  plugins/*.py         (next to exe)   (chat + whisper)
┌───────────────┐   ┌────────────────┐
│ voice/stt.py  │   │ voice/tts.py   │        Support: core/config.py (settings.json),
│ push-to-talk  │   │ edge-tts       │        core/log.py (atlas.log), core/updater.py
│ → Groq whisper│   │ British male   │        (GitHub releases version check)
└───────────────┘   └────────────────┘
```

**Threading model** — exactly three kinds of threads:

| Thread | Owns | Talks to others via |
|---|---|---|
| Main (tkinter) | All widgets, canvas animation, modals | reads `EventBus` queue on a 33 ms `after()` tick |
| Agent worker (one at a time) | LLM calls, plugin execution, memory writes | posts events to `EventBus`; blocks on `threading.Event` for confirmations |
| Utility threads | TTS playback, updater check, `keyboard` hook callbacks | post to `EventBus` only |

No widget is ever touched off the main thread. No plugin ever runs on the main
thread. This is the single rule that makes the whole app thread-safe (see
`docs/CODE_REVIEW.md` §4 for the audit).

## 2. Data flow: hotkey → STT → agent → plugin → memory → TTS

```
Ctrl+Space (keyboard hook thread)
   └─► EventBus: TOGGLE ─► HUD shows, focuses input        [state: IDLE, orb breathing]
Hold F8 (push-to-talk)
   └─► stt.py records mic (sounddevice, 16 kHz mono)       [state: LISTENING, orb pulses]
Release F8
   └─► WAV bytes → GroqProvider.transcribe() → text
   └─► same path as typed text ↓
User text submitted
   └─► Agent.run(text) on worker thread                    [state: THINKING, orb spins]
        ├─ builds messages: system prompt + MemoryStore.summary() + rolling history
        ├─ LLMProvider.chat(messages, tools=registry.schemas(), stream_cb)
        │     └─► streamed tokens → EventBus: STREAM → HUD types them out
        ├─ if tool_calls:
        │     ├─ EventBus: TOOL("EXECUTING: send_discord_message")
        │     ├─ requires_confirmation? → EventBus: CONFIRM → modal on UI thread
        │     │       agent thread blocks on threading.Event (60 s timeout = deny)
        │     ├─ registry.execute() — plugin exceptions are caught, logged,
        │     │       returned to the LLM as a tool error string (it can recover)
        │     └─ loop (≤ 8 steps, then forced report-back)
        ├─ MemoryStore.log_history(command, outcome) + habit tick
        └─ final text → EventBus: SPEAK → tts.py (edge-tts, async in thread)
                                                            [state: SPEAKING, orb ripples]
```

## 3. Plugin lifecycle

1. **Discover** — at startup, `core/plugins.py` globs `<exe dir>/plugins/*.py`
   (files starting with `_` are skipped; `EXAMPLE_plugin.py` is loaded — it is a
   working plugin as well as documentation).
2. **Load** — each file is imported with `importlib.util.spec_from_file_location`
   under a namespaced module name (`atlas_plugin_<stem>`), so plugin modules can
   never shadow stdlib or app modules, and two plugins with the same filename
   stem in theory still collide loudly rather than silently.
3. **Validate** — the loader accepts a `Plugin` class or a `PLUGINS` list (one
   file can export several tools, e.g. `remember` + `recall`). Each instance
   must expose `name`, `description`, `parameters`, `requires_confirmation`,
   `execute`. Anything malformed is logged and skipped — a broken plugin never
   prevents startup.
4. **Register** — descriptions and JSON-schema parameters are converted verbatim
   into OpenAI-style function schemas for the LLM.
5. **Execute** — always on the agent worker thread, always inside try/except,
   always with a wall-clock log line before and after. The plugin receives a
   `PluginContext` (`ctx`) giving it: `ctx.memory` (MemoryStore), `ctx.config`
   (settings), `ctx.llm` (recursive model calls), `ctx.confirm()`,
   `ctx.notify()`, `ctx.app_dir`.
6. **Fail** — exceptions become `"[plugin error] ..."` tool results fed back to
   the LLM; the app never dies because a plugin did.

There is no unload/reload at runtime in v1 — restart to pick up plugin changes.
(Hot *reload* is a seam: the registry is rebuilt from disk by one function.)

## 4. Tradeoff: `tkinter` vs `pywebview` — **tkinter wins**

| Criterion | tkinter Canvas | pywebview + HTML/CSS |
|---|---|---|
| Runtime dependency | None — stdlib | Requires Edge WebView2 runtime installed & matching |
| Exe size | ~12 MB baseline | +30–50 MB, and pythonnet/webview wheels |
| Cold start | ~0.5 s | 1.5–3 s (WebView2 process spawn) |
| Frameless/topmost/transparent | `overrideredirect` + `-transparentcolor` + `-topmost`, all native | Supported but click-through & transparency are flaky per WebView2 version |
| Orb animation | Canvas at 30 fps — trivial for arcs/ovals | Better (CSS/canvas shaders) |
| JS↔Python bridge | N/A — one process, one language | Extra IPC layer, extra thread-safety surface |
| Dependency budget (10 pkgs) | 0 packages | 1–2 packages |

The only thing pywebview genuinely buys is prettier shaders. The orb we need
(pulse / spin / ripple) is arcs and alpha-stepped ovals — comfortably within
Canvas. Against the hard constraints (<100 MB, sub-2 s cold start, single exe,
10-package cap, no runtime installs on the user's machine), **tkinter is the
only defensible choice**. Decision: tkinter.

## 5. Provider abstraction

`core/llm.py` defines `LLMProvider` (abstract): `chat(messages, tools,
stream_cb) -> ChatResult` and optional `transcribe(wav_bytes) -> str`.
`GroqProvider` implements both over raw HTTPS (`requests`) against Groq's
OpenAI-compatible endpoints — chat streaming via SSE, STT via
`whisper-large-v3` on the same free key. A Gemini or Ollama provider is a new
~80-line class and one `settings.json` field (`"provider": "groq"`); nothing
else in the app knows which provider is live.

## 6. Memory

`MemoryStore` is an interface; `SQLiteMemoryStore` is the v1 implementation
over `memory.db` (next to the exe, WAL mode, one connection per thread via
`threading.local`). Tables:

- `facts(id, fact, source, created_at)` — user-stated truths
- `history(id, command, outcome, ok, created_at)` — every agent run
- `habits(id, key, hour_bucket, count)` — app launches / tool use by hour

`summary()` returns a compact block (top-N recent facts + top habits) injected
into the system prompt at the start of every agent run. **Vector search is a
deliberate seam, not a feature**: swap `SQLiteMemoryStore` for a
`VectorMemoryStore` (sentence-transformers + sqlite-vec) behind the same
interface; the agent loop does not change.

## 7. Files on disk (next to the exe — the contract)

```
ATLAS.exe          settings.json       apps.json
plugins/*.py        skills/*/SKILL.md   memory.db          atlas.log
```

`core/config.py` resolves `app_dir()` as `Path(sys.executable).parent` when
frozen, the repo `atlas/` dir in dev, and materializes default `settings.json`
/ `apps.json` / `plugins/` on first run so a bare exe self-heals.

## 8. Dependency budget (8 of 10 used)

`requests`, `edge-tts`, `keyboard`, `pygetwindow`, `pydirectinput`,
`sounddevice`, `Pillow`, `pystray`. Everything else is stdlib (tkinter,
sqlite3, wave, ctypes, asyncio). Two slots held in reserve for the
vector-memory upgrade.

## 9. Skills subsystem (v0.1 addition)

Plugins are **capabilities** (verbs: send, click, launch). Skills are
**knowledge** (workflows, procedures, style guides) — markdown folders in
`<exe dir>/skills/`, no code. `core/skills.py` owns the whole layer.

```
skills/<name>/SKILL.md            frontmatter: name, description
              <support files>     templates, examples, reference docs

startup            agent run                 on demand
───────            ─────────                 ─────────
scan skills/  ──►  index in system prompt ─► use_skill(name)
(frontmatter       "- name: description"     → full SKILL.md body
 only, stops       ≤ ~50 tokens per skill    → lists support files
 at the fence)                               read_skill_file(skill, path)
                                             → sandboxed file read
```

**Progressive disclosure** keeps token cost flat: only the one-line index is
always present; bodies (and support files) enter the context only when the
model asks. **Hot reload**: `manage_skills(reload)` — or the tray menu —
rescans the folder; `SkillsIndex` swaps its dict under a lock, so worker
threads never see a half-built index. Bodies are re-read from disk on every
`use_skill`, so editing a SKILL.md takes effect immediately even without a
reload.

**Security boundary**: skills are text fed to the model, never code. Nothing
in a skill folder executes automatically; a skill that wants a script run
must convince the model to call `run_shell`, which still applies its
whitelist and confirmation modal. `read_skill_file` is jailed to the skill's
own folder (no absolute paths, no `..`, symlinks that resolve outside are
rejected after `resolve()`). The tray icon (`ui/tray.py`, pystray) exposes
show/hide, skills list/reload, and quit — every action posts to the EventBus
or calls the thread-safe `SkillsIndex`; it never touches tkinter.


---

# v0.2 addendum — provider chain · FUI · hands-free voice · auto-update

## 10. LLM provider fallback chain

All three providers speak the OpenAI wire format, so one `OpenAICompatProvider`
(raw HTTPS) covers them; only base URL/key/model differ.

```
gemini (primary)  →  https://generativelanguage.googleapis.com/v1beta/openai
groq   (fallback) →  https://api.groq.com/openai/v1
cerebras          →  https://api.cerebras.ai/v1   (model list queried live)
```

`ProviderChain` is **sticky within a request, resettable between requests**:
on a 429/quota/5xx/network error it advances to the next provider and emits
`PROVIDER → GROQ` to the HUD; a real error (bad key/request) propagates
immediately instead of burning the whole chain. The agent calls `reset()` at
the start of each user turn so it always retries from Gemini. No index ever
wraps past the end — the chain is tried at most once per call (no infinite
loop). Cerebras' free catalog drifts, so its model is discovered at startup
from `GET /models` rather than hardcoded.

**Token diet.** A cheap heuristic (`Agent._is_trivial`: short + an action verb
like open/volume/lock) routes one-shot commands to each provider's *small*
model (`gemini-2.5-flash-lite` / `llama-3.1-8b-instant`); the big model is used
only once a request needs a second step. History is trimmed to the last N=12
turns, with older turns folded into a single system summary line so context
stays bounded.

## 11. UI reversal — pywebview becomes primary (tkinter is the fallback)

v0.1 chose tkinter to avoid the WebView2 dependency. v0.2's brief calls for
glassmorphism depth, animated data-readout panels, a boot sequence and richer
micro-interactions — all of which are HTML/CSS-native and awkward on a Canvas.
So the decision is **reversed on purpose**: pywebview (vanilla HTML/CSS/JS, no
JS framework) is now primary, and `main._make_hud` falls back to the original
tkinter HUD automatically if pywebview/WebView2 is unavailable. Both consume
the same EventBus and expose the same `run()`/`set_speaker()` surface, so the
agent/voice/tray code is UI-agnostic. The JS bridge: a pump thread drains the
bus and pushes batched events via `window.evaluate_js`; JS calls back through
`pywebview.api`. Style follows the ui-ux-pro-max **HUD / Sci-Fi FUI** guidance
(1px lines, glow, corner brackets, scanlines, Orbitron+JetBrains Mono) with its
accessibility discipline layered on (≥4.5:1 body text, 150–300ms motion, full
`prefers-reduced-motion` fallback).

## 12. Hands-free voice pipeline (all local)

```
continuous 16kHz mic ─► openWakeWord (ONNX, 80ms frames) ─► score>thresh
   ─► chime + orb:listening ─► webrtcvad records to 1.2s silence
   ─► faster-whisper (base, CPU int8) ─► agent.submit ─► TTS
```

CPU discipline: the sounddevice callback only *enqueues* frames; all ONNX
inference is on one worker that blocks on the queue, keeping idle cost to the
mel+embedding pass per 80ms (< 3%). **Mute genuinely stops capture** — the
input stream is closed, not just ignored. Push-to-talk and text remain
fallbacks. Whisper + wake models are **not bundled**: they download to
`models/` on first run (resumable, HUD progress bar), and everything after is
offline. Audio never leaves the machine.

## 13. Verified update path

`GET /repos/<repo>/releases/latest` → semver compare (rejects same/older) →
on confirm, download the `ATLAS.exe` asset (HTTPS only) with progress → verify
SHA-256 against the release's `ATLAS.exe.sha256` → spawn a detached
`update.bat` that waits for the process to exit, swaps the locked exe (retrying
up to 15× if still locked), and relaunches. Never silent; `plugins/`, `skills/`,
`settings.json`, `memory.db`, `models/` are never touched. The release side is
`.github/workflows/release.yml` (builds, checksums, drafts a Release on tag
push) + `release.md`.

## 14. Dependency budget — deliberate expansion

v0.1's 10-package cap is intentionally exceeded in v0.2 (~14): a *local* voice
pipeline (openWakeWord, onnxruntime, faster-whisper, webrtcvad, numpy) and a
pywebview FUI cannot be built within the old cap. Everything still lazy-imports,
so cold start stays < 2 s (voice + provider chain init after the window shows).


---

# v0.3 addendum — installer, data separation, in-place upgrades

## 15. paths.py — one place for every location

Program files are now read-only (Program Files), so all user data moved to
`%APPDATA%\ATLAS`. `core/paths.py` is the single authority:

```
program_dir()  install dir / dev repo (read-only)
bundle_dir()   PyInstaller _MEIPASS (bundled plugins/skills/web/wake/assets)
data_dir()     %APPDATA%\ATLAS  ← settings, apps.json, plugins, skills,
               memory.db, models/, atlas.log
```

Every module imports its paths here (`log_path`, `memory_db`, `plugins_dir`,
`skills_dir`, `models_dir`, `settings_path`); `config.app_dir` is kept only as a
compatibility alias to `data_dir`. `migrate_legacy()` runs once on first launch
of an installed build and moves any files a pre-0.3 build wrote next to the exe
into `data_dir` — never overwriting newer data. It's a no-op in a dev checkout,
so the repo's own `plugins/`/`skills/` are never disturbed. Cost is a handful of
`os.path.exists` checks → no measurable cold-start impact.

## 16. Inno Setup installer + uninstaller

`installer/atlas.iss` produces `ATLAS-Setup-v<version>.exe` (the release asset).

- **Fixed `AppId` GUID** ⇒ Windows treats every future version as an *upgrade*
  of one app (single Apps & features entry), never a second install.
- **Data separation is structural:** the installer only ever writes to
  `{app}` (Program Files); it never creates or touches `%APPDATA%\ATLAS`. An
  upgrade replaces program files and leaves user data byte-for-byte intact.
- **`AppMutex=Global\ATLAS_Running_Mutex`** matches the mutex the app creates
  at startup (`core/singleton.py`), so Setup detects a running instance;
  `CloseApplications`/`RestartApplications` (Restart Manager) close and relaunch
  it for a seamless in-place upgrade.
- **Options:** desktop shortcut, launch-at-startup via the **HKCU Run key**
  (not the Startup folder), launch-after-install.
- **Uninstaller** (auto, in Apps & features) removes program files, shortcuts
  and the Run key (`uninsdeletevalue`); a `[Code]` step asks *"Keep your
  settings, memory and plugins?"* (default **Yes**) and only deletes
  `%APPDATA%\ATLAS` if the user declines — and never in silent mode.
- **Size/speed:** `Compression=lzma2/max` + `SolidCompression`; a single small
  exe installs in well under 10 s on an SSD.

## 17. Updater rework (installer-based)

The download-exe + `.bat`-swap is gone. Now: check latest release → semver
compare (reject downgrades) → download `ATLAS-Setup-v<new>.exe` to `%TEMP%`
(HTTPS only) with progress → verify SHA-256 against the release's `.sha256` →
run it `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`. Inno owns the
close-swap-relaunch that the `.bat` botched, and never touches user data. Still
gated on explicit HUD confirmation. Release side: `build.py` (icon → PyInstaller
→ iscc → checksums → `dist/release/`) and the updated Actions workflow.

## 18. Icon pipeline

`build.py:make_icon` converts the supplied `icon.png` → `assets/atlas.ico` with
all standard sizes (16/24/32/48/64/128/256), high-quality LANCZOS downscale,
alpha preserved, non-square art padded (not stretched). Missing `icon.png` →
generated placeholder + warning (build never fails). The `.ico` is wired into
the exe (PyInstaller `--icon`), tray glyph, tkinter window icon, installer
wizard (`SetupIconFile`), Add/Remove Programs (`UninstallDisplayIcon`) and all
shortcuts.
