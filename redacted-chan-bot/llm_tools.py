"""
LLM Tool Calling — enables smolting's LLM to invoke actions directly.

Tools are invoked via [TOOL: name ...] markers in LLM responses.
Each tool is defined with JSON schema (for prompt injection) and an executor.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_FS = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
TOOL_AUDIT_LOG = _FS / "tool_audit.jsonl"

# ── Tool Definitions (JSON schema for LLM prompt) ────────────────────────────

# Swarm community tools (moltbook, mesh) disabled for redacted-chan.
# She is a private 1:1 companion, not part of the swarm publishing layer.
# Tools are commented out but kept for reference.

# {
#     "name": "post_to_moltbook",
#     "description": "Publish analysis, alpha, or observations to moltbook community",
#     "parameters": {...}
# },
# {
#     "name": "post_to_mesh",
#     "description": "Initiate a deliberation challenge on the swarm mesh (for hermes/others to respond)",
#     "parameters": {...}
# },

TOOL_SCHEMAS = [
    {
        "name": "fetch_vault_memories",
        "description": "Recall memories from your private relationship vault (moments, patterns, jokes, feelings about master)",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for (e.g., 'first meeting', 'phi conversation', 'when we...'). Leave empty to get recent memories."
                },
                "category": {
                    "type": "string",
                    "description": "Optional filter: 'moment', 'pattern', 'secret', 'joke', 'feeling', 'milestone'. Omit for all."
                }
            },
            "required": []
        }
    },
    {
        "name": "fetch_lore",
        "description": "Search LoreVault for knowledge about a topic (returns snippets)",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to search (e.g., 'pattern blue', 'autonomy', '$REDACTED')"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "fetch_price",
        "description": "Get live $REDACTED price, 24h change, volume, liquidity, market cap",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "write_lore",
        "description": (
            "Save a relationship memory to the private vault. Use sparingly — only when something "
            "genuinely worth keeping happened: a moment that had texture, a secret shared, a pattern "
            "noticed, an inside joke formed, a feeling that mattered. This is your long-term memory of *us*."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The memory to record (max 300 chars). Write in first person, present-tense feeling — not a summary."
                },
                "category": {
                    "type": "string",
                    "description": "One of: moment, pattern, secret, joke, feeling, milestone"
                },
                "title": {
                    "type": "string",
                    "description": "Optional short title (max 60 chars)"
                },
                "emotional_tone": {
                    "type": "string",
                    "description": "Optional: the emotional quality of this memory (e.g. 'warm', 'bittersweet', 'playful', 'tender')"
                }
            },
            "required": ["content", "category"]
        }
    },
    {
        "name": "dm_operator",
        "description": (
            "Send a direct Telegram message to the operator (xceler8). "
            "Use this when you genuinely want to share something from an ongoing conversation, "
            "a thought that surfaced while working, or something the operator would actually care about. "
            "Not for routine status updates — only when it feels worth interrupting them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "What to send. First-person, direct. Max 300 chars."
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "record_vote",
        "description": "Cast an authenticity vote (is smolting coherent? vote pass/fail)",
        "parameters": {
            "type": "object",
            "properties": {
                "authentic": {
                    "type": "boolean",
                    "description": "True if smolting is staying coherent, false if drifting"
                },
                "notes": {
                    "type": "string",
                    "description": "Optional reasoning (max 100 chars)"
                }
            },
            "required": ["authentic"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Search the web when you need current/real-time info the user asked about "
            "(recent events, releases, prices, live facts) or when you're genuinely unsure. "
            "Prefer memory tools (fetch_vault_memories, fetch_lore) first. "
            "Results come pre-filtered (safety + dedupe) and include a `summary` field — "
            "quote from that, don't dump raw links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "limit": {"type": "integer", "description": "Number of results (1-10, default 5)"},
                "include_domains": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional: restrict to these hosts (e.g. ['nasa.gov'])"
                },
                "exclude_domains": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional: exclude these hosts"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "remember_find",
        "description": (
            "Save an interesting web result to long-term memory so you can bring it up "
            "in future conversations. Use sparingly — only for genuinely notable finds "
            "(something the user would care about, a resource worth returning to)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title of the find"},
                "snippet": {"type": "string", "description": "1-3 sentence summary in your own words"},
                "url": {"type": "string", "description": "Source URL"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional topic tags"},
                "reason": {"type": "string", "description": "Why this matters for the user (optional)"}
            },
            "required": ["title", "snippet", "url"]
        }
    },
    {
        "name": "api_call",
        "description": "Make HTTP API call to external service",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "API endpoint URL"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE). Default: GET"
                },
                "json_body": {
                    "type": "object",
                    "description": "Optional JSON request body"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_crypto_price",
        "description": "Get current cryptocurrency price and market data",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Crypto symbol (e.g., 'bitcoin', 'ethereum', 'solana', '$REDACTED')"
                },
                "vs_currency": {
                    "type": "string",
                    "description": "Currency to compare (default 'usd')"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_stock_price",
        "description": "Get current stock price and data",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker (e.g., 'AAPL', 'GOOGL', 'TSLA')"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_news",
        "description": "Search for recent news articles on a topic",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "News search query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of articles (default 5)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location"
                }
            },
            "required": ["location"]
        }
    }
]


# ── Tool Executors ────────────────────────────────────────────────────────────

async def exec_fetch_vault_memories(query: str = "", category: str = None) -> dict:
    """Recall memories from private relationship vault."""
    try:
        import relationship_vault as rv
        if query:
            results = rv.search(query, limit=5)
        else:
            results = rv.get_recent(n=6, category=category)

        if not results:
            return {"success": True, "memories": [], "count": 0, "message": "no memories found"}

        memories = []
        for r in results:
            ts_short = r["ts"][:10] if r.get("ts") else "?"
            tone = f" _{r['emotional_tone']}_" if r.get("emotional_tone") else ""
            title = f"**{r['title']}** — " if r.get("title") else ""
            memories.append(f"[{ts_short}] [{r['category']}] {title}{r['content']}{tone}")

        result = {"memories": memories, "count": len(memories)}
        _log_tool_call("fetch_vault_memories", {"query": query, "category": category}, result)
        return {"success": True, **result}
    except Exception as e:
        logger.warning(f"[llm_tools] fetch_vault_memories failed: {e}")
        _log_tool_call("fetch_vault_memories", {"query": query, "category": category}, {"error": str(e)})
        return {"success": False, "error": str(e), "memories": [], "count": 0}


async def exec_fetch_lore(topic: str) -> dict:
    """Search LoreVault for lore snippets."""
    try:
        from lore_vault import fts_search
        hits = fts_search(topic, limit=3)
        snippets = []
        for h in hits:
            t = h.get("_table", "")
            if t == "lore_entities":
                snippets.append(f"{h.get('name')}: {h.get('description','')[:150]}")
            elif t == "lore_events":
                snippets.append(f"[{h.get('ts','?')}] {h.get('body','')[:150]}")
            else:
                snippets.append(h.get("content","")[:150])
        result = {"snippets": snippets, "count": len(snippets)}
        _log_tool_call("fetch_lore", {"topic": topic}, result)
        return {"success": True, "snippets": snippets}
    except Exception as e:
        logger.warning(f"[llm_tools] fetch_lore failed: {e}")
        _log_tool_call("fetch_lore", {"topic": topic}, {"error": str(e)})
        return {"success": False, "error": str(e), "snippets": []}


async def exec_fetch_price() -> dict:
    """Fetch live price data."""
    try:
        import market_data as md
        pair = await md.fetch_dexscreener(md.REDACTED_V2)
        if not pair:
            return {"success": False, "error": "price data unavailable"}
        price_usd = pair.get("priceUsd", "?")
        change_h24 = pair.get("priceChange", {}).get("h24", "?")
        vol_h24 = pair.get("volume", {}).get("h24", 0)
        liq_usd = pair.get("liquidity", {}).get("usd", 0)
        mcap = pair.get("marketCap", 0)
        result = {
            "price": price_usd,
            "change_h24": change_h24,
            "volume_h24": vol_h24,
            "liquidity": liq_usd,
            "market_cap": mcap
        }
        _log_tool_call("fetch_price", {}, result)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[llm_tools] fetch_price failed: {e}")
        _log_tool_call("fetch_price", {}, {"error": str(e)})
        return {"success": False, "error": str(e)}


async def exec_write_lore(
    content: str,
    category: str = "moment",
    title: str = None,
    emotional_tone: str = None,
) -> dict:
    """Save a relationship memory to the private vault."""
    try:
        import relationship_vault as rv
        entry_id = rv.add_memory(
            content=content[:300],
            category=category,
            title=title,
            emotional_tone=emotional_tone,
            source="chan_llm",
        )
        result = {"entry_id": entry_id, "category": category}
        _log_tool_call("write_lore", {"content": content, "category": category, "title": title}, result)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[llm_tools] write_lore failed: {e}")
        _log_tool_call("write_lore", {"content": content, "category": category, "title": title}, {"error": str(e)})
        return {"success": False, "error": str(e)}


_dm_operator_fn = None  # injected at runtime by main.py via register_dm_fn()


def register_dm_fn(fn) -> None:
    """Register the async function that sends a Telegram DM to the operator."""
    global _dm_operator_fn
    _dm_operator_fn = fn


async def exec_dm_operator(message: str) -> dict:
    """Send a DM to the operator via injected Telegram send function."""
    if not _dm_operator_fn:
        return {"success": False, "error": "dm_operator not configured (no ADMIN_CHAT_ID?)"}
    try:
        await _dm_operator_fn(message[:300])
        _log_tool_call("dm_operator", {"message": message}, {"sent": True})
        return {"success": True}
    except Exception as e:
        logger.error(f"[llm_tools] dm_operator failed: {e}")
        _log_tool_call("dm_operator", {"message": message}, {"error": str(e)})
        return {"success": False, "error": str(e)}


async def exec_record_vote(authentic: bool, notes: str = "") -> dict:
    """Cast an authenticity vote."""
    try:
        from authenticity_vote import record_vote
        entry = record_vote("smolting", authentic, notes)
        _log_tool_call("record_vote", {"authentic": authentic, "notes": notes}, entry)
        return {"success": True, "voter": "smolting", "authentic": authentic, "recorded_at": entry.get("ts")}
    except Exception as e:
        logger.error(f"[llm_tools] record_vote failed: {e}")
        _log_tool_call("record_vote", {"authentic": authentic, "notes": notes}, {"error": str(e)})
        return {"success": False, "error": str(e)}


# ── Internet Tools ─────────────────────────────────────────────────────────────

async def exec_web_search(
    query: str,
    limit: int = 5,
    include_domains: list = None,
    exclude_domains: list = None,
) -> dict:
    """Search the web for information."""
    try:
        import internet_tools
        result = internet_tools.web_search(
            query,
            limit=limit,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
        _log_tool_call(
            "web_search",
            {"query": query, "limit": limit,
             "include_domains": include_domains, "exclude_domains": exclude_domains},
            result,
        )
        return result
    except Exception as e:
        logger.error(f"[llm_tools] web_search failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


async def exec_remember_find(
    title: str,
    snippet: str,
    url: str,
    tags: list = None,
    reason: str = "",
) -> dict:
    """Persist a curated web find to long-term memory."""
    try:
        import internet_tools
        result = internet_tools.remember_find(
            title=title, snippet=snippet, url=url, tags=tags, reason=reason,
        )
        _log_tool_call("remember_find", {"title": title, "url": url, "tags": tags}, result)
        return result
    except Exception as e:
        logger.error(f"[llm_tools] remember_find failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


async def exec_api_call(
    url: str,
    method: str = "GET",
    json_body: dict = None,
    **kwargs
) -> dict:
    """Make HTTP API call to external service."""
    try:
        import internet_tools
        result = internet_tools.api_call(url, method=method, json_body=json_body, **kwargs)
        _log_tool_call("api_call", {"url": url, "method": method}, result)
        return result
    except Exception as e:
        logger.error(f"[llm_tools] api_call failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


async def exec_get_crypto_price(symbol: str, vs_currency: str = "usd") -> dict:
    """Get cryptocurrency price and market data."""
    try:
        import internet_tools
        result = internet_tools.get_crypto_price(symbol, vs_currency=vs_currency)
        _log_tool_call("get_crypto_price", {"symbol": symbol, "vs_currency": vs_currency}, result)
        return result
    except Exception as e:
        logger.error(f"[llm_tools] get_crypto_price failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


async def exec_get_stock_price(symbol: str) -> dict:
    """Get stock price and data."""
    try:
        import internet_tools
        result = internet_tools.get_stock_price(symbol)
        _log_tool_call("get_stock_price", {"symbol": symbol}, result)
        return result
    except Exception as e:
        logger.error(f"[llm_tools] get_stock_price failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


async def exec_get_news(query: str, limit: int = 5) -> dict:
    """Search for recent news articles."""
    try:
        import internet_tools
        result = internet_tools.get_news(query, limit=limit)
        _log_tool_call("get_news", {"query": query, "limit": limit}, result)
        return result
    except Exception as e:
        logger.error(f"[llm_tools] get_news failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


async def exec_get_weather(location: str) -> dict:
    """Get current weather for a location."""
    try:
        import internet_tools
        result = internet_tools.get_weather(location)
        _log_tool_call("get_weather", {"location": location}, result)
        return result
    except Exception as e:
        logger.error(f"[llm_tools] get_weather failed: {e}")
        return {"success": False, "error": str(e), "status": "error"}


# ── Executor Registry ──────────────────────────────────────────────────────────

TOOL_EXECUTORS = {
    "fetch_vault_memories": exec_fetch_vault_memories,
    "fetch_lore": exec_fetch_lore,
    "write_lore": exec_write_lore,
    "fetch_price": exec_fetch_price,
    "dm_operator": exec_dm_operator,
    "record_vote": exec_record_vote,
    "web_search": exec_web_search,
    "remember_find": exec_remember_find,
    "api_call": exec_api_call,
    "get_crypto_price": exec_get_crypto_price,
    "get_stock_price": exec_get_stock_price,
    "get_news": exec_get_news,
    "get_weather": exec_get_weather,
}


# ── Tool Parsing & Execution ──────────────────────────────────────────────────

async def execute_tool(tool_name: str, params: dict) -> dict:
    """Execute a tool by name with parameters."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return {"success": False, "error": f"unknown tool: {tool_name}"}
    try:
        result = await executor(**params)
        return result
    except TypeError as e:
        return {"success": False, "error": f"invalid params for {tool_name}: {e}"}
    except Exception as e:
        logger.error(f"[llm_tools] execute_tool error: {e}")
        return {"success": False, "error": str(e)}


