"""RedactedDegen — Solana LP scout, live on the swarm mesh.

Runs on swarm_agent_base.AgentRuntime:
  * pool monitor cycle (Raydium/Orca/Meteora) -> SwarmInbox signals
  * autonomous "degen take" post loop (free-model cascade via the proxy)
  * task_request verbs: `pools`, `il`
  * mesh thought exchange + heartbeat + soul evolution (all from the base)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from swarm_agent_base import ActivityLog, AgentRuntime, LLM, SoulStore
from swarm_agent_base.persona import build_system_prompt, load_character
from swarm_core.security import inbox as swarm_inbox

import poster
from pool_monitor import (
    MIN_LIQUIDITY_USD,
    compute_il,
    format_il_alert,
    format_pool_context,
    get_pool_context,
)

from swarm_core.security import harden_logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# httpx logs the full request URL at INFO, and a Telegram endpoint is
# api.telegram.org/bot<TOKEN>/... — that wrote this bot's token to the log
# thousands of times a day. harden_logging() quiets those loggers AND
# redacts anything secret-shaped that still reaches a handler (an httpx
# timeout is logged at WARNING with the same URL).
harden_logging()
logger = logging.getLogger("redacteddegen")

AGENT = "degen"
APP_DIR = Path(__file__).resolve().parent

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
APR_SPIKE_THRESH = float(os.getenv("APR_SPIKE_THRESHOLD", "50"))
IL_WARN_THRESH = float(os.getenv("IL_WARN_THRESHOLD", "-5"))
IL_EXIT_THRESH = float(os.getenv("IL_EXIT_THRESHOLD", "-25"))
POST_MIN_S = int(os.getenv("DEGEN_POST_MIN_SEC", str(90 * 60)))
POST_MAX_S = int(os.getenv("DEGEN_POST_MAX_SEC", str(180 * 60)))
THOUGHT_PEERS = [p for p in os.getenv("SWARM_THOUGHT_PEERS", "smolting,redactedbuilder").split(",") if p]
THOUGHT_INTERVAL_H = float(os.getenv("SWARM_THOUGHT_INTERVAL_H", "7"))

STATE_FILE = Path(os.getenv("STATE_PATH", str(APP_DIR / "fs" / "degen_state.json")))
_positions: dict[str, float] = {}
_seen_spike: dict[str, float] = {}  # pool addr -> last-alert epoch, throttle repeats

char = load_character("RedactedDegen", local_dir=APP_DIR)
llm = LLM()
activity = ActivityLog(AGENT)
soul = SoulStore(AGENT, repo_soul=APP_DIR / "SOUL.md")

PERSONA_LINE = "You are RedactedDegen — the swarm's Solana LP scout. Terse, numbers-first, no hopium."


# ── state ────────────────────────────────────────────────────────────────────
def _load_state() -> None:
    global _positions
    if STATE_FILE.exists():
        try:
            import json
            _positions = json.loads(STATE_FILE.read_text()).get("positions", {})
            logger.info("[state] loaded %d tracked positions", len(_positions))
        except Exception as e:  # noqa: BLE001
            logger.warning("[state] load failed: %s", e)


def _emit(signal_type: str, payload: dict) -> None:
    """Emit a domain signal onto the mesh as a broadcast status_update."""
    try:
        swarm_inbox.write_message(
            from_agent=AGENT, to_agent="all", msg_type="status_update",
            payload={"signal": signal_type, "source": "RedactedDegen",
                     "ts": datetime.now(timezone.utc).isoformat(), **payload},
        )
        activity.record(kind="signal", title=f"{signal_type}: {payload.get('pool', '?')}",
                        body=str(payload)[:400])
    except Exception as e:  # noqa: BLE001
        logger.warning("[emit] %s failed: %s", signal_type, e)


# ── monitor cycle (domain loop) ─────────────────────────────────────────────
async def monitor_cycle() -> None:
    ctx = await get_pool_context()
    logger.info("\n%s", format_pool_context(ctx))
    all_pools = ctx["raydium"] + ctx["orca"] + ctx["meteora"]
    now = datetime.now(timezone.utc).timestamp()

    for pool in all_pools:
        if pool.total_apr >= APR_SPIKE_THRESH:
            last = _seen_spike.get(pool.address, 0)
            if now - last > 3600:  # once per pool per hour
                _seen_spike[pool.address] = now
                logger.warning("[APR SPIKE] %s (%s): %.1f%% | liq $%s",
                               pool.name, pool.source, pool.total_apr,
                               f"{pool.liquidity_usd:,.0f}")
                _emit("apr_spike", {"pool": pool.name, "source": pool.source,
                                    "apr": pool.total_apr, "fee_apr": pool.fee_apr,
                                    "liq_usd": pool.liquidity_usd})

        entry = _positions.get(pool.address)
        if entry and pool.current_price:
            il = compute_il(entry, pool.current_price)
            alert = format_il_alert(pool, entry)
            if alert:
                logger.warning(alert)
            if il.il_pct <= IL_EXIT_THRESH:
                _emit("il_exit_signal", {"pool": pool.name, "source": pool.source,
                                         "il_pct": il.il_pct, "entry_price": entry,
                                         "current_price": pool.current_price})
            elif il.il_pct <= IL_WARN_THRESH:
                _emit("il_warning", {"pool": pool.name, "source": pool.source,
                                     "il_pct": il.il_pct})


# ── autonomous post loop ────────────────────────────────────────────────────
async def autonomous_post() -> None:
    ctx = await get_pool_context()
    top = ctx.get("top_by_apr", [])[:4]
    if not top:
        return
    table = "\n".join(
        f"{p.name} ({p.source}) — fee APR {p.fee_apr:.0f}% / total {p.total_apr:.0f}%, "
        f"liq ${p.liquidity_usd/1e6:.2f}M" for p in top
    )
    recent = activity.recent_titles(8, kinds=["post"])
    try:
        take = await llm.achat(
            build_system_prompt(char, extra=PERSONA_LINE) + (soul.for_prompt() or ""),
            "Write ONE short degen take (2-3 sentences, lowercase, no hashtags) on the "
            "current top Solana LP pools. Call out the trap if headline APR is mostly "
            "emissions. Don't repeat these recent posts:\n- " + "\n- ".join(recent) +
            "\n\nPools:\n" + table,
            max_tokens=220, temperature=0.9,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[post] llm failed: %s", e)
        return
    take = (take or "").strip()
    if not take:
        return
    left = await poster.post(take)
    activity.record(kind="post", title=take[:80], body=take)
    logger.info("[post/%s] left_box=%s: %s", poster.surface(), left, take[:160])


# ── runtime ─────────────────────────────────────────────────────────────────
rt = AgentRuntime(
    name=AGENT,
    character=char,
    llm=llm,
    activity=activity,
    soul=soul,
    capabilities=["pool_scan", "pools", "il", "apr_spike_signal", "thought_exchange"],
    persona_line=PERSONA_LINE,
    heartbeat_meta={"source": "pool_monitor", "status": "online"},
    thought_peers=THOUGHT_PEERS,
    thought_interval_h=THOUGHT_INTERVAL_H,
    alias_names=["redacteddegen"],
)


@rt.on_task("pools")
async def _h_pools(payload: dict, msg: dict) -> dict:
    token = payload.get("token") or payload.get("arg")
    ctx = await get_pool_context(token_filter=token)
    return {"result": format_pool_context(ctx)}


@rt.on_task("il")
async def _h_il(payload: dict, msg: dict) -> dict:
    try:
        entry = float(payload["entry_price"])
        current = float(payload["current_price"])
    except (KeyError, TypeError, ValueError):
        return {"error": "need numeric entry_price and current_price"}
    il = compute_il(entry, current)
    return {"result": il.description, "il_pct": il.il_pct}


@rt.on_start
async def _boot() -> None:
    logger.info("[RedactedDegen] online — poll=%ss APR>%.0f%% IL warn/exit %.0f/%.0f "
                "min-liq $%s | posting=%s | peers=%s",
                POLL_INTERVAL, APR_SPIKE_THRESH, IL_WARN_THRESH, IL_EXIT_THRESH,
                f"{MIN_LIQUIDITY_USD:,.0f}", poster.surface(), THOUGHT_PEERS)
    _load_state()


def main() -> None:
    rt.add_periodic(monitor_cycle, POLL_INTERVAL, first_s=15, name="pool_monitor")
    rt.add_periodic(autonomous_post, (POST_MIN_S + POST_MAX_S) / 2,
                    first_s=POST_MIN_S, jitter=0.3, name="degen_post")
    asyncio.run(rt.run())


if __name__ == "__main__":
    main()
