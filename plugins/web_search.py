"""Web Search plugin for A.T.L.A.S. utilizing DuckDuckGo's free API."""
from __future__ import annotations

import urllib.parse
import requests


class Plugin:
    name = "web_search"
    description = (
        "Search the live web / internet for real-time information, definitions, news, "
        "or facts. Use when the user asks a question about current events, coding documentation, "
        "or general knowledge that requires searching the web."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (e.g. 'python 3.12 release date' or 'who is the CEO of Apple').",
            }
        },
        "required": ["query"],
    }
    requires_confirmation = False  # Completely safe read-only query

    def execute(self, ctx, query: str) -> str:
        ctx.notify(f"Searching: {query}")
        escaped = urllib.parse.quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={escaped}&format=json&no_html=1&skip_disambig=1"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 202 and resp.status_code != 200:
                return f"[error] Search service returned status {resp.status_code}."

            data = resp.json()
        except Exception as e:
            return f"[error] Failed to complete web search: {e}"

        abstract = data.get("AbstractText") or data.get("Abstract")
        source = data.get("AbstractSource")
        source_url = data.get("AbstractURL")

        results = [f"🌐 Web Search Results for: '{query}'\n"]

        if abstract:
            results.append("📝 Direct Summary:")
            results.append(abstract)
            if source:
                results.append(f"Source: {source} ({source_url})")
            results.append("")

        related = data.get("RelatedTopics", [])
        if related:
            results.append("🔗 Related Topics & Results:")
            count = 0
            for item in related:
                if count >= 5:
                    break
                text = item.get("Text")
                item_url = item.get("FirstURL")
                # DuckDuckGo sometimes has nested topics in 'Topics'
                if not text and "Topics" in item:
                    for sub in item["Topics"]:
                        if count >= 5:
                            break
                        text = sub.get("Text")
                        item_url = sub.get("FirstURL")
                        if text and item_url:
                            results.append(f"- {text}\n  Link: {item_url}")
                            count += 1
                elif text and item_url:
                    results.append(f"- {text}\n  Link: {item_url}")
                    count += 1

        web_link = f"https://duckduckgo.com/?q={escaped}"
        results.append(f"\nFor more results, visit: {web_link}")

        if len(results) <= 1:
            return f"No direct instant answers found for '{query}'. Try simplifying the query or view full results here: {web_link}"

        return "\n".join(results)
