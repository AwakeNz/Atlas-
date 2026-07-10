# A.T.L.A.S. — Autonomous Task & Logic Assistance System

**v0.3** · one-click Windows installer · in-place upgrades that keep your data · Gemini-first LLM chain · hands-free wake word · pywebview FUI

A general-purpose, plugin-based AI desktop assistant for Windows. A frameless,
always-on-top HUD with an animated violet orb: summon it with **Ctrl+Space**,
type or hold **F8** to talk, and it acts on your PC through hot-loaded
plugins — and follows workflows you teach it through drop-in **skills**.
Powered by Groq's free tier, with the provider abstracted so Gemini/Ollama
can drop in later.

```
ATLAS.exe             ← the whole app, one file, no Python needed
settings.json         ← your config (created on first run)
apps.json             ← your app launch registry
plugins\              ← drop a .py file here → new capability (a verb)
skills\               ← drop a folder here  → new workflow  (knowledge)
memory.db             ← long-term memory (facts / history / habits)
atlas.log             ← full action log
```

## Install

**Download `ATLAS-Setup.exe` from the [latest release](https://github.com/AwakeNz/Atlas-/releases/latest) -> run it -> done.** No Python, no console, no setup steps.

- The installer registers A.T.L.A.S. in **Apps & features** (proper uninstall),
  and offers optional **desktop shortcut** and **launch at Windows startup**.
- **Upgrades:** just run a newer `ATLAS-Setup.exe`, or accept the in-app update
  prompt -- Windows treats it as an upgrade of the same app and **keeps every
  byte of your settings, memory, plugins and skills**.
- **Where your data lives:** program files go to `Program Files\ATLAS`; all your
  data lives in `%APPDATA%\ATLAS` (`settings.json`, `plugins/`, `skills/`,
  `memory.db`, `models/`, `atlas.log`). Uninstalling asks whether to keep it --
  default **yes**.

### First run

1. Get a free API key (Gemini: [aistudio.google.com](https://aistudio.google.com/apikey), or Groq: [console.groq.com](https://console.groq.com)).
2. Launch A.T.L.A.S., open `%APPDATA%\ATLAS\settings.json`, paste your key into
   `providers`, and relaunch.
3. `Ctrl+Space` to summon/dismiss (also in the system tray). Type, or say
   **"Atlas"**, or hold `F8` to talk.


## What it can do out of the box

Everyday things: open apps, control volume/brightness, take screenshots,
find and focus windows, run whitelisted console commands, draft and save
code, send a Discord message, remember facts about you, and follow any
workflow you install as a skill.

| Tool | What | Guardrail |
|---|---|---|
| `open_app` | Launch apps from `apps.json` | registry keys only, never raw paths |
| `system_control` | Volume, brightness, lock, screenshot | — |
| `run_shell` | Run console commands | **whitelist + confirmation modal**, no shell, no pipes |
| `write_code` | Write code, open in your editor, optionally run | runs only in a sandbox temp dir, after a modal |
| `discord_message` | Send via your webhook/bot token | confirmation modal; credentials never shown to the model |
| `window_control` | List / focus / minimize windows | — |
| `game_interact` | Keys/clicks into a game you own | **only windows you whitelist** in `allowed_game_windows`, and only while focused |
| `remember` / `recall` | Long-term memory | — |
| `use_skill` / `read_skill_file` / `manage_skills` | The skills system (below) | reads sandboxed to each skill's folder |

> **Trust model:** plugins are ordinary Python running as you — the same deal
> as VS Code extensions. Only drop plugins you wrote or read into `plugins/`.
> Skills are safer: they're instructions, not code, and nothing in a skill
> folder is ever executed automatically.

## Skills: teach it workflows without code

Plugins are **capabilities** (verbs). Skills are **knowledge** — workflows,
procedures, style guides — written as markdown. At startup A.T.L.A.S. reads
only each skill's name + description into its context (progressive
disclosure); when a request matches, it loads the full instructions with its
`use_skill` tool and follows them.

### How to write a skill in 5 minutes

1. Create `skills/my-skill/SKILL.md`:

```markdown
---
name: meeting-notes
description: How to turn raw notes into a structured summary with action items. Use when the user asks to clean up or summarize notes.
---
When the user gives you raw meeting notes:
1. Extract decisions, action items (owner + due date), and open questions.
2. Output sections: **Summary**, **Decisions**, **Actions**, **Open**.
3. Keep the summary under 5 bullets. Use the template in template.md.
```

2. Optionally add support files (templates, reference docs, examples) to the
   same folder — the model reads them on demand with `read_skill_file`,
   which is locked to that skill's folder.
3. Say *"reload skills"* (or use the tray menu → Skills: reload). No restart.

Rules: `name` is lowercase letters/digits/`-`/`_`; `description` is one
sentence saying what the skill does **and when to use it** — it's the only
part that's always in the model's context, so make it count. A malformed
skill is logged to `atlas.log` and skipped, never fatal. See
`skills/example-email-tone/` for a heavily commented working example.

### Installing skills from GitHub

A skill is just a folder, so installing one is a copy:

1. Download or clone the repo containing the skill.
2. Copy the skill's folder (the one holding `SKILL.md`) into `skills/`.
3. Ask A.T.L.A.S. to *"reload skills"*, or use the tray menu.

Read a skill before installing it — skills steer the assistant's behavior.
They cannot bypass safety, though: if a skill tells A.T.L.A.S. to run a
script from its folder, that still goes through the `run_shell` whitelist
and confirmation dialog like any other command.

## How to write a plugin in 5 minutes

1. Copy `plugins/EXAMPLE_plugin.py` to `plugins/my_tool.py`.
2. Fill in four class attributes and one method:

```python
class Plugin:
    name = "get_weather"                       # what the LLM calls
    description = "Get current weather for a city. Use when asked about weather."
    parameters = {                              # JSON Schema for the arguments
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }
    requires_confirmation = False               # True → ALLOW/DENY modal first

    def execute(self, ctx, city: str) -> str:
        import requests                         # heavy imports go INSIDE execute
        r = requests.get(f"https://wttr.in/{city}?format=3", timeout=10)
        return r.text                           # this string goes back to the LLM
```

3. Restart A.T.L.A.S. Done — the model can now call `get_weather`.

Details worth knowing:
- `ctx` gives you `ctx.memory` (remember/recall), `ctx.config`
  (settings.json), `ctx.llm` (call the model recursively),
  `ctx.confirm(title, detail)`, `ctx.notify(text)`, `ctx.app_dir`.
- Your `description` is fed to the LLM verbatim — say what the tool does and
  when to use it.
- Raise freely: crashes are caught, logged to `atlas.log`, and reported to
  the model as a tool error. You cannot take the app down.
- One file can export several tools via a `PLUGINS = [...]` list — see
  `plugins/memory_tools.py`.
- Set `requires_confirmation = True` for anything that touches files,
  networks, or other apps.

## Building the exe

```bat
cd atlas
build.bat
```

Produces `dist\ATLAS.exe` (PyInstaller onefile, windowed — no console).
The exe self-heals: run it in an empty folder and it recreates
`settings.json`, `apps.json`, `plugins\` and `skills\`.

### Performance notes (Optimizer)

- **Sub-2 s cold start** — before the window appears we import only stdlib +
  tkinter. `requests`, `edge-tts`, `sounddevice`, `keyboard`, `Pillow`,
  `pygetwindow`, `pydirectinput`, `pystray` all load lazily on first use;
  hotkey wiring, the tray, and the update check run after the HUD is visible.
- **Skills scan** — startup parses frontmatter only (it stops reading each
  SKILL.md at the closing fence), so 50 skills add well under 100 ms and
  ≤ ~50 tokens each to the system prompt. Full bodies load only on demand.
- **Size** — 8 runtime dependencies, no numpy/vendor SDKs, aggressive
  `excludes` in `atlas.spec`, optional UPX. Expect ~25–35 MB, far under the
  100 MB budget.
- **Updater** — on startup a daemon thread compares the running version with
  the latest GitHub release (`update_repo` in settings) and shows a HUD
  notice with the release link. It never self-replaces the exe by design.

## settings.json reference

| Key | Meaning |
|---|---|
| `groq_api_key` | your Groq key (free tier is fine) |
| `provider` / `model` | `groq` + any Groq chat model |
| `hotkey` / `push_to_talk_key` | summon key / PTT key |
| `tts_voice` / `voice_enabled` | edge-tts voice name / master voice switch |
| `allowed_shell_commands` | executables `run_shell` may run |
| `allowed_game_windows` | window titles `game_interact` may touch |
| `discord.webhook_url` or `discord.bot_token` + `default_channel_id` | Discord sending |
| `editor_command` | e.g. `code` — editor for `write_code` (default: OS association) |
| `max_agent_steps` | ReAct step budget (default 8) |
| `update_repo` | `owner/repo` checked for newer releases |

## LLM providers (Gemini-first, auto-fallback)

A.T.L.A.S. tries providers top-to-bottom and falls to the next on a rate-limit
or quota error, showing `PROVIDER → GROQ` in the HUD. Add a free key to any of
them in `settings.json`:

```json
"providers": [
  {"name": "gemini",   "model": "gemini-2.5-flash",        "api_key": "..."},
  {"name": "groq",     "model": "llama-3.3-70b-versatile", "api_key": "..."},
  {"name": "cerebras", "model": "",                        "api_key": "..."}
]
```

- **Gemini** (primary): free key at [aistudio.google.com](https://aistudio.google.com/apikey).
- **Groq**: [console.groq.com](https://console.groq.com).
- **Cerebras**: model left blank → discovered from its live catalog at startup.

Trivial one-shot commands ("open notepad", "mute") are routed to a cheaper
small model automatically; the big model is used only for multi-step reasoning.

## Hands-free voice — "Atlas" / "Hey Atlas"

Say **"Atlas"** (or "Hey Atlas") and A.T.L.A.S. wakes, chimes, listens until you
stop talking, transcribes, and acts — no key press. It's built in: **openWakeWord**
for the wake phrase and **faster-whisper** for transcription, both running
locally on CPU.

- **First run** downloads the voice models into `models/` with a HUD progress
  bar (`INITIALIZING VOICE SYSTEMS… 42%`). After that, **voice is fully
  offline**.
- **Privacy:** audio never leaves your machine. Wake detection and speech
  recognition are 100% local — nothing is streamed to any server.
- Tray → **Mute microphone** actually stops capture (the icon shows an amber
  slash). Push-to-talk (`F8`) and typing always work as fallbacks.
- `settings.json`: `wake_word_enabled`, `wake_sensitivity` (0–1), `wake_phrases`.
- The wake model `atlas.onnx` is trained from synthetic speech — see
  `wake/TRAINING.md`. Until you train it, hands-free falls back to a bundled
  pretrained phrase.

## Updates (verified, one-click, never silent)

On startup (and via tray → **Check for updates**) A.T.L.A.S. checks this repo's
latest GitHub Release. If it's newer you'll see `UPDATE AVAILABLE — vX.Y.Z`.
Click **INSTALL** and it downloads the new `ATLAS.exe`, **verifies its SHA-256**
against the checksum published in the release, then swaps and relaunches via a
small `update.bat` (a running exe can't overwrite itself on Windows). Downgrades
and unverified downloads are refused. Your `plugins/`, `skills/`, `settings.json`,
`memory.db` and `models/` are never touched by an update.

`settings.json`: `auto_check_updates`, `update_channel`, `update_repo`.

## Architecture & review

- `docs/ARCHITECTURE.md` — module diagram, data flow, plugin lifecycle,
  skills progressive disclosure, tkinter-vs-pywebview tradeoff, the
  vector-memory seam.
- `docs/CODE_REVIEW.md` — the adversarial review of `run_shell`,
  `game_interact`, `read_skill_file` path traversal, hostile SKILL.md
  content, the hot-load path, and thread safety.

Known v0.1 limitations: Windows-only; `memory.db` is plaintext (a purge tool
is a fast follow); plugin changes need a restart (skills hot-reload);
brightness control depends on the display supporting WMI.
