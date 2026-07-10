"""EXAMPLE plugin — copy this file to make your own tool in 5 minutes.

HOW PLUGINS WORK
================
1. Any `.py` file dropped into the `plugins/` folder (next to ATLAS.exe) is
   loaded at startup. Files starting with `_` are ignored.
2. Your file must define either:
      - a class named `Plugin`, or
      - a list named `PLUGINS` containing several plugin instances/classes
        (see memory_tools.py for the multi-tool pattern).
3. A.T.L.A.S. turns your `name` / `description` / `parameters` into a function
   schema the LLM can call. The `description` is fed to the model VERBATIM —
   write it like you're explaining the tool to a smart intern.
4. When the model calls your tool, A.T.L.A.S. runs `execute(ctx, **kwargs)` on a
   worker thread (never the UI thread) and returns whatever string you return
   back to the model.
5. If your code raises, A.T.L.A.S. catches it, logs it to atlas.log, and tells
   the model the tool errored — the app never crashes because of a plugin.

WHAT `ctx` GIVES YOU
====================
   ctx.memory   — long-term store: ctx.memory.remember("..."), .recall("...")
   ctx.config   — settings.json: ctx.config.get("some_key")
   ctx.llm      — the model itself: ctx.llm.chat([{"role":"user","content":...}])
                  so your plugin can ask the LLM sub-questions recursively
   ctx.confirm  — ctx.confirm("title", "detail") -> bool, shows a modal
   ctx.notify   — ctx.notify("text") pushes a status line to the HUD
   ctx.app_dir  — pathlib.Path of the folder the exe lives in
"""
import datetime
import random


class Plugin:
    # The tool name the LLM will call. Must be a valid Python identifier.
    name = "example_dice"

    # Fed to the LLM verbatim. Say WHAT it does and WHEN to use it.
    description = ("Roll dice and/or report the current local time. Use when "
                   "the user asks for a dice roll, a random number, or the time.")

    # Standard JSON Schema. The LLM fills these in when calling you.
    parameters = {
        "type": "object",
        "properties": {
            "sides": {
                "type": "integer",
                "description": "Number of sides on the die (default 6).",
            },
            "include_time": {
                "type": "boolean",
                "description": "Also report the current local time.",
            },
        },
        "required": [],
    }

    # True → A.T.L.A.S. shows an ALLOW/DENY modal before running execute().
    # Set this on anything that touches files, networks, or other apps.
    requires_confirmation = False

    def execute(self, ctx, sides: int = 6, include_time: bool = False) -> str:
        # TIP: import heavy libraries INSIDE execute(), not at module top —
        # it keeps A.T.L.A.S.'s cold start fast.
        sides = max(2, min(int(sides), 1000))   # never trust model input blindly
        roll = random.randint(1, sides)
        out = f"Rolled a d{sides}: {roll}"
        if include_time:
            out += f" | Local time: {datetime.datetime.now():%H:%M on %A}"
        # Whatever you return is what the LLM 'sees' as the tool result.
        return out
