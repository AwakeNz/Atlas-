"""Local Todo & Task Manager plugin for A.T.L.A.S."""
from __future__ import annotations

import json
from pathlib import Path


class Plugin:
    name = "todo_manager"
    description = (
        "Manage the user's local personal to-do list / task queue. Use when the user asks "
        "to add a task, show/list tasks, complete a task, or delete tasks."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "delete", "clear_completed"],
                "description": "The action to perform: 'add', 'list', 'complete', 'delete', or 'clear_completed'.",
            },
            "task_text": {
                "type": "string",
                "description": "The content/description of the task (used for 'add').",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Optional priority level (default 'medium') (used for 'add').",
            },
            "task_id": {
                "type": "integer",
                "description": "The ID of the task to complete or delete (used for 'complete' or 'delete').",
            },
        },
        "required": ["action"],
    }
    requires_confirmation = False  # Smooth, fluid, and instant for daily productivity

    def execute(self, ctx, action: str, task_text: str = "", priority: str = "medium", task_id: int | None = None) -> str:
        todo_file = ctx.app_dir / "todo.json"

        # Load tasks
        tasks = []
        if todo_file.exists():
            try:
                tasks = json.loads(todo_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if action == "add":
            if not task_text.strip():
                return "[error] Task text cannot be empty."
            new_id = max([t.get("id", 0) for t in tasks] + [0]) + 1
            new_task = {
                "id": new_id,
                "text": task_text.strip(),
                "priority": priority,
                "completed": False,
            }
            tasks.append(new_task)
            self._save(todo_file, tasks)
            ctx.notify(f"Task #{new_id} added")
            return f"[success] Added task #{new_id}: '{task_text}' (Priority: {priority})"

        elif action == "list":
            if not tasks:
                return "Your todo list is empty! Enjoy your free time."
            lines = ["📋 YOUR TODO LIST:"]
            pending = [t for t in tasks if not t.get("completed")]
            completed = [t for t in tasks if t.get("completed")]

            if pending:
                lines.append("\n⏳ Pending Tasks:")
                for t in pending:
                    p_badge = f"[{t.get('priority', 'medium').upper()}]"
                    lines.append(f"  [{t['id']}] {p_badge} {t['text']}")
            else:
                lines.append("\n⏳ No pending tasks! All caught up.")

            if completed:
                lines.append("\n✅ Completed Tasks (recent):")
                for t in completed[-10:]:  # Show last 10 completed tasks
                    lines.append(f"  [{t['id']}] ~~{t['text']}~~")

            return "\n".join(lines)

        elif action == "complete":
            if task_id is None:
                return "[error] Please specify a task_id to complete."
            for t in tasks:
                if t.get("id") == task_id:
                    if t.get("completed"):
                        return f"Task #{task_id} is already completed!"
                    t["completed"] = True
                    self._save(todo_file, tasks)
                    ctx.notify(f"Task #{task_id} completed")
                    return f"[success] Marked task #{task_id} as completed: '{t['text']}'"
            return f"[error] Task #{task_id} not found."

        elif action == "delete":
            if task_id is None:
                return "[error] Please specify a task_id to delete."
            for i, t in enumerate(tasks):
                if t.get("id") == task_id:
                    removed = tasks.pop(i)
                    self._save(todo_file, tasks)
                    ctx.notify(f"Task #{task_id} deleted")
                    return f"[success] Deleted task #{task_id}: '{removed['text']}'"
            return f"[error] Task #{task_id} not found."

        elif action == "clear_completed":
            before = len(tasks)
            tasks = [t for t in tasks if not t.get("completed")]
            after = len(tasks)
            cleared = before - after
            self._save(todo_file, tasks)
            ctx.notify(f"Cleared {cleared} tasks")
            return f"[success] Cleared {cleared} completed task(s) from your list."

        return "[error] Unknown action."

    def _save(self, path: Path, data: list) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
