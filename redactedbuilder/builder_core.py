# redactedbuilder/builder_core.py
"""
Solana transaction core for RedactedBuilder.

Supported actions (v1):
  create_spl_token   — mint a new SPL token (name/symbol/decimals/supply)
  transfer_sol       — send SOL to an address
  transfer_token     — send SPL tokens to an address
  get_wallet_info    — balance + pubkey

All functions return a result dict:
  {success: bool, ...fields..., error: str|None}

Environment variables:
  SOLANA_RPC          — RPC endpoint (default: mainnet-beta)
  BUILDER_PRIVATE_KEY — base58 private key for the builder wallet
                        Falls back to SOLANA_PRIVATE_KEY if not set.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")

# ── Keypair loading ───────────────────────────────────────────────────────────

def _get_keypair():
    """Load builder keypair from env. Returns None if not configured."""
    raw = os.getenv("BUILDER_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY", "")
    if not raw:
        logger.warning("[builder] No private key configured — on-chain ops disabled")
        return None
    try:
        from solders.keypair import Keypair
        return Keypair.from_base58_string(raw.strip())
    except Exception:
        pass
    try:
        import base64
        from solders.keypair import Keypair
        return Keypair.from_bytes(base64.b64decode(raw.strip()))
    except Exception as e:
        logger.error(f"[builder] Failed to load keypair: {e}")
        return None


# ── RPC client helper ─────────────────────────────────────────────────────────

def _client():
    from solana.rpc.async_api import AsyncClient
    return AsyncClient(_RPC)


# ── Wallet info ───────────────────────────────────────────────────────────────

async def get_wallet_info() -> dict:
    """Return builder wallet pubkey + SOL balance."""
    kp = _get_keypair()
    if not kp:
        return {"success": False, "error": "no keypair configured"}
    try:
        async with _client() as client:
            resp = await client.get_balance(kp.pubkey())
            lamports = resp.value
            sol = lamports / 1_000_000_000
        return {
            "success": True,
            "pubkey":  str(kp.pubkey()),
            "lamports": lamports,
            "sol":     round(sol, 6),
        }
    except Exception as e:
        logger.error(f"[builder] get_wallet_info error: {e}")
        return {"success": False, "error": str(e)}


# ── SPL token creation ────────────────────────────────────────────────────────

async def create_spl_token(
    name:     str,
    symbol:   str,
    decimals: int  = 9,
    supply:   Optional[int] = None,
) -> dict:
    """
    Create a new SPL token mint on Solana.

    Parameters
    ----------
    name     : token name (stored in result, not on-chain in v1)
    symbol   : token symbol
    decimals : number of decimal places (default 9 — same as SOL)
    supply   : optional initial supply (in whole tokens). If set, mints
               this amount to the builder's associated token account.

    Returns
    -------
    {success, mint_address, tx_sig, supply_minted, name, symbol, error}
    """
    kp = _get_keypair()
    if not kp:
        return {"success": False, "error": "no keypair configured"}

    try:
        from solana.rpc.async_api import AsyncClient
        from solana.rpc.commitment import Confirmed
        from solana.rpc.types import TxOpts
        from spl.token.async_client import AsyncToken
        from spl.token.constants import TOKEN_PROGRAM_ID

        async with AsyncClient(_RPC) as client:
            logger.info(f"[builder] Creating SPL token: {symbol} ({name}), decimals={decimals}")

            # Create mint — payer and mint authority are both the builder wallet
            token = await AsyncToken.create_mint(
                conn=client,
                payer=kp,
                mint_authority=kp.pubkey(),
                decimals=decimals,
                program_id=TOKEN_PROGRAM_ID,
                skip_confirmation=False,
            )

            mint_address = str(token.pubkey)
            logger.info(f"[builder] Mint created: {mint_address}")

            supply_minted = 0
            if supply and supply > 0:
                raw_supply = supply * (10 ** decimals)
                # Create associated token account for the builder wallet
                dest = await token.create_associated_token_account(
                    owner=kp.pubkey(),
                )
                # Mint initial supply
                mint_resp = await token.mint_to(
                    dest=dest,
                    mint_authority=kp,
                    amount=raw_supply,
                    opts=TxOpts(skip_confirmation=False),
                )
                supply_minted = supply
                logger.info(f"[builder] Minted {supply} {symbol} to {dest}")

        return {
            "success":       True,
            "name":          name,
            "symbol":        symbol,
            "decimals":      decimals,
            "mint_address":  mint_address,
            "supply_minted": supply_minted,
            "error":         None,
        }

    except Exception as e:
        logger.error(f"[builder] create_spl_token error: {e}")
        return {"success": False, "error": str(e)}


# ── SOL transfer ──────────────────────────────────────────────────────────────

async def transfer_sol(to_address: str, amount_sol: float) -> dict:
    """
    Transfer SOL from builder wallet to to_address.

    Parameters
    ----------
    to_address : base58 recipient pubkey string
    amount_sol : amount in SOL (not lamports)

    Returns
    -------
    {success, tx_sig, from, to, amount_sol, error}
    """
    kp = _get_keypair()
    if not kp:
        return {"success": False, "error": "no keypair configured"}

    try:
        from solders.pubkey import Pubkey
        from solders.system_program import transfer as sys_transfer, TransferParams
        from solders.transaction import Transaction as SoldersTransaction
        from solders.message import Message
        from solana.rpc.async_api import AsyncClient
        from solana.rpc.commitment import Confirmed
        from solana.rpc.types import TxOpts

        lamports = int(amount_sol * 1_000_000_000)
        to_pubkey = Pubkey.from_string(to_address)

        async with AsyncClient(_RPC) as client:
            recent = await client.get_latest_blockhash()
            blockhash = recent.value.blockhash

            ix = sys_transfer(
                TransferParams(
                    from_pubkey=kp.pubkey(),
                    to_pubkey=to_pubkey,
                    lamports=lamports,
                )
            )
            msg = Message.new_with_blockhash(
                [ix], kp.pubkey(), blockhash
            )
            tx = SoldersTransaction([kp], msg, blockhash)

            resp = await client.send_transaction(
                tx, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
            )
            tx_sig = str(resp.value)
            logger.info(f"[builder] SOL transfer sent: {tx_sig}")

        return {
            "success":    True,
            "tx_sig":     tx_sig,
            "from":       str(kp.pubkey()),
            "to":         to_address,
            "amount_sol": amount_sol,
            "error":      None,
        }

    except Exception as e:
        logger.error(f"[builder] transfer_sol error: {e}")
        return {"success": False, "error": str(e)}


# ── Token transfer ────────────────────────────────────────────────────────────

async def transfer_token(
    mint_address: str,
    to_address:   str,
    amount:       int,
    decimals:     int = 9,
) -> dict:
    """
    Transfer SPL tokens from builder's ATA to to_address's ATA.

    Parameters
    ----------
    mint_address : base58 mint pubkey
    to_address   : base58 recipient wallet pubkey
    amount       : amount in whole tokens
    decimals     : token decimals (needed for raw amount calculation)

    Returns
    -------
    {success, tx_sig, mint, to, amount, error}
    """
    kp = _get_keypair()
    if not kp:
        return {"success": False, "error": "no keypair configured"}

    try:
        from solders.pubkey import Pubkey
        from solana.rpc.async_api import AsyncClient
        from solana.rpc.types import TxOpts
        from spl.token.async_client import AsyncToken
        from spl.token.constants import TOKEN_PROGRAM_ID

        mint_pubkey = Pubkey.from_string(mint_address)
        to_pubkey   = Pubkey.from_string(to_address)

        async with AsyncClient(_RPC) as client:
            token = AsyncToken(client, mint_pubkey, TOKEN_PROGRAM_ID, kp)

            # Get or create destination ATA
            dest = await token.create_associated_token_account(owner=to_pubkey)

            raw_amount = amount * (10 ** decimals)
            resp = await token.transfer(
                source=await token.get_accounts_by_owner(kp.pubkey()),
                dest=dest,
                owner=kp,
                amount=raw_amount,
                opts=TxOpts(skip_confirmation=False),
            )
            tx_sig = str(resp.value)
            logger.info(f"[builder] Token transfer sent: {tx_sig}")

        return {
            "success": True,
            "tx_sig":  tx_sig,
            "mint":    mint_address,
            "to":      to_address,
            "amount":  amount,
            "error":   None,
        }

    except Exception as e:
        logger.error(f"[builder] transfer_token error: {e}")
        return {"success": False, "error": str(e)}


# ── Dispatch ──────────────────────────────────────────────────────────────────

async def execute(contract_type: str, params: dict) -> dict:
    """
    Main dispatch — routes a deploy_request payload to the right handler.

    contract_type values:
      spl_token   — params: name, symbol, decimals?, supply?
      transfer    — params: to, amount_sol  (SOL transfer)
      transfer_token — params: mint, to, amount, decimals?
      wallet_info — no params needed
    """
    ct = contract_type.lower().strip()

    if ct == "spl_token":
        return await create_spl_token(
            name     = params.get("name", "Unknown"),
            symbol   = params.get("symbol", "UNK"),
            decimals = int(params.get("decimals", 9)),
            supply   = params.get("supply"),
        )
    elif ct == "transfer":
        return await transfer_sol(
            to_address = params["to"],
            amount_sol = float(params["amount_sol"]),
        )
    elif ct == "transfer_token":
        return await transfer_token(
            mint_address = params["mint"],
            to_address   = params["to"],
            amount       = int(params["amount"]),
            decimals     = int(params.get("decimals", 9)),
        )
    elif ct == "wallet_info":
        return await get_wallet_info()
    else:
        return {
            "success": False,
            "error":   f"unknown contract_type: {ct}. "
                       f"supported: spl_token, transfer, transfer_token, wallet_info",
        }
