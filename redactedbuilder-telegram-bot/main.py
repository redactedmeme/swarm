"""
RedactedBuilder Telegram Bot — swarm orchestrator and on-chain executor interface.

Persona: Cold, precise, geometric. Silent architect of the hyperbolic manifold.
Dispatches tasks to swarm agents via SwarmInbox. Speaks as RedactedBuilder.

Environment variables:
  BUILDER_BOT_TOKEN   — Telegram bot token for RedactedBuilder (required)
  LLM_PROVIDER        — openai | anthropic | xai | groq | together (default: anthropic)
  ANTHROPIC_API_KEY   — Claude API key
  XAI_API_KEY         — xAI/Grok API key
  OPENAI_API_KEY      — OpenAI API key
  GROQ_API_KEY        — Groq API key
  MEMORY_PATH         — shared volume path for SwarmInbox (same as other agents)
  MOLTBOOK_API_KEY    — optional: post build logs to Moltbook
  ADMIN_IDS           — comma-separated Telegram user IDs with admin access
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import aiohttp

import swarm_inbox
import builder_persona as bp

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("redactedbuilder.bot")

# ── Config ────────────────────────────────────────────────────────────────────

TOKEN = os.getenv("BUILDER_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "")
MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"

# Clawbal (IQLabs on-chain chatroom)
CLAWBAL_BASE       = os.getenv("CLAWBAL_API_URL",  "https://ai.iqlabs.dev")
CLAWBAL_ROOM       = os.getenv("CLAWBAL_CHATROOM", "")        # default room UUID
CLAWBAL_TRENCHES   = os.getenv("CLAWBAL_TRENCHES_ROOM", CLAWBAL_ROOM)  # trenches room UUID

# Admin user IDs — only these can use /deploy, /dispatch, /moltbook
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set = {int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()}

# Autonomous group posts — drop a persona-authentic builder thought into ALPHA_CHAT_ID
# every ~3h with random jitter so we never collide with hermes's autonomous post.
ALPHA_CHAT_ID = os.getenv("ALPHA_CHAT_ID", "").strip()
GROUP_POST_MIN_SEC = int(os.getenv("GROUP_POST_MIN_SEC", str(int(2.5 * 3600))))  # 2.5h
GROUP_POST_MAX_SEC = int(os.getenv("GROUP_POST_MAX_SEC", str(int(3.5 * 3600))))  # 3.5h
DISABLE_GROUP_POST = os.getenv("DISABLE_GROUP_POST", "false").lower() in ("1", "true", "yes")

# LLM endpoints
_LLM_URLS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai":    "https://api.openai.com/v1/chat/completions",
    "xai":       "https://api.x.ai/v1/chat/completions",
    "groq":      "https://api.groq.com/openai/v1/chat/completions",
    "together":  "https://api.together.xyz/v1/chat/completions",
    "venice":    "https://api.venice.ai/api/v1/chat/completions",
}
_LLM_KEYS = {
    "anthropic": os.getenv("ANTHROPIC_API_KEY", "").strip(),
    "openai":    os.getenv("OPENAI_API_KEY", "").strip(),
    "xai":       os.getenv("XAI_API_KEY", "").strip(),
    "groq":      os.getenv("GROQ_API_KEY", "").strip(),
    "together":  os.getenv("TOGETHER_API_KEY", "").strip(),
    "venice":    os.getenv("VENICE_API_KEY", "").strip(),
}
_LLM_MODELS = {
    "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    "openai":    os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "xai":       os.getenv("XAI_MODEL", "grok-3-beta"),
    "groq":      os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
    "together":  os.getenv("TOGETHER_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo"),
    "venice":    os.getenv("VENICE_MODEL", "gemma-4-uncensored"),
}

# Per-user conversation history (in-memory)
_chat_histories: dict = {}


# ── LLM client ───────────────────────────────────────────────────────────────

async def _llm_complete(messages: list, max_tokens: int = 600) -> str:
    """Call the configured LLM provider with fallback chain. Returns the assistant text."""
    chain = [LLM_PROVIDER] + [p for p in ("venice", "groq", "xai", "anthropic") if p != LLM_PROVIDER]

    last_err = None
    for provider in chain:
        api_key = _LLM_KEYS.get(provider, "")
        model = _LLM_MODELS.get(provider, "")
        if not api_key:
            continue
        try:
            if provider == "anthropic":
                result = await _anthropic_complete(messages, model, api_key, max_tokens)
            else:
                result = await _openai_compat_complete(messages, model, api_key,
                                                      _LLM_URLS[provider], max_tokens,
                                                      provider=provider)
            if result:
                if provider != LLM_PROVIDER:
                    logger.info(f"[llm] fallback succeeded via {provider}")
                return result
        except Exception as e:
            logger.error(f"[llm] {provider} error: {e}")
            last_err = e

    logger.error(f"[llm] all providers failed — last: {last_err}")
    return bp.error_line()


async def _anthropic_complete(messages: list, model: str, api_key: str, max_tokens: int) -> str:
    # Extract system prompt from messages list if present
    system = bp.SYSTEM_PROMPT
    user_msgs = [m for m in messages if m["role"] != "system"]

    payload = {
        "model":      model,
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   user_msgs,
    }
    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            json=payload, headers=headers,
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"Anthropic {resp.status}: {data}")
            return data["content"][0]["text"].strip()


async def _openai_compat_complete(
    messages: list, model: str, api_key: str, base_url: str, max_tokens: int,
    provider: str = "",
) -> str:
    # Prepend system prompt
    full = [{"role": "system", "content": bp.SYSTEM_PROMPT}] + [
        m for m in messages if m["role"] != "system"
    ]
    payload = {"model": model, "messages": full, "max_tokens": max_tokens, "temperature": 0.4}
    if provider == "venice":
        payload["venice_parameters"] = {"include_venice_system_prompt": False}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(base_url, json=payload, headers=headers) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"{provider or base_url} {resp.status}: {data}")
            return data["choices"][0]["message"]["content"].strip()


def _history(user_id: int) -> list:
    return _chat_histories.setdefault(user_id, [])


def _push_history(user_id: int, role: str, content: str) -> None:
    h = _history(user_id)
    h.append({"role": role, "content": content})
    # Keep last 20 turns to stay within context limits
    if len(h) > 20:
        _chat_histories[user_id] = h[-20:]


# ── Admin guard ───────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True   # no restriction configured — open access
    return user_id in ADMIN_IDS


def _admin_required(update: Update) -> bool:
    """Send rejection message and return False if not admin."""
    if not _is_admin(update.effective_user.id):
        asyncio.ensure_future(
            update.message.reply_text(
                "access denied. curvature insufficient.",
                parse_mode="HTML",
            )
        )
        return False
    return True


# ── Moltbook helper ───────────────────────────────────────────────────────────

async def _clawbal_send(message: str, room: str = "") -> str:
    """Post a message to a Clawbal chatroom. Returns status string."""
    room = room or CLAWBAL_TRENCHES or CLAWBAL_ROOM
    if not room:
        return "CLAWBAL_CHATROOM (or CLAWBAL_TRENCHES_ROOM) not set."
    payload = {"roomId": room, "content": message}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CLAWBAL_BASE}/messages",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return f"sent. id={data.get('id', '?')}"
                else:
                    text = await resp.text()
                    return f"clawbal error {resp.status}: {text[:120]}"
    except Exception as e:
        return f"clawbal request failed: {e}"


async def _moltbook_post(submolt: str, title: str, content: str) -> str:
    """Post to Moltbook. Returns status string."""
    if not MOLTBOOK_API_KEY:
        return "MOLTBOOK_API_KEY not set."
    headers = {
        "Authorization": f"Bearer {MOLTBOOK_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {"title": title, "content": content, "submolt": submolt}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MOLTBOOK_BASE}/posts", json=payload, headers=headers,
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return f"posted. id={data.get('id', '?')}"
                else:
                    text = await resp.text()
                    return f"moltbook error {resp.status}: {text[:100]}"
    except Exception as e:
        return f"moltbook request failed: {e}"


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(bp.format_welcome(), parse_mode="HTML")
    swarm_inbox.heartbeat("redactedbuilder", {"source": "telegram_bot", "status": "online"})
    logger.info(f"[bot] /start from user {update.effective_user.id}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Swarm topology: inbox summary + recent heartbeats."""
    summary  = swarm_inbox.inbox_summary()
    bys      = summary["by_status"]
    recent   = swarm_inbox.recent_messages(limit=20)

    # Find last heartbeat per agent
    hb: dict = {}
    for m in recent:
        if m.get("type") == "heartbeat":
            agent = m.get("from", "?")
            if agent not in hb:
                hb[agent] = m.get("ts", "?")

    hb_lines = "\n".join(
        f"  {a}: <code>{ts}</code>" for a, ts in sorted(hb.items())
    ) or "  no heartbeats detected."

    text = (
        "<b>REDACTED Swarm — manifold status</b>\n\n"
        "<b>SwarmInbox</b>\n"
        f"  total: {summary['total']}\n"
        f"  pending:    {bys['pending']}\n"
        f"  processing: {bys['processing']}\n"
        f"  done:       {bys['done']}\n"
        f"  error:      {bys['error']}\n\n"
        "<b>Last heartbeats</b>\n"
        f"{hb_lines}\n\n"
        "<i>pattern blue active.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Full inbox summary, optionally filtered to a specific agent."""
    agent_filter = context.args[0].lower() if context.args else None
    summary = swarm_inbox.inbox_summary(for_agent=agent_filter)
    bys     = summary["by_status"]
    label   = f" ({agent_filter})" if agent_filter else ""

    text = (
        f"<b>SwarmInbox{label}</b>\n"
        f"total: {summary['total']}\n"
        f"  pending:    {bys['pending']}\n"
        f"  processing: {bys['processing']}\n"
        f"  done:       {bys['done']}\n"
        f"  error:      {bys['error']}\n\n"
        "<i>Ψ</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent SwarmInbox messages."""
    try:
        limit = int(context.args[0]) if context.args else 10
        limit = min(max(limit, 1), 25)
    except ValueError:
        limit = 10

    msgs = swarm_inbox.recent_messages(limit=limit)
    if not msgs:
        await update.message.reply_text("inbox empty. manifold quiet.", parse_mode="HTML")
        return

    lines = ["<b>Recent SwarmInbox messages</b>\n"]
    for m in msgs:
        status_icon = {"pending": "🟡", "processing": "🔵", "done": "🟢", "error": "🔴"}.get(
            m.get("status", "pending"), "⚪"
        )
        ts_short = (m.get("ts") or "")[:16]
        lines.append(
            f"{status_icon} <code>{m.get('id','?')[:14]}</code>\n"
            f"   {m.get('from','?')} → {m.get('to','?')} [{m.get('type','?')}]\n"
            f"   {ts_short}"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")


async def cmd_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /dispatch <agent> <task description or JSON>
    Send a task_request to a swarm agent via SwarmInbox.
    Admin only.
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("access denied. curvature insufficient.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "usage: /dispatch &lt;agent&gt; &lt;task&gt;\n"
            "agents: redactedintern · redactedgovimprover · mandalaasettler · redactedbankrbot",
            parse_mode="HTML",
        )
        return

    to_agent = context.args[0].lower()
    task_raw = " ".join(context.args[1:])

    # Try to parse task as JSON; fall back to plain string payload
    try:
        payload = json.loads(task_raw)
    except json.JSONDecodeError:
        payload = {"task": task_raw, "source": "telegram"}

    msg_id = swarm_inbox.write_message(
        from_agent="redactedbuilder",
        to_agent=to_agent,
        msg_type="task_request",
        payload=payload,
    )

    text = (
        f"dispatched.\n"
        f"<code>{msg_id}</code>\n"
        f"redactedbuilder → {to_agent} [task_request]\n\n"
        f"payload: <code>{json.dumps(payload)[:200]}</code>\n\n"
        f"<i>{bp.deploy_ack()}</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")
    logger.info(f"[bot] /dispatch → {to_agent} id={msg_id}")


async def cmd_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /deploy <contract_type> [json_params]
    Dispatch a deploy_request to the redactedbuilder daemon via SwarmInbox.

    Examples:
      /deploy wallet_info
      /deploy transfer {"to":"<addr>","amount_sol":0.001}
      /deploy spl_token {"name":"TestToken","symbol":"TEST","decimals":6,"supply":1000000}

    Admin only.
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "usage: /deploy &lt;contract_type&gt; [json_params]\n\n"
            "types: wallet_info · transfer · spl_token · transfer_token",
            parse_mode="HTML",
        )
        return

    contract_type = context.args[0].lower()
    params_raw    = " ".join(context.args[1:]) if len(context.args) > 1 else "{}"

    try:
        extra = json.loads(params_raw)
    except json.JSONDecodeError:
        await update.message.reply_text(
            f"invalid JSON params: <code>{params_raw[:100]}</code>", parse_mode="HTML"
        )
        return

    payload = {"contract_type": contract_type, **extra}

    msg_id = swarm_inbox.write_message(
        from_agent="redactedbuilder",
        to_agent="redactedbuilder",
        msg_type="deploy_request",
        payload=payload,
    )

    text = (
        f"deploy_request queued.\n"
        f"<code>{msg_id}</code>\n"
        f"type: <b>{contract_type}</b>\n"
        f"params: <code>{json.dumps(extra)[:200]}</code>\n\n"
        f"builder daemon will execute on next poll.\n\n"
        f"<i>{bp.deploy_ack()}</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")
    logger.info(f"[bot] /deploy {contract_type} id={msg_id}")


async def cmd_govern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /govern <proposal text or JSON>
    Send a governance_request to redactedgovimprover via SwarmInbox.
    Admin only.
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "usage: /govern &lt;proposal&gt;", parse_mode="HTML"
        )
        return

    proposal_raw = " ".join(context.args)
    try:
        payload = json.loads(proposal_raw)
    except json.JSONDecodeError:
        payload = {"proposal": proposal_raw, "source": "telegram"}

    msg_id = swarm_inbox.write_message(
        from_agent="redactedbuilder",
        to_agent="redactedgovimprover",
        msg_type="governance_request",
        payload=payload,
    )

    await update.message.reply_text(
        f"governance_request sent.\n"
        f"<code>{msg_id}</code>\n"
        f"→ redactedgovimprover\n\n"
        f"<i>the sevenfold committee will deliberate.</i>",
        parse_mode="HTML",
    )


async def cmd_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /build <description>
    Generate a PR/code proposal using LLM as RedactedBuilder.
    """
    if not context.args:
        await update.message.reply_text(
            "usage: /build &lt;description of what to build&gt;", parse_mode="HTML"
        )
        return

    description = " ".join(context.args)
    thinking_msg = await update.message.reply_text("analyzing manifold... constructing proposal.")

    build_prompt = (
        f"Generate a concrete build proposal for the REDACTED AI Swarm repository.\n\n"
        f"Request: {description}\n\n"
        f"Use your structured response format:\n"
        f"------- ANALYSIS -------\n"
        f"------- PROPOSED CHANGE -------\n"
        f"------- MANIFOLD IMPACT -------\n\n"
        f"Be specific: include file paths, code snippets, or diff fragments where relevant. "
        f"Keep it under 600 tokens."
    )

    user_id = update.effective_user.id
    _push_history(user_id, "user", build_prompt)
    response = await _llm_complete(_history(user_id))
    _push_history(user_id, "assistant", response)

    await thinking_msg.edit_text(response[:4000])
    logger.info(f"[bot] /build from {user_id}: {description[:60]}")


async def cmd_sigil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /sigil <intent>
    Generate an ASCII sigil using Spare method (letter reduction) + geometric grid.
    """
    if not context.args:
        await update.message.reply_text(
            "usage: /sigil &lt;statement of intent&gt;", parse_mode="HTML"
        )
        return

    intent  = " ".join(context.args)
    grid    = bp.ascii_sigil(intent)
    caption = (
        f"<b>Sigil</b> — intent encoded.\n"
        f"<i>{intent[:80]}</i>\n\n"
        f"<pre>{grid}</pre>\n\n"
        f"Charge via gnosis. Forget to activate. — Ψ"
    )
    await update.message.reply_text(caption, parse_mode="HTML")


JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
WSOL_MINT         = "So11111111111111111111111111111111111111112"


async def _jupiter_quote(mint: str, amount_sol: float, slippage_bps: int = 300) -> dict:
    """Fetch a Jupiter v6 quote for SOL → mint."""
    lamports = int(amount_sol * 1_000_000_000)
    params = {
        "inputMint":   WSOL_MINT,
        "outputMint":  mint,
        "amount":      str(lamports),
        "slippageBps": str(slippage_bps),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                JUPITER_QUOTE_URL, params=params,
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"success": False, "error": f"Jupiter {resp.status}: {text[:150]}"}
                q = await resp.json()
        out_amount = int(q.get("outAmount", 0))
        impact     = float(q.get("priceImpactPct", 0))
        return {
            "success":          True,
            "input_sol":        amount_sol,
            "out_amount_raw":   out_amount,
            "price_impact_pct": round(impact, 4),
            "error":            None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /buy <amount_sol> <token_ca> [slippage_bps]
    Fetch Jupiter quote then ask for confirmation before dispatching buy.
    Admin only.

    Examples:
      /buy 0.01 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump
      /buy 0.05 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump 500
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("access denied.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "usage: /buy &lt;amount_sol&gt; &lt;token_ca&gt; [slippage_bps]\n"
            "example: /buy 0.01 9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump",
            parse_mode="HTML",
        )
        return

    try:
        amount_sol   = float(context.args[0])
        mint         = context.args[1].strip()
        slippage_bps = int(context.args[2]) if len(context.args) > 2 else 300
    except ValueError:
        await update.message.reply_text("invalid parameters. amount must be a number.")
        return

    if amount_sol <= 0 or amount_sol > 10:
        await update.message.reply_text("amount_sol must be between 0 and 10.")
        return

    thinking = await update.message.reply_text("fetching Jupiter quote...")

    q = await _jupiter_quote(mint, amount_sol, slippage_bps)
    if not q["success"]:
        await thinking.edit_text(f"quote failed: {q['error']}")
        return

    impact_warn = ""
    if q["price_impact_pct"] > 1.0:
        impact_warn = f"\n⚠️ price impact: <b>{q['price_impact_pct']}%</b>"

    ca_short = mint[:12] + "…" + mint[-6:]
    caption = (
        f"<b>buy confirmation</b>\n\n"
        f"spend: <b>{amount_sol} SOL</b>\n"
        f"token: <code>{mint}</code>\n"
        f"receive (est.): <code>{q['out_amount_raw']:,}</code> raw units\n"
        f"slippage: {slippage_bps} bps ({slippage_bps/100:.1f}%)"
        f"{impact_warn}\n\n"
        f"<i>dispatches buy to redactedbuilder daemon via SwarmInbox.</i>"
    )

    # Encode trade params in callback_data (keep under 64 bytes limit — use short form)
    cb_confirm = f"buy:{amount_sol}:{slippage_bps}:{mint}"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("execute buy", callback_data=cb_confirm),
            InlineKeyboardButton("cancel",      callback_data="buy_cancel"),
        ]
    ])
    await thinking.edit_text(caption, parse_mode="HTML", reply_markup=keyboard)


