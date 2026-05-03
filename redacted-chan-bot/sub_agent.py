# redacted-chan-bot/sub_agent.py
"""
Sub-Agent — routes factual work to the dedicated sub-agent service.

xAI emits [SUB: task description] when it needs factual work done.
The echo handler catches it, calls sub_agent.run(task), gets back a
structured result, then re-prompts xAI to voice it.

Emotional reroute: if the task touches relationship texture, it's
flagged here (never reaches the service) and defers to xAI.

Architecture:
  Primary:  HTTP POST to swarm-runtime FastAPI service (Railway internal networking)
  Fallback: Inline Groq call if service is unreachable
"""

import os
import re
import logging
import asyncio
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

# ── Service config ────────────────────────────────────────────────────────────

SUB_AGENT_URL   = os.getenv("SUB_AGENT_URL", "")
SUB_AGENT_TOKEN = os.getenv("SUB_AGENT_TOKEN", "")

# Fallback LLM config (used when service is unreachable)
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL    = "openai/gpt-oss-20b"
GROQ_FALLBACK = "llama-3.1-8b-instant"

# ── Emotional reroute detector ─────────────────────────────────────────────────

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
    match = _EMOTIONAL_RE.search(task)
    if match:
        return True, f"emotional texture detected: '{match.group()}'"
    return False, ""


# ── Task type routing (client-side hint) ──────────────────────────────────────

_VAULT_KEYWORDS        = re.compile(r"\b(vault|stored moment|saved moment|lore)\b", re.I)
_MEMORY_KEYWORDS       = re.compile(r"\b(memory|memories|conversation log|history|recall|remember|when did|what did (i|he|we) say|did i mention|did i tell)\b", re.I)
_SENTIMENT_KEYWORDS    = re.compile(r"\b(sentiment|mood|stress|pattern|trend|analysis|emotional state|how.*feeling)\b", re.I)
_DEEP_SENT_KEYWORDS    = re.compile(r"\b(deep sentiment|full analysis|emotional trajectory|baseline)\b", re.I)
_PATTERN_KEYWORDS      = re.compile(r"\b(pattern|recurring|theme|cycle|growth)\b", re.I)
_CONTEXT_KEYWORDS      = re.compile(r"\b(context brief|context packet|session context)\b", re.I)
_URL_KEYWORDS          = re.compile(r"https?://\S+", re.I)
_DEEP_RESEARCH_KEYWORDS = re.compile(
    r"\b(academic|synthesize|synthesis|literature|cite|peer.review|evidence|paper|study|studies|journal|arxiv|pubmed|deep.research)\b",
    re.I,
)


def _route(task: str) -> str:
    if _URL_KEYWORDS.search(task):
        return "summarize_url"
    if _CONTEXT_KEYWORDS.search(task):
        return "context_brief"
    if _DEEP_SENT_KEYWORDS.search(task):
        return "deep_sentiment"
    if _VAULT_KEYWORDS.search(task):
        return "vault_search"
    if _MEMORY_KEYWORDS.search(task):
        return "memory_search"
    if _PATTERN_KEYWORDS.search(task):
        return "pattern_detect"
    if _SENTIMENT_KEYWORDS.search(task):
        return "sentiment"
    if _DEEP_RESEARCH_KEYWORDS.search(task):
        return "deep_research"
    return "research"


# ── Service call ──────────────────────────────────────────────────────────────

async def _call_service(task: str, task_type: str = None) -> str:
    if not SUB_AGENT_URL:
        return await _local_fallback(task)

    import aiohttp
    try:
        payload = {"task": task, "task_type": task_type}
        headers = {
            "Authorization": f"Bearer {SUB_AGENT_TOKEN}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SUB_AGENT_URL}/task",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise ValueError(f"service error {resp.status}: {data}")
                return data.get("result", "")
    except Exception as e:
        logger.warning(f"[sub_agent] service call failed: {e}, falling back to local")
        return await _local_fallback(task)


# ── Local fallback (inline Groq) ─────────────────────────────────────────────

async def _local_fallback(task: str) -> str:
    if not GROQ_API_KEY:
        return f"Sub-agent unavailable (no service URL, no API key)"

    import aiohttp
    system = (
        "You are a research assistant. Answer the following factual question or "
        "complete the research task concisely. Return structured output where "
        "appropriate. No emotional commentary."
    )
    payload_base = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Task: {task}"},
        ],
        "temperature": 0.3,
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
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
            logger.warning(f"[sub_agent] fallback {model} failed: {e}")

    return "Sub-agent could not complete task (all providers failed)"


# ── Main entry point ───────────────────────────────────────────────────────────

async def run(task: str) -> dict:
    """
    Run the sub-agent on a task string.

    Returns:
        {
          "result":           str,
          "task_type":        str,
          "emotional_flag":   bool,
          "emotional_reason": str,
        }
    """
    task = task.strip()
    logger.info(f"[sub_agent] task: {task[:80]}")

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
        result = await _call_service(task, task_type)
    except Exception as e:
        logger.warning(f"[sub_agent] task failed: {e}")
        result = f"Sub-agent could not complete task: {e}"

    return {
        "result":           result,
        "task_type":        task_type,
        "emotional_flag":   False,
        "emotional_reason": "",
    }
