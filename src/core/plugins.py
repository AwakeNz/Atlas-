"""Plugin hot-loader and registry.

Each plugin is one .py file in <exe dir>/plugins/, loaded at startup under a
namespaced module name. A crashing plugin is logged and skipped at load time,
and caught/reported as a tool error at call time — never fatal.
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Callable

from .paths import data_dir, plugins_dir
from .log import get_logger

log = get_logger("atlas.plugins")

REQUIRED_ATTRS = ("name", "description", "parameters", "execute")


class PluginContext:
    """What a plugin gets to touch. Passed as `ctx` to every execute()."""

    def __init__(self, memory, config, llm, confirm: Callable[[str, str], bool],
                 notify: Callable[[str], None]):
        self.memory = memory          # MemoryStore
        self.config = config          # Config (settings.json)
        self.llm = llm                # LLMProvider — plugins may call the model
        self.confirm = confirm        # (title, detail) -> bool, blocks on modal
        self.notify = notify          # push a line to the HUD
        self.app_dir = data_dir()


class PluginRegistry:
    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._plugins: dict[str, object] = {}
        self._builtins: list[object] = []

    def register_builtin(self, plugin) -> None:
        """Register an app-provided tool (e.g. the skills tools). Builtins
        survive a plugin rescan and can't be shadowed by a plugins/ file of
        the same name (first registration wins)."""
        self._builtins.append(plugin)
        self._register(plugin, "builtin")

    # -- loading ------------------------------------------------------------

    def load_all(self) -> None:
        self._plugins.clear()
        for b in self._builtins:            # builtins first: files can't shadow them
            self._register(b, "builtin")
        plugin_dir = plugins_dir()
        if not plugin_dir.is_dir():
            log.warning("no plugins/ directory at %s", plugin_dir)
            return
        for path in sorted(plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            self._load_file(path)
        log.info("loaded %d tools: %s", len(self._plugins),
                 ", ".join(sorted(self._plugins)))

    def _load_file(self, path: Path) -> None:
        mod_name = f"atlas_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module     # so plugin-internal imports resolve
            spec.loader.exec_module(module)
        except Exception:
            log.error("plugin %s failed to import:\n%s", path.name,
                      traceback.format_exc())
            sys.modules.pop(mod_name, None)
            return
        candidates = []
        if hasattr(module, "PLUGINS"):          # one file may export several tools
            candidates = list(module.PLUGINS)
        elif hasattr(module, "Plugin"):
            candidates = [module.Plugin]
        for cand in candidates:
            self._register(cand() if isinstance(cand, type) else cand, path.name)

    def _register(self, plugin, filename: str) -> None:
        missing = [a for a in REQUIRED_ATTRS if not hasattr(plugin, a)]
        if missing:
            log.error("plugin %s missing %s — skipped", filename, missing)
            return
        name = str(plugin.name)
        if not name.isidentifier():
            log.error("plugin %s has invalid tool name %r — skipped", filename, name)
            return
        if name in self._plugins:
            log.error("duplicate tool name %r (%s) — keeping first", name, filename)
            return
        if not hasattr(plugin, "requires_confirmation"):
            plugin.requires_confirmation = False
        self._plugins[name] = plugin
        log.info("registered %s (%s, confirm=%s)", name, filename,
                 plugin.requires_confirmation)

    # -- LLM-facing ----------------------------------------------------------

    def schemas(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": p.name,
                "description": str(p.description),
                "parameters": p.parameters or {"type": "object", "properties": {}},
            },
        } for p in self._plugins.values()]

    def execute(self, name: str, arguments: dict) -> str:
        plugin = self._plugins.get(name)
        if plugin is None:
            return f"[plugin error] no tool named '{name}'"
        if "__malformed__" in arguments:
            return ("[plugin error] your tool-call arguments were not valid JSON: "
                    f"{arguments['__malformed__']}")
        if plugin.requires_confirmation:
            detail = "\n".join(f"{k} = {v!r}" for k, v in arguments.items()) or "(no arguments)"
            if not self.ctx.confirm(f"Allow tool: {name}?", detail):
                log.info("user DENIED %s(%s)", name, arguments)
                return "[denied] The user declined this action. Do not retry it."
        log.info("EXECUTING %s(%s)", name, arguments)
        try:
            result = plugin.execute(self.ctx, **arguments)
            result = "" if result is None else str(result)
        except TypeError as e:
            # most common LLM failure: wrong/missing kwargs — recoverable
            log.warning("bad arguments for %s: %s", name, e)
            return f"[plugin error] bad arguments for {name}: {e}"
        except Exception:
            log.error("plugin %s crashed:\n%s", name, traceback.format_exc())
            return (f"[plugin error] {name} raised an exception; "
                    "see atlas.log. Try a different approach or report to the user.")
        log.info("RESULT %s -> %s", name, result[:300])
        return result[:8000]  # keep tool output from blowing the context window

    def names(self) -> list[str]:
        return sorted(self._plugins)
