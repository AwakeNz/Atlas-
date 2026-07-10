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
