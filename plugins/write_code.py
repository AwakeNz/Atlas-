"""write_code — saves LLM-generated code into a sandboxed temp project dir,
opens it in the user's editor, and can optionally run it (Python only, with a
confirmation modal, cwd pinned inside the sandbox dir).
"""
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_SAFE_NAME = re.compile(r"^[\w][\w.\-]{0,80}$")


class Plugin:
    name = "write_code"
    description = ("Save a code file the model has written into a scratch "
                   "workspace and open it in the user's editor. Set run=true "
                   "to also execute it (Python files only; the user must "
                   "approve). Returns the file path and, if run, the output.")
    parameters = {
        "type": "object",
        "properties": {
            "filename": {"type": "string",
                         "description": "Plain filename with extension, e.g. 'scraper.py'."},
            "code": {"type": "string", "description": "Full file contents."},
            "run": {"type": "boolean",
                    "description": "Execute after saving (python files only)."},
        },
        "required": ["filename", "code"],
    }
    requires_confirmation = False   # writing to the sandbox is safe; RUNNING confirms

    def execute(self, ctx, filename: str, code: str, run: bool = False) -> str:
        filename = filename.strip()
        if not _SAFE_NAME.match(filename) or ".." in filename:
            return "[plugin error] unsafe filename; use e.g. 'script.py'."

        workspace = Path(tempfile.gettempdir()) / "atlas_code" / time.strftime("%Y%m%d_%H%M%S")
        workspace.mkdir(parents=True, exist_ok=True)
        path = workspace / filename
        path.write_text(code, encoding="utf-8")

        editor = (ctx.config.get("editor_command") or "").strip()
        try:
            if editor:
                subprocess.Popen([editor, str(path)], shell=False)
            elif sys.platform == "win32":
                import os
                os.startfile(path)  # default association
        except Exception as e:
            ctx.notify(f"Couldn't open editor: {e}")

        result = f"Saved to {path} and opened in the editor."
        if run:
            if not filename.endswith(".py"):
                return result + " (run skipped: only .py files can be executed)"
            if not ctx.confirm("Run generated code?",
                               f"python {filename}\nin sandbox {workspace}\n\n"
                               f"--- first lines ---\n" +
                               "\n".join(code.splitlines()[:12])):
                return result + " (user declined to run it)"
            try:
                r = subprocess.run([sys.executable, str(path)], shell=False,
                                   capture_output=True, text=True, timeout=60,
                                   cwd=workspace, errors="replace")
                out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
                result += f"\nRan it: exit {r.returncode}\n{out.strip()[:3000]}"
            except subprocess.TimeoutExpired:
                result += "\nRun timed out after 60s."
        return result
