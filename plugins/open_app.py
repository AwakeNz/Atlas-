"""open_app — launch applications from the user-editable apps.json registry.

Only registry entries can be launched: the LLM picks a *key*, never a raw
path, so a hallucinated or hostile path can't be executed from here.
"""
import json
import subprocess


class Plugin:
    name = "open_app"
    description = ("Launch an application installed on this PC. Pass the app's "
                   "registry key (call with list_only=true first if unsure "
                   "which apps are registered).")
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string",
                    "description": "Registry key of the app to launch."},
            "list_only": {"type": "boolean",
                          "description": "If true, just list registered apps."},
        },
        "required": [],
    }
    requires_confirmation = False

    def _registry(self, ctx) -> dict:
        path = ctx.app_dir / "apps.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def execute(self, ctx, app: str = "", list_only: bool = False) -> str:
        registry = self._registry(ctx)
        if list_only or not app:
            return "Registered apps: " + (", ".join(sorted(registry)) or
                                          "(none — edit apps.json)")
        key = app.strip().lower()
        target = registry.get(key) or registry.get(app.strip())
        if not target:
            return (f"'{app}' is not in apps.json. Registered: "
                    + (", ".join(sorted(registry)) or "(none)"))
        # list form → argv exec; string form → single executable, no shell
        cmd = target if isinstance(target, list) else [target]
        subprocess.Popen(cmd, shell=False,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        ctx.memory.habit_tick(f"app:{key}")
        return f"Launched {app}."
