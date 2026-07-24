"""Plugin to dynamically install/teach A.T.L.A.S. new skills."""
from __future__ import annotations

import re


class Plugin:
    name = "install_skill"
    description = (
        "Install or teach A.T.L.A.S. a new skill (workflow, procedural guideline, "
        "or style guide) by writing its SKILL.md. Use when the user specifically "
        "asks to install, teach, configure, or save a new skill."
    )
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Short name of the skill using lowercase letters, digits, hyphen, or underscore (e.g., 'meeting-notes').",
            },
            "description": {
                "type": "string",
                "description": "One sentence describing the skill and when to use it.",
            },
            "instructions": {
                "type": "string",
                "description": "The full body markdown instructions of the skill. Keep under 24,000 characters.",
            },
        },
        "required": ["skill_name", "description", "instructions"],
    }
    requires_confirmation = True

    def execute(self, ctx, skill_name: str, description: str, instructions: str) -> str:
        skill_name = skill_name.strip().lower()
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", skill_name):
            return "[error] Invalid skill name. Use lowercase letters, digits, hyphens, and underscores only."

        skills_folder = ctx.app_dir / "skills"
        skill_dir = skills_folder / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md_path = skill_dir / "SKILL.md"

        # Assemble YAML frontmatter + instructions
        content = (
            "---\n"
            f"name: {skill_name}\n"
            f"description: {description}\n"
            "---\n"
            f"{instructions}\n"
        )

        try:
            skill_md_path.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"[error] Failed to write skill file: {e}"

        ctx.notify(f"Skill '{skill_name}' installed")
        return (
            f"[success] Installed skill '{skill_name}' successfully into skills folder.\n"
            "To use it immediately, you MUST run 'manage_skills(action=\"reload\")' "
            "so the skills index hot-reloads it without requiring an app restart."
        )
