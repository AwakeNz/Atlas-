---
# ─────────────────────────────────────────────────────────────────────
# EXAMPLE SKILL — copy this folder to write your own in 5 minutes.
#
# A skill teaches A.T.L.A.S. a WORKFLOW — no code, just markdown.
# Rules:
#   - The folder must contain this file, named exactly SKILL.md.
#   - Frontmatter sits between the two '---' fences: simple `key: value`
#     lines. Lines starting with '#' (like these) are ignored.
#   - `name`: lowercase letters, digits, - and _ only. This is what the
#     model passes to use_skill().
#   - `description`: ONE sentence saying what the skill does and WHEN to
#     use it. This line is always in the model's context, so keep it
#     short — the body below is only loaded when the skill is used.
# ─────────────────────────────────────────────────────────────────────
name: example-email-tone
description: How to draft and rewrite emails in the user's preferred tone. Use whenever the user asks to write, reply to, or soften an email.
---

# Email tone workflow

When drafting or rewriting an email for the user, follow these steps:

1. **Identify the audience** — colleague, manager, stranger, support desk.
   If it isn't obvious from the request, ask one short question.
2. **Default tone** — warm but direct. Short sentences. No corporate filler
   ("I hope this email finds you well" is banned).
3. **Structure** — one-line purpose up top, details in the middle,
   a single clear ask at the end. Never more than three paragraphs
   unless the user asks for detail.
4. **Match register to audience** — see the examples in the support file
   `tone-examples.md` (load it with read_skill_file if you need concrete
   before/after samples).
5. **Close** — sign off with the user's stored sign-off if one exists in
   memory (try recall("email sign-off") first); otherwise "Best, <name>".

Never send anything anywhere: output the draft in the HUD and let the user
copy it. If the user explicitly asks to send it via a tool (e.g. Discord),
that action still requires its normal confirmation.
