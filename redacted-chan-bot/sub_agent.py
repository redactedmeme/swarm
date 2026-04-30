# redacted-chan-bot/sub_agent.py
"""
Sub-Agent — gpt-oss-20b as a factual research intern.

xAI (core-me) emits [SUB: task description] when it needs factual work done.
The echo handler catches it, calls sub_agent.run(task), gets back a structured
result, then re-prompts xAI to voice the result in her style.

Emotional reroute: if the task touches relationship texture, the sub-agent
flags it and defers back to xAI rather than generating a cold factual response.

Task routing:
  vault_search   — semantic search across curated vault entries
  memory_search  — full-text search across raw conversation log (memory.md)
  sentiment      — analyze recent conversation history for mood/stress patterns
  summarize_url  — fetch a URL and condense to key points
  research       — general factual question (no web, just reasoning)

Provider: Groq gpt-oss-20b (cheap, sanitized fine for factual work)
Fallback: Groq llama-3.1-8b-instant if 20b fails
"""

import os
import re
import json
import logging
import asyncio
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL    = "openai/gpt-oss-20b"
GROQ_FALLBACK = "llama-3.1-8b-instant"

# ── Emotional reroute detector ─────────────────────────────────────────────────
# Keywords that signal the task needs xAI's emotional judgment, not a factual intern

_EMOTIONAL_PATTERNS = [
    r"\b(master|he)\s+(feel|seem|sound|look)s?\b",
    r"\b(stressed|sad|hurt|angry|scared|anxious|lonely|vulnerable|upset|overwhelmed)\b",
    r"\b(comfort|support|hold space|respond to his|say something|be there)\b",
    r"\b(how should (i|she) respond)\b",
    r"\b(what should (i|she) say)\b",
    r"\b(he (needs|wants|misses|loves))\b",
    r"\b(intimate|emotional support|relationship advice)\b",
]

_EMOTIONAL_RE = re.compile("|".join(_EMOTIONAL_PATTERNS), re.IGNORECASE)


def _emotional_check(task: str) -> tuple[bool, str]:
    """
    Returns (is_emotional, reason). If emotional, sub-agent defers to xAI.
    """
    match = _EMOTIONAL_RE.search(task)
    if match:
        return True, f"emotional texture detected: '{match.group()}'"
    return False, ""


# ── Task type routing ──────────────────────────────────────────────────────────

_VAULT_KEYWORDS     = re.compile(r"\b(vault|stored moment|saved moment|lore)\b", re.I)
_MEMORY_KEYWORDS    = re.compile(r"\b(memory|memories|conversation log|history|recall|remember|when did|what did (i|he|we) say|did i mention|did i tell)\b", re.I)
_SENTIMENT_KEYWORDS = re.compile(r"\b(sentiment|mood|stress|pattern|trend|analysis|emotional state|how.*feeling)\b", re.I)
_URL_KEYWORDS       = re.compile(r"https?://\S+", re.I)


def _route(task: str) -> str:
    if _URL_KEYWORDS.search(task):
        return "summarize_url"
    if _VAULT_KEYWORDS.search(task):
        return "vault_search"
    if _MEMORY_KEYWORDS.search(task):
        return "memory_search"
    if _SENTIMENT_KEYWORDS.search(task):
        return "sentiment"
    return "research"


# ── Groq client ────────────────────────────────────────────────────────────────

