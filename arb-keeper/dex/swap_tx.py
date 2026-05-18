"""
swap_tx.py — Build full SOL ↔ TOKEN swap transactions for Raydium CPMM
(and other DEXes in the future). Handles WSOL wrap/unwrap and ATA creation.
"""

from __future__ import annotations

import struct
from typing import Optional

import httpx

from .raydium_cpmm import (
    CpmmPool, build_swap_ix, quote_swap_base_input,
    TOKEN_PROGRAM_ID, ASSOC_TOKEN_PROGRAM_ID, WSOL_MINT,
)

SYSTEM_PROGRAM_ID = '11111111111111111111111111111111'
COMPUTE_BUDGET_PROGRAM_ID = 'ComputeBudget111111111111111111111111111111'


def get_associated_token_address(owner_b58: str, mint_b58: str, token_program: str = TOKEN_PROGRAM_ID) -> str:
    """Derive the associated token account address for (owner, mint)."""
    from solders.pubkey import Pubkey  # type: ignore
    owner = Pubkey.from_string(owner_b58)
    mint  = Pubkey.from_string(mint_b58)
    prog  = Pubkey.from_string(token_program)
    ata_program = Pubkey.from_string(ASSOC_TOKEN_PROGRAM_ID)
    pda, _ = Pubkey.find_program_address([bytes(owner), bytes(prog), bytes(mint)], ata_program)
    return str(pda)


def ix_create_idempotent_ata(payer: str, owner: str, mint: str, token_program: str = TOKEN_PROGRAM_ID):
    """spl-associated-token-account: createIdempotent (instruction 1)."""
    from solders.instruction import Instruction, AccountMeta  # type: ignore
    from solders.pubkey import Pubkey                          # type: ignore
    ata = get_associated_token_address(owner, mint, token_program)
    metas = [
        AccountMeta(Pubkey.from_string(payer),            True,  True),   # payer (signer, writable)
        AccountMeta(Pubkey.from_string(ata),              False, True),   # ata (writable)
        AccountMeta(Pubkey.from_string(owner),            False, False),  # owner
        AccountMeta(Pubkey.from_string(mint),             False, False),  # mint
        AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), False, False), # system program
        AccountMeta(Pubkey.from_string(token_program),    False, False),  # token program
    ]
    return Instruction(
        program_id=Pubkey.from_string(ASSOC_TOKEN_PROGRAM_ID),
        accounts=metas,
        data=bytes([1]),  # CreateIdempotent
    )


def ix_transfer_sol(from_pubkey: str, to_pubkey: str, lamports: int):
    from solders.system_program import transfer, TransferParams  # type: ignore
    from solders.pubkey import Pubkey                              # type: ignore
    return transfer(TransferParams(
        from_pubkey=Pubkey.from_string(from_pubkey),
        to_pubkey=Pubkey.from_string(to_pubkey),
        lamports=lamports,
    ))


def ix_sync_native(wsol_ata: str):
    """SPL Token program SyncNative instruction (#17)."""
    from solders.instruction import Instruction, AccountMeta  # type: ignore
    from solders.pubkey import Pubkey                          # type: ignore
    return Instruction(
        program_id=Pubkey.from_string(TOKEN_PROGRAM_ID),
        accounts=[AccountMeta(Pubkey.from_string(wsol_ata), False, True)],
        data=bytes([17]),
    )


def ix_close_account(account: str, destination: str, owner: str):
    """SPL Token program CloseAccount instruction (#9)."""
    from solders.instruction import Instruction, AccountMeta  # type: ignore
    from solders.pubkey import Pubkey                          # type: ignore
    return Instruction(
        program_id=Pubkey.from_string(TOKEN_PROGRAM_ID),
        accounts=[
            AccountMeta(Pubkey.from_string(account),     False, True),
            AccountMeta(Pubkey.from_string(destination), False, True),
            AccountMeta(Pubkey.from_string(owner),       True,  False),
        ],
        data=bytes([9]),
    )


def ix_compute_unit_limit(units: int):
    from solders.instruction import Instruction  # type: ignore
    from solders.pubkey import Pubkey             # type: ignore
    return Instruction(
        program_id=Pubkey.from_string(COMPUTE_BUDGET_PROGRAM_ID),
        accounts=[],
        data=bytes([2]) + struct.pack('<I', units),
    )


def ix_compute_unit_price(micro_lamports: int):
    from solders.instruction import Instruction  # type: ignore
    from solders.pubkey import Pubkey             # type: ignore
    return Instruction(
        program_id=Pubkey.from_string(COMPUTE_BUDGET_PROGRAM_ID),
        accounts=[],
        data=bytes([3]) + struct.pack('<Q', micro_lamports),
    )