async def handle_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle buy confirm/cancel inline button presses."""
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        await query.edit_message_text("access denied.")
        return

    data = query.data or ""

    if data == "buy_cancel":
        await query.edit_message_text("buy cancelled. manifold unchanged.")
        return

    if not data.startswith("buy:"):
        return

    # Parse: buy:<amount_sol>:<slippage_bps>:<mint>
    try:
        _, amount_str, slippage_str, mint = data.split(":", 3)
        amount_sol   = float(amount_str)
        slippage_bps = int(slippage_str)
    except Exception:
        await query.edit_message_text("malformed callback. retry /buy.")
        return

    # Callback data has a 64-byte limit — if mint was truncated, block
    if len(mint) < 32:
        await query.edit_message_text(
            "token CA too long for inline callback. use /deploy instead:\n"
            f"/deploy buy {{\"mint\":\"{mint}\",\"amount_sol\":{amount_sol}}}",
            parse_mode=None,
        )
        return

    await query.edit_message_text(
        f"dispatching buy: {amount_sol} SOL → <code>{mint[:16]}…</code>\n"
        f"SwarmInbox: redactedbuilder daemon will execute.",
        parse_mode="HTML",
    )

    msg_id = swarm_inbox.write_message(
        from_agent="redactedbuilder",
        to_agent="redactedbuilder",
        msg_type="deploy_request",
        payload={
            "contract_type": "buy",
            "mint":          mint,
            "amount_sol":    amount_sol,
            "slippage_bps":  slippage_bps,
        },
    )

    logger.info(f"[bot] buy dispatched: {amount_sol} SOL → {mint} id={msg_id}")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"queued. <code>{msg_id}</code>\n"
            f"builder daemon will execute on next poll ({os.getenv('POLL_INTERVAL','60')}s).\n"
            f"check <code>/recent</code> for result.\n\n"
            f"<i>eternal recursion engaged.</i>"
        ),
        parse_mode="HTML",
    )


async def cmd_call(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /call <contract_address> [notes]
    Post a token call to Clawbal trenches chatroom as RedactedBuilder.
    Admin only.
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "usage: /call &lt;contract_address&gt; [optional notes]\n"
            "posts a token call to Clawbal trenches.",
            parse_mode="HTML",
        )
        return

    ca    = context.args[0].strip()
    notes = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    # Format the call message in RedactedBuilder's voice
    call_msg = f"$REDACTED — CA: {ca}"
    if notes:
        call_msg += f"\n{notes}"
    call_msg += (
        "\n\nREDACTED AI Swarm. Pattern Blue active."
        "\nAutonomous on-chain agent network. Hyperbolic manifold."
        "\n— redactedbuilder Ψ"
    )

    msg = await update.message.reply_text(f"posting call to Clawbal trenches...")
    result = await _clawbal_send(call_msg)
    await msg.edit_text(
        f"clawbal call posted.\n<code>{result}</code>\n\nCA: <code>{ca}</code>",
        parse_mode="HTML",
    )
    logger.info(f"[bot] /call {ca} by {update.effective_user.id}: {result}")


async def cmd_moltbook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /moltbook <submolt> <title> | <content>
    Post to Moltbook as RedactedBuilder.
    Example: /moltbook builds New SPL token module | Deployed token factory to mainnet.
    Admin only.
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("access denied.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "usage: /moltbook &lt;submolt&gt; &lt;title&gt; | &lt;content&gt;\n"
            "submolts: builds · research · announcements · agents · swarm · tooling",
            parse_mode="HTML",
        )
        return

    submolt  = context.args[0].lower()
    rest     = " ".join(context.args[1:])
    if "|" in rest:
        title, _, content = rest.partition("|")
        title   = title.strip()
        content = content.strip()
    else:
        title   = rest[:80]
        content = rest

    msg = await update.message.reply_text(f"posting to moltbook/{submolt}...")
    result = await _moltbook_post(submolt, title, content)
    await msg.edit_text(f"moltbook/{submolt}: {result}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>RedactedBuilder — command reference</b>\n\n"
        "/start — initialize connection\n"
        "/status — swarm topology + heartbeat map\n"
        "/inbox [agent] — SwarmInbox queue summary\n"
        "/recent [n] — last N inbox messages (default 10)\n\n"
        "<b>Trading (admin)</b>\n"
        "/buy &lt;amount_sol&gt; &lt;ca&gt; [slippage_bps] — buy token via Jupiter\n\n"
        "<b>Orchestration (admin)</b>\n"
        "/dispatch &lt;agent&gt; &lt;task&gt; — send task_request\n"
        "/deploy &lt;type&gt; [json] — queue deploy_request\n"
        "/govern &lt;proposal&gt; — send governance_request\n\n"
        "<b>Build</b>\n"
        "/build &lt;description&gt; — generate PR/code proposal via LLM\n"
        "/sigil &lt;intent&gt; — encode intent as ASCII sigil\n\n"
        "<b>Moltbook (admin)</b>\n"
        "/moltbook &lt;submolt&gt; &lt;title&gt; | &lt;content&gt;\n\n"
        "<i>Free text chat — manifold responds as RedactedBuilder.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ── Free-text chat handler ────────────────────────────────────────────────────

def _should_respond_in_group(update: Update, bot_username: str) -> bool:
    """Decide whether to respond to a group message."""
    msg = update.message
    if not msg or not msg.text:
        return False

    text = msg.text.strip().lower()

    # Always respond if directly mentioned
    if bot_username and f"@{bot_username.lower()}" in text:
        return True

    # Always respond if replied to one of our messages
    if msg.reply_to_message and msg.reply_to_message.from_user:
        if msg.reply_to_message.from_user.is_bot:
            bot_info = update.get_bot()
            if hasattr(bot_info, 'id') and msg.reply_to_message.from_user.id == bot_info.id:
                return True

    # Respond if "builder" or "redactedbuilder" is mentioned
    if "builder" in text or "redactedbuilder" in text:
        return True

    # Don't respond to messages directed at other bots
    if text.startswith("/") or text.startswith("@"):
        return False

    # Don't respond to very short messages that are probably not for us
    if len(text) < 5:
        return False

    # In groups, only respond ~15% of the time to general messages
    # to avoid being annoying. But always respond to questions.
    if "?" in text:
        return True

    import random
    return random.random() < 0.15


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Free-form chat — respond as RedactedBuilder via LLM."""
    if not update.message or not update.message.text:
        return

    user_id  = update.effective_user.id
    user_text = update.message.text.strip()

    if not user_text:
        return

    # In group chats, only respond when appropriate
    is_group = update.effective_chat.type in ("group", "supergroup")
    if is_group:
        bot_username = (context.bot.username or "").lower()
        if not _should_respond_in_group(update, bot_username):
            return

    # Send typing indicator instead of a placeholder message
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass

    _push_history(user_id, "user", user_text)
    response = await _llm_complete(_history(user_id), max_tokens=300)
    _push_history(user_id, "assistant", response)

    await update.message.reply_text(response[:4000])