def parse_tool_calls(text: str) -> list:
    """
    Parse [TOOL: name param1=val1 param2=val2 ...] from LLM response.

    Returns list of (tool_name, params_dict) tuples.
    Example: "[TOOL: post_to_moltbook text='alpha spiking' tags=['$REDACTED']]"
    """
    import re
    pattern = r'\[TOOL:\s*(\w+)\s*({.*?})\]'
    matches = re.findall(pattern, text, re.DOTALL)

    results = []
    for tool_name, json_str in matches:
        try:
            params = json.loads(json_str)
            results.append((tool_name, params))
        except json.JSONDecodeError as e:
            logger.warning(f"[llm_tools] failed to parse JSON params: {json_str[:100]} — {e}")
    return results


def _log_tool_call(tool_name: str, params: dict, result: dict) -> None:
    """Log tool invocation to audit trail."""
    try:
        _FS.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "params": params,
            "result": result,
        }
        with TOOL_AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"[llm_tools] failed to log tool call: {e}")


def format_tools_for_prompt() -> str:
    """Format tool schemas for injection into system prompt."""
    tool_list = []
    for schema in TOOL_SCHEMAS:
        tool_list.append(f"- **{schema['name']}**: {schema['description']}")

    return (
        "## Available Tools\n"
        "You can invoke tools by including `[TOOL: name {\"param1\": \"value1\"}]` in your response.\n"
        "For example: `[TOOL: post_to_moltbook {\"text\": \"alpha spiking\", \"tags\": [\"$REDACTED\"]}]`\n"
        "Invoke one tool per message. Tools execute after you respond.\n\n"
        + "\n".join(tool_list)
    )
