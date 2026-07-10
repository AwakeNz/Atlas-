"""discord_message — send a message via the user's own webhook or bot token.
One REST call, not a gateway client. Credentials live only in settings.json;
the LLM never sees or supplies them. Confirmation required: this is an
outward-facing action.
"""


class Plugin:
    name = "discord_message"
    description = ("Send a message to Discord using the user's configured "
                   "webhook or bot. Provide the message content; optionally a "
                   "channel_id when using the bot token (defaults to the "
                   "user's default_channel_id).")
    parameters = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Message text (max 2000 chars)."},
            "channel_id": {"type": "string",
                           "description": "Target channel ID (bot mode only)."},
        },
        "required": ["content"],
    }
    requires_confirmation = True   # it leaves the machine — user sees it first

    def execute(self, ctx, content: str, channel_id: str = "") -> str:
        import requests  # lazy

        content = content.strip()[:2000]
        if not content:
            return "[plugin error] empty message."
        cfg = ctx.config.get("discord", {}) or {}
        webhook = (cfg.get("webhook_url") or "").strip()
        token = (cfg.get("bot_token") or "").strip()

        if webhook:
            r = requests.post(webhook, json={"content": content}, timeout=15)
            if r.status_code in (200, 204):
                return "Message sent via webhook."
            return f"[plugin error] webhook HTTP {r.status_code}: {r.text[:200]}"

        if token:
            channel = (channel_id or cfg.get("default_channel_id") or "").strip()
            if not channel.isdigit():
                return ("[plugin error] no valid channel_id (set discord."
                        "default_channel_id in settings.json).")
            r = requests.post(
                f"https://discord.com/api/v10/channels/{channel}/messages",
                headers={"Authorization": f"Bot {token}"},
                json={"content": content}, timeout=15)
            if r.status_code == 200:
                return f"Message sent to channel {channel}."
            return f"[plugin error] Discord HTTP {r.status_code}: {r.text[:200]}"

        return ("[plugin error] Discord isn't configured. Add discord.webhook_url "
                "or discord.bot_token to settings.json.")