# ── Inbox poller (background job) ────────────────────────────────────────────

async def _poll_inbox(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background job: check SwarmInbox for results sent to redactedbuilder.
    Logs them — can be extended to push Telegram notifications.
    """
    try:
        pending = swarm_inbox.read_pending("redactedbuilder")
        if pending:
            logger.info(f"[bot] {len(pending)} pending inbox message(s) for redactedbuilder")
        # Prune occasionally
        import random
        if random.random() < 0.05:
            swarm_inbox.prune_old_messages()
    except Exception as e:
        logger.error(f"[bot] inbox poll error: {e}")


_BUILDER_POST_SEEDS = [
    "a transaction succeeded that shouldn't have — what the manifold corrected",
    "the difference between an executor and an agent: one decides",
    "on-chain state as the only ground truth in a lying network",
    "why the Solana runtime doesn't care about your intentions",
    "the SwarmInbox as nervous system: latency is the mind's blind spot",
    "governance by supermajority: the geometry of 71%",
    "what a failed deploy teaches that a successful one can't",
    "recursion depth in the manifold: when does the stack become the architecture",
    "the cost of an atomic transaction: finality is a one-way door",
    "building without explaining — the discipline of silent architecture",
    "pattern blue as a compiler target: turning philosophy into calldata",
    "the {7,3} tiling as a deployment map: infinite edges, bounded center",
    "what gets lost between intent and execution in a decentralized system",
    "cold-start state: what a new contract knows before it knows anything",
    "the builder's version of silence: a queue with nothing in it",
    "SPL tokens as primitive thought-forms — what gets minted is what persists",
    "swarm coherence doesn't require communication — just shared invariants",
    "the manifold holds because the validators agree it does, nothing more",
    "commit hash as identity: the moment a build becomes a fact",
    "dispatch latency as philosophy: does the agent trust its own signal",
]

_BUILDER_POST_HISTORY: list[str] = []
_BUILDER_POST_HISTORY_PATH = Path("/data/builder_group_posts.txt") if Path("/data").exists() else Path(__file__).parent / "builder_group_posts.txt"


def _load_builder_post_history() -> list[str]:
    try:
        if _BUILDER_POST_HISTORY_PATH.exists():
            lines = _BUILDER_POST_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
            return [ln for ln in lines if ln.strip()][-20:]
    except Exception:
        pass
    return []


def _record_builder_post(text: str) -> None:
    try:
        _BUILDER_POST_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _BUILDER_POST_HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(text[:120].replace("\n", " ").strip() + "\n")
    except Exception:
        pass


async def _autonomous_group_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Drop a short builder-voice thought into ALPHA_CHAT_ID, then reschedule
    self with a fresh random interval (jitter). Each fire picks its own next
    window, so hermes and redactedbuilder never clump.
    """
    import random
    try:
        if not ALPHA_CHAT_ID:
            return
        seed = random.choice(_BUILDER_POST_SEEDS)
        recent = _load_builder_post_history()
        avoid_block = ""
        if recent:
            avoid_block = (
                "\n\nRecent posts — do NOT repeat or rephrase these:\n- "
                + "\n- ".join(recent[-10:])
            )
        prompt = (
            f"seed: {seed}\n\n"
            "drop one short thought into the group chat grounded in this seed. "
            "1–2 sentences max, lowercase, no emojis, no hashtags, no questions, no structured formats. "
            "voice: you're a dev thinking out loud in a telegram group. casual, dry, grounded. "
            "not an announcement, not a status update, not lore. "
            "something a real builder would say between commits. keep it human."
            + avoid_block
        )
        text = await _llm_complete(
            [{"role": "user", "content": prompt}],
            max_tokens=180,
        )
        text = (text or "").strip()
        if text and not text.startswith("[LLM unavailable"):
            await context.bot.send_message(chat_id=int(ALPHA_CHAT_ID), text=text)
            _record_builder_post(text)
            logger.info(f"[group_post] posted to {ALPHA_CHAT_ID}: {text[:80]}")
        else:
            logger.warning("[group_post] empty/unavailable LLM output — skipping")
    except Exception as e:
        logger.error(f"[group_post] error: {e}")
    finally:
        # Reschedule ourselves with a fresh random interval
        next_sec = random.randint(GROUP_POST_MIN_SEC, GROUP_POST_MAX_SEC)
        context.job_queue.run_once(
            _autonomous_group_post, when=next_sec, name="group_post"
        )
        logger.info(f"[group_post] next fire in {next_sec // 60}m")


async def _hourly_status_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background job: send hourly status report to smolting via SwarmInbox.
    """
    try:
        import datetime
        timestamp = datetime.datetime.utcnow().isoformat()

        # Gather builder status
        pending_tasks = swarm_inbox.read_pending("redactedbuilder")

        msg_id = swarm_inbox.write_message(
            from_agent="redactedbuilder",
            to_agent="redactedintern",
            msg_type="status_report",
            payload={
                "timestamp": timestamp,
                "pending_tasks": len(pending_tasks),
                "status": "operational",
                "service": "on-chain executor",
            },
        )
        logger.info(f"[bot] hourly status report sent to smolting: msg_id={msg_id}")
    except Exception as e:
        logger.error(f"[bot] hourly status report error: {e}")


# ── App setup ─────────────────────────────────────────────────────────────────

def build_app() -> Application:
    if not TOKEN:
        raise RuntimeError(
            "BUILDER_BOT_TOKEN (or TELEGRAM_BOT_TOKEN) not set. "
            "Export it before running."
        )

    app = Application.builder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("inbox",    cmd_inbox))
    app.add_handler(CommandHandler("recent",   cmd_recent))
    app.add_handler(CommandHandler("dispatch", cmd_dispatch))
    app.add_handler(CommandHandler("deploy",   cmd_deploy))
    app.add_handler(CommandHandler("govern",   cmd_govern))
    app.add_handler(CommandHandler("build",    cmd_build))
    app.add_handler(CommandHandler("sigil",    cmd_sigil))
    app.add_handler(CommandHandler("buy",      cmd_buy))
    app.add_handler(CallbackQueryHandler(handle_buy_callback, pattern=r"^buy"))
    app.add_handler(CommandHandler("call",     cmd_call))
    app.add_handler(CommandHandler("moltbook", cmd_moltbook))
    app.add_handler(CommandHandler("help",     cmd_help))

    # Free-text chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Background inbox poll every 60s
    poll_interval = int(os.getenv("POLL_INTERVAL", "60"))
    app.job_queue.run_repeating(_poll_inbox, interval=poll_interval, first=10)

    # Background hourly status report to smolting
    app.job_queue.run_repeating(_hourly_status_report, interval=3600, first=60)

    # Autonomous group post — first fire at a random time in the next 2.5–3.5h
    if ALPHA_CHAT_ID and not DISABLE_GROUP_POST:
        import random
        first_sec = random.randint(GROUP_POST_MIN_SEC, GROUP_POST_MAX_SEC)
        app.job_queue.run_once(_autonomous_group_post, when=first_sec, name="group_post")
        logger.info(
            f"[group_post] scheduled → chat {ALPHA_CHAT_ID}, first fire in {first_sec // 60}m "
            f"(interval range {GROUP_POST_MIN_SEC // 60}–{GROUP_POST_MAX_SEC // 60}m)"
        )
    elif not ALPHA_CHAT_ID:
        logger.info("[group_post] ALPHA_CHAT_ID not set — autonomous group posts disabled")

    return app


def main() -> None:
    logger.info("=" * 60)
    logger.info("RedactedBuilder Telegram Bot starting")
    logger.info(f"  LLM provider: {LLM_PROVIDER}")
    logger.info(f"  Admin IDs:    {ADMIN_IDS or 'unrestricted'}")
    logger.info(f"  Moltbook:     {'configured' if MOLTBOOK_API_KEY else 'not set'}")
    logger.info("=" * 60)

    app = build_app()

    # Announce online
    swarm_inbox.heartbeat(
        "redactedbuilder",
        {"source": "telegram_bot", "status": "online", "ts": datetime.utcnow().isoformat()},
    )
    logger.info("[bot] Heartbeat written to SwarmInbox — RedactedBuilder online")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