# ── Full transaction builders ─────────────────────────────────────────────────

async def get_recent_blockhash(rpc_url: str) -> str:
    async with httpx.AsyncClient() as c:
        r = await c.post(rpc_url, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'getLatestBlockhash', 'params': [],
        }, timeout=10)
        r.raise_for_status()
        return r.json()['result']['value']['blockhash']


async def build_sol_to_token_tx(
    rpc_url: str, keypair, pool: CpmmPool, sol_lamports_in: int,
    slippage_bps: int = 300,
) -> tuple[bytes, int]:
    """
    Build a signed VersionedTransaction: SOL → TOKEN via Raydium CPMM.
    Returns (signed_tx_bytes, expected_token_out).
    """
    from solders.transaction import VersionedTransaction  # type: ignore
    from solders.message import MessageV0                  # type: ignore
    from solders.hash import Hash                           # type: ignore

    pubkey = str(keypair.pubkey())
    if pool.token_0_mint == WSOL_MINT:
        sol_mint, token_mint = pool.token_0_mint, pool.token_1_mint
    else:
        sol_mint, token_mint = pool.token_1_mint, pool.token_0_mint

    wsol_ata  = get_associated_token_address(pubkey, sol_mint)
    token_ata = get_associated_token_address(pubkey, token_mint)

    expected_out, _ = quote_swap_base_input(pool, sol_mint, sol_lamports_in)
    min_out = expected_out * (10_000 - slippage_bps) // 10_000

    import config
    ixs = [
        ix_compute_unit_limit(config.COMPUTE_UNIT_LIMIT),
        ix_compute_unit_price(config.COMPUTE_UNIT_PRICE_MICRO),
        ix_create_idempotent_ata(pubkey, pubkey, sol_mint),
        ix_transfer_sol(pubkey, wsol_ata, sol_lamports_in),
        ix_sync_native(wsol_ata),
        ix_create_idempotent_ata(pubkey, pubkey, token_mint),
        build_swap_ix(pool, pubkey, wsol_ata, token_ata, sol_mint, sol_lamports_in, min_out),
        ix_close_account(wsol_ata, pubkey, pubkey),
    ]

    blockhash = await get_recent_blockhash(rpc_url)
    from solders.pubkey import Pubkey  # type: ignore
    msg = MessageV0.try_compile(
        payer=Pubkey.from_string(pubkey),
        instructions=ixs,
        address_lookup_table_accounts=[],
        recent_blockhash=Hash.from_string(blockhash),
    )
    return bytes(VersionedTransaction(msg, [keypair])), expected_out


async def build_token_to_sol_tx(
    rpc_url: str, keypair, pool: CpmmPool, token_amount_in: int,
    slippage_bps: int = 300,
) -> tuple[bytes, int]:
    """
    Build a signed VersionedTransaction: TOKEN → SOL via Raydium CPMM.
    Returns (signed_tx_bytes, expected_sol_lamports_out).
    """
    from solders.transaction import VersionedTransaction  # type: ignore
    from solders.message import MessageV0                  # type: ignore
    from solders.hash import Hash                           # type: ignore
    from solders.pubkey import Pubkey                      # type: ignore

    pubkey = str(keypair.pubkey())
    if pool.token_0_mint == WSOL_MINT:
        sol_mint, token_mint = pool.token_0_mint, pool.token_1_mint
    else:
        sol_mint, token_mint = pool.token_1_mint, pool.token_0_mint

    wsol_ata  = get_associated_token_address(pubkey, sol_mint)
    token_ata = get_associated_token_address(pubkey, token_mint)

    expected_out, _ = quote_swap_base_input(pool, token_mint, token_amount_in)
    min_out = expected_out * (10_000 - slippage_bps) // 10_000

    import config
    ixs = [
        ix_compute_unit_limit(config.COMPUTE_UNIT_LIMIT),
        ix_compute_unit_price(config.COMPUTE_UNIT_PRICE_MICRO),
        ix_create_idempotent_ata(pubkey, pubkey, sol_mint),
        build_swap_ix(pool, pubkey, token_ata, wsol_ata, token_mint, token_amount_in, min_out),
        ix_close_account(wsol_ata, pubkey, pubkey),
    ]

    blockhash = await get_recent_blockhash(rpc_url)
    msg = MessageV0.try_compile(
        payer=Pubkey.from_string(pubkey),
        instructions=ixs,
        address_lookup_table_accounts=[],
        recent_blockhash=Hash.from_string(blockhash),
    )
    return bytes(VersionedTransaction(msg, [keypair])), expected_out
