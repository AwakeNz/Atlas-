"""run_shell — the most dangerous tool in the box, so it is the most locked
down. Defense in depth, in order:

1. requires_confirmation=True — the user sees the EXACT argv in a modal.
2. Whitelist: the executable (argv[0], basename, extension stripped) must be
   in settings.json → allowed_shell_commands. Default list is read-only-ish
   diagnostics only.
3. `shlex.split` + `shell=False` — the model's text is parsed into argv and
   NEVER handed to cmd.exe/a shell, so `&&`, `|`, `>` etc. are inert argument
   text, not operators. We additionally reject them outright to avoid
   confusing argv-level surprises.
4. 30-second timeout, output truncated.
"""
import shlex
import subprocess

_FORBIDDEN_CHARS = set("&|;<>`^%\n\r")


class Plugin:
    name = "run_shell"
    description = ("Run a whitelisted console command and return its output. "
                   "Only commands whose executable is in the user's "
                   "allowed_shell_commands setting will run; the user must "
                   "also approve each invocation in a dialog. No pipes, "
                   "redirection, or chaining.")
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string",
                        "description": "The command line, e.g. 'ping -n 2 example.com'."},
        },
        "required": ["command"],
    }
    requires_confirmation = True   # modal shows the exact command

    def execute(self, ctx, command: str) -> str:
        command = command.strip()
        if not command:
            return "[plugin error] empty command."
        bad = _FORBIDDEN_CHARS.intersection(command)
        if bad:
            return (f"[denied] command contains forbidden characters {sorted(bad)}. "
                    "Chaining, piping and redirection are not allowed.")
        try:
            argv = shlex.split(command, posix=False)
        except ValueError as e:
            return f"[plugin error] could not parse command: {e}"
        if not argv:
            return "[plugin error] empty command."

        exe = argv[0].strip('"').replace("\\", "/").rsplit("/", 1)[-1].lower()
        exe = exe.removesuffix(".exe").removesuffix(".com").removesuffix(".bat")
        allowed = [c.lower() for c in ctx.config.get("allowed_shell_commands", [])]
        if exe not in allowed:
            return (f"[denied] '{exe}' is not whitelisted. The user can add it to "
                    f"allowed_shell_commands in settings.json. Currently allowed: "
                    f"{', '.join(allowed) or '(none)'}")
        if exe in ("cmd", "powershell", "pwsh", "wt", "start"):
            return "[denied] shell interpreters cannot be whitelisted through run_shell."

        try:
            r = subprocess.run(argv, shell=False, capture_output=True, text=True,
                               timeout=30, errors="replace")
        except FileNotFoundError:
            return f"[plugin error] executable not found: {argv[0]}"
        except subprocess.TimeoutExpired:
            return "[plugin error] command timed out after 30s."
        out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
        return f"exit code {r.returncode}\n{out.strip()[:4000] or '(no output)'}"