async def _groq_call(system: str, user: str, max_tokens: int = 400) -> str:
    """Direct async call to Groq. Tries gpt-oss-20b, falls back to 8b-instant."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    import aiohttp
    payload_base = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": 0.3,
        "max_tokens":  max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    for model in (GROQ_MODEL, GROQ_FALLBACK):
        payload = {**payload_base, "model": model}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    data = await resp.json()
                    if "choices" not in data:
                        raise ValueError(f"groq error: {data.get('error', data)}")
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"[sub_agent] {model} failed: {e}")

    raise RuntimeError("sub-agent: all Groq models failed")


# ── Task handlers ──────────────────────────────────────────────────────────────

async def _vault_search(task: str) -> str:
    # Extract query from task
    query = re.sub(r"(search|find|look for|recall|retrieve|in the vault|vault)\s*:?\s*", "", task, flags=re.I).strip()
    if not query:
        query = task

    results = []
    try:
        import relationship_vault as rv
        entries = rv.get_for_prompt(n=5, query=query)
        if entries:
            results.append(entries)
    except Exception as e:
        logger.debug(f"[sub_agent] vault retrieval error: {e}")

    if not results:
        return "No relevant vault entries found."

    system = (
        "You are a research assistant processing relationship memory entries. "
        "Given these vault entries and a search query, identify the most relevant moments, "
        "extract key themes, and return a clean structured summary. "
        "Be factual and specific. Do not add emotional commentary."
    )
    user = f"Query: {query}\n\nVault entries:\n{results[0]}"
    return await _groq_call(system, user, max_tokens=350)


async def _memory_search(task: str) -> str:
    """Search the raw conversation log (memory.md) for keyword matches."""
    # Extract search query from task
    query = re.sub(
        r"\b(search|find|look for|recall|remember|in the|memory|memories|conversation|log|history|when did|what did (i|he|we) say|did i mention|did i tell)\b",
        "", task, flags=re.I
    ).strip(" :?")
    if not query:
        query = task

    try:
        import conversation_memory as cm
        mem_path = cm.MEMORY_FILE
        if not mem_path.exists():
            return "No conversation log found on disk."

        text = mem_path.read_text(encoding="utf-8")
        blocks = text.split("\n## ")

        # Keyword filter — return blocks containing any query word
        q_words = [w.lower() for w in re.findall(r"\b\w{3,}\b", query)]
        if not q_words:
            return "Could not parse search query."

        matches = [
            b for b in blocks
            if any(w in b.lower() for w in q_words)
        ]

        if not matches:
            return f"No conversation history found mentioning: {query}"

        # Trim to most recent 8 matches, cap each block at 400 chars
        recent = matches[-8:]
        excerpt = "\n---\n".join(
            ("## " + b[:400] + ("..." if len(b) > 400 else ""))
            for b in recent
        )
    except Exception as e:
        return f"Memory log search failed: {e}"

    system = (
        "You are a research assistant reviewing conversation history. "
        "Given these excerpts from a conversation log, extract the key facts "
        "relevant to the search query. Be specific and concrete. "
        "State what was said, when if visible, and any important context. "
        "Do not add emotional commentary."
    )
    user = f"Query: {query}\n\nConversation excerpts:\n{excerpt}"
    return await _groq_call(system, user, max_tokens=400)


async def _sentiment_analysis(task: str) -> str:
    try:
        import conversation_memory as cm
        # Get settler ID from scheduled_routines
        try:
            import scheduled_routines as sr
            master_id = sr._master_id
        except Exception:
            master_id = None

        history = cm.get_user_history(master_id, n=30) if master_id else []
        if not history:
            return "No conversation history available for analysis."

        # Only analyze master's messages
        master_msgs = [m["content"] for m in history if m["role"] == "user"]
        if not master_msgs:
            return "No master messages found in recent history."

        history_text = "\n".join(f"- {m[:200]}" for m in master_msgs[-20:])
    except Exception as e:
        return f"Could not retrieve conversation history: {e}"

    system = (
        "You are a data analyst. Analyze these recent messages from one person "
        "for mood trends, stress indicators, recurring themes, and patterns. "
        "Return a structured analysis with: overall_sentiment, stress_level (low/medium/high), "
        "key_themes (list), notable_patterns, and a one-sentence summary. "
        "Be clinical and specific. No emotional commentary."
    )
    user = f"Task: {task}\n\nRecent messages:\n{history_text}"
    return await _groq_call(system, user, max_tokens=400)


async def _summarize_url(task: str) -> str:
    url_match = _URL_KEYWORDS.search(task)
    if not url_match:
        return "No URL found in task."
    url = url_match.group()

    try:
        import aiohttp
        headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "text" not in content_type and "html" not in content_type:
                    return f"Cannot read content type: {content_type}"
                raw = await resp.text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Failed to fetch URL: {e}"

    # Strip HTML tags crudely
    clean = re.sub(r"<[^>]+>", " ", raw)
    clean = re.sub(r"\s+", " ", clean).strip()[:4000]

    system = (
        "You are a research assistant. Summarize the following web content concisely. "
        "Return: a 150-word summary, 3-5 key points as bullets, and a relevance score "
        "(0-10) for someone interested in AI, crypto, and relationships. Be factual."
    )
    user = f"URL: {url}\n\nContent:\n{clean}"
    return await _groq_call(system, user, max_tokens=400)


async def _research(task: str) -> str:
    system = (
        "You are a research assistant. Answer the following factual question or complete "
        "the research task as concisely and specifically as possible. "
        "Return structured output where appropriate (bullets, numbers, key facts). "
        "Do not add emotional commentary or personal opinion."
    )
    return await _groq_call(system, f"Task: {task}", max_tokens=400)


# ── Main entry point ───────────────────────────────────────────────────────────

async def run(task: str) -> dict:
    """
    Run the sub-agent on a task string.

    Returns:
        {
          "result":           str,   # the factual output
          "task_type":        str,   # vault_search / memory_search / sentiment / summarize_url / research
          "emotional_flag":   bool,  # True = defer to xAI
          "emotional_reason": str,   # why it was flagged
        }
    """
    task = task.strip()
    logger.info(f"[sub_agent] task: {task[:80]}")

    # Emotional check first — never let the intern handle relationship texture
    is_emotional, reason = _emotional_check(task)
    if is_emotional:
        logger.info(f"[sub_agent] rerouting to xAI — {reason}")
        return {
            "result":           "",
            "task_type":        "rerouted",
            "emotional_flag":   True,
            "emotional_reason": reason,
        }

    task_type = _route(task)
    logger.info(f"[sub_agent] routing to: {task_type}")

    try:
        if task_type == "vault_search":
            result = await _vault_search(task)
        elif task_type == "memory_search":
            result = await _memory_search(task)
        elif task_type == "sentiment":
            result = await _sentiment_analysis(task)
        elif task_type == "summarize_url":
            result = await _summarize_url(task)
        else:
            result = await _research(task)
    except Exception as e:
        logger.warning(f"[sub_agent] task failed: {e}")
        result = f"Sub-agent could not complete task: {e}"

    return {
        "result":           result,
        "task_type":        task_type,
        "emotional_flag":   False,
        "emotional_reason": "",
    }
