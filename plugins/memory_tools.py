"""remember / recall — the LLM's hands on long-term memory.

Demonstrates the multi-tool pattern: one file exporting a PLUGINS list.
"""


class RememberPlugin:
    name = "remember"
    description = ("Store a durable fact about the user or their environment "
                   "in long-term memory, e.g. 'User's work hours are 9-17 CET' or "
                   "'User prefers dark mode'. Use for things worth knowing in "
                   "future sessions, not transient chat.")
    parameters = {
        "type": "object",
        "properties": {
            "fact": {"type": "string",
                     "description": "One self-contained sentence to remember."},
        },
        "required": ["fact"],
    }
    requires_confirmation = False

    def execute(self, ctx, fact: str) -> str:
        fact = fact.strip()
        if len(fact) < 3:
            return "[plugin error] fact too short to be useful."
        ctx.memory.remember(fact, source="agent")
        return f"Remembered: {fact}"


class RecallPlugin:
    name = "recall"
    description = ("Search long-term memory for stored facts. Use when the "
                   "user references something they may have told you before, "
                   "or before asking them a question they might already have "
                   "answered.")
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keywords to search for."},
        },
        "required": ["query"],
    }
    requires_confirmation = False

    def execute(self, ctx, query: str) -> str:
        hits = ctx.memory.recall(query, limit=6)
        if not hits:
            return f"No stored facts matching '{query}'."
        return "Recalled facts:\n" + "\n".join(f"- {h}" for h in hits)


PLUGINS = [RememberPlugin, RecallPlugin]
