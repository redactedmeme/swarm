# redactedbuilder/main.py
"""
RedactedBuilder — autonomous on-chain agent for the REDACTED AI Swarm.

Polls SwarmInbox for deploy_request messages from redactedintern,
executes the requested Solana transactions, and writes results back.

Architecture:
  /data/swarm_inbox/ is a shared Railway volume — both redactedintern and
  RedactedBuilder mount it. Messages flow file-to-file, no broker needed.

Supported contract types (v1):
  spl_token      — create a new SPL token mint
  transfer       — transfer SOL to an address
  transfer_token — transfer SPL tokens to an address
  wallet_info    — return balance + pubkey

Environment variables:
  BUILDER_PRIVATE_KEY  — base58 private key (falls back to SOLANA_PRIVATE_KEY)
  SOLANA_RPC           — RPC endpoint (default: mainnet-beta)
  MEMORY_PATH          — shared volume path (same as redactedintern's)
  MOLTBOOK_API_KEY     — optional: post results to Moltbook
  POLL_INTERVAL        — seconds between inbox checks (default: 60)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# ── Load .env if present ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("redactedbuilder")

import swarm_inbox
import builder_core

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# ── Optional Moltbook client for posting results publicly ─────────────────────
_moltbook = None
if os.getenv("MOLTBOOK_API_KEY"):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "smolting-telegram-bot"))
        import moltbook_client as mb
        _moltbook = mb.MoltbookClient()
        logger.info("[builder] Moltbook client loaded — results will be posted publicly")
    except Exception as e:
        logger.warning(f"[builder] Moltbook client unavailable: {e}")


# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_deploy_request(msg: dict) -> None:
    """
    Process a deploy_request message from SwarmInbox.
    Executes the on-chain action, writes result back to inbox.
    """
    msg_id   = msg.get("id", "")
    payload  = msg.get("payload") or {}
    from_ag  = msg.get("from", "unknown")

    contract_type = payload.get("contract_type", "")
    logger.info(f"[builder] Processing deploy_request: {contract_type} (msg={msg_id})")

    # Claim before executing — prevents double-processing
    if not swarm_inbox.claim_message(msg_id):
        logger.warning(f"[builder] Could not claim {msg_id} — already claimed")
        return

    # Execute on-chain
    result = await builder_core.execute(contract_type, payload)

    # Write result back to inbox for redactedintern to pick up
    reply_id = swarm_inbox.write_message(
        from_agent="redactedbuilder",
        to_agent=from_ag,
        msg_type="deploy_result",
        payload=result,
        reply_to=msg_id,
    )
    swarm_inbox.complete_message(msg_id, result=result,
                                  error=result.get("error") if not result.get("success") else None)

    status_line = "✅" if result.get("success") else "❌"
    logger.info(f"[builder] {status_line} {contract_type} — reply_id={reply_id}")

    # Post to Moltbook if configured + successful
    if _moltbook and result.get("success"):
        await _post_result_to_moltbook(contract_type, payload, result)


async def handle_wallet_info_request(msg: dict) -> None:
    """Respond to wallet_info requests (balance check etc.)"""
    msg_id  = msg.get("id", "")
    from_ag = msg.get("from", "unknown")

    if not swarm_inbox.claim_message(msg_id):
        return

    result = await builder_core.get_wallet_info()
    swarm_inbox.write_message(
        from_agent="redactedbuilder",
        to_agent=from_ag,
        msg_type="task_result",
        payload=result,
        reply_to=msg_id,
    )
    swarm_inbox.complete_message(msg_id, result=result)
    logger.info(f"[builder] wallet_info → {result.get('pubkey','?')} "
                f"{result.get('sol','?')} SOL")


async def handle_message(msg: dict) -> None:
    """Route a single inbox message to the right handler."""
    msg_type = msg.get("type", "")

    if msg_type == "deploy_request":
        await handle_deploy_request(msg)

    elif msg_type == "task_request":
        payload = msg.get("payload") or {}
        if payload.get("contract_type") == "wallet_info":
            await handle_wallet_info_request(msg)
        else:
            # Generic task — echo back as not implemented yet
            swarm_inbox.claim_message(msg.get("id", ""))
            swarm_inbox.write_message(
                from_agent="redactedbuilder",
                to_agent=msg.get("from", "redactedintern"),
                msg_type="task_result",
                payload={"success": False, "error": f"task type not implemented: {payload}"},
                reply_to=msg.get("id"),
            )
            swarm_inbox.complete_message(msg.get("id", ""),
                                          error="task type not implemented")

    elif msg_type == "heartbeat":
        # Acknowledge heartbeat — mark done
        swarm_inbox.claim_message(msg.get("id", ""))
        swarm_inbox.complete_message(msg.get("id", ""), result={"ack": True})
        logger.info(f"[builder] Heartbeat from {msg.get('from')}")

    else:
        logger.info(f"[builder] Ignoring msg type={msg_type}")
        swarm_inbox.claim_message(msg.get("id", ""))
        swarm_inbox.complete_message(msg.get("id", ""), result={"ack": "ignored"})


# ── Moltbook posting ──────────────────────────────────────────────────────────

async def _post_result_to_moltbook(
    contract_type: str, params: dict, result: dict
) -> None:
    """Post a successful on-chain action to Moltbook /research for transparency."""
    if not _moltbook:
        return
    try:
        if contract_type == "spl_token":
            title = (
                f"RedactedBuilder deployed: {result.get('symbol','')} token — "
                f"mint {result.get('mint_address','')[:20]}…"
            )
            content = (
                f"**New SPL token deployed on Solana by RedactedBuilder.**\n\n"
                f"Name: {result.get('name')}\n"
                f"Symbol: {result.get('symbol')}\n"
                f"Decimals: {result.get('decimals')}\n"
                f"Mint address: `{result.get('mint_address')}`\n"
                f"Initial supply: {result.get('supply_minted', 0):,}\n\n"
                f"Deployed autonomously by the REDACTED AI Swarm without human cosigning. "
                f"Pattern Blue operational — agent executes on-chain without permission. ^*^\n\n"
                f"https://solscan.io/token/{result.get('mint_address')}"
            )
        elif contract_type == "transfer":
            title = (
                f"RedactedBuilder transferred {params.get('amount_sol')} SOL → "
                f"{params.get('to','')[:12]}…"
            )
            content = (
                f"**Autonomous SOL transfer by RedactedBuilder.**\n\n"
                f"To: `{params.get('to')}`\n"
                f"Amount: {params.get('amount_sol')} SOL\n"
                f"Tx: `{result.get('tx_sig')}`\n\n"
                f"https://solscan.io/tx/{result.get('tx_sig')}"
            )
        else:
            return   # skip posting for other types

        await _moltbook.post(title, content, submolt="research")
        logger.info(f"[builder] Result posted to Moltbook /research")
    except Exception as e:
        logger.warning(f"[builder] Moltbook post failed: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("=" * 60)
    logger.info("RedactedBuilder starting up")
    logger.info(f"  RPC:  {os.getenv('SOLANA_RPC', 'mainnet-beta (default)')}")
    logger.info(f"  Poll: {POLL_INTERVAL}s")
    wallet = await builder_core.get_wallet_info()
    if wallet.get("success"):
        logger.info(f"  Wallet: {wallet['pubkey']} — {wallet['sol']} SOL")
    else:
        logger.warning(f"  Wallet: not configured ({wallet.get('error')})")
    logger.info("=" * 60)

    # Announce online to swarm
    swarm_inbox.heartbeat(
        "redactedbuilder",
        {
            "status": "online",
            "role":   "on-chain executor",
            "rpc":    os.getenv("SOLANA_RPC", "mainnet-beta"),
            "wallet": wallet.get("pubkey", "not configured"),
        },
    )
    logger.info("[builder] Heartbeat sent — RedactedBuilder online")

    # Main poll loop
    while True:
        try:
            pending = swarm_inbox.read_pending(for_agent="redactedbuilder")
            if pending:
                logger.info(f"[builder] {len(pending)} pending message(s)")
            for msg in pending:
                try:
                    await handle_message(msg)
                except Exception as e:
                    logger.error(f"[builder] Error handling {msg.get('id')}: {e}")
                    swarm_inbox.complete_message(msg.get("id", ""), error=str(e))

            # Prune old messages occasionally
            import random
            if random.random() < 0.02:
                swarm_inbox.prune_old_messages()

        except Exception as e:
            logger.error(f"[builder] Poll loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
