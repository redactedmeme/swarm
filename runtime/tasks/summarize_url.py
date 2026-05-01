"""URL summarization — fetch and condense web content."""

import re
import aiohttp
import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    url_match = re.search(r"https?://\S+", task)
    if not url_match:
        return "No URL found in task.", "", []

    url = url_match.group()

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "text" not in content_type and "html" not in content_type:
                    return f"Cannot read content type: {content_type}", "", []
                raw = await resp.text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Failed to fetch URL: {e}", "", []

    clean = re.sub(r"<[^>]+>", " ", raw)
    clean = re.sub(r"\s+", " ", clean).strip()[:4000]

    # Seed with user interests from facts
    facts = await dc.get_facts(limit=10)
    interests = ""
    if facts:
        interests = "User interests: " + "; ".join(f.get("fact", "")[:60] for f in facts[:5])

    system = (
        "You are a research assistant. Summarize the following web content concisely. "
        "Return: a 150-word summary, 3-5 key points as bullets, and a relevance score "
        "(0-10) for the user. Be factual."
    )
    user = f"URL: {url}\n{interests}\n\nContent:\n{clean}"

    result, model = await llm.call(system, user, max_tokens=400)
    return result, model, ["url"] + (["facts"] if facts else [])
