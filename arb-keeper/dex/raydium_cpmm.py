"""
raydium_cpmm.py — Raydium Constant Product AMM (CPMM) direct integration.

Program: CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C
Reads pool state on-chain, computes swap output locally (constant-product with
fee deduction), and builds raw swap instructions for inclusion in our own
versioned transactions.

PoolState layout (8-byte Anchor discriminator + 629 bytes):
  amm_config            Pubkey  (32)
  pool_creator          Pubkey  (32)
  token_0_vault         Pubkey  (32)
  token_1_vault         Pubkey  (32)
  lp_mint               Pubkey  (32)
  token_0_mint          Pubkey  (32)
  token_1_mint          Pubkey  (32)
  token_0_program       Pubkey  (32)
  token_1_program       Pubkey  (32)
  observation_key       Pubkey  (32)
  auth_bump             u8
  status                u8
  lp_mint_decimals      u8
  mint_0_decimals       u8
  mint_1_decimals       u8
  lp_supply             u64
  protocol_fees_token_0 u64
  protocol_fees_token_1 u64
  fund_fees_token_0     u64
  fund_fees_token_1     u64
  open_time             u64
  padding               [u64; 32]

AmmConfig layout (8-byte disc + ...):
  bump                  u8
  disable_create_pool   bool
  index                 u16
  trade_fee_rate        u64       (in 1e6 units — 2500 = 0.25%)
  protocol_fee_rate     u64
  fund_fee_rate         u64
  create_pool_fee       u64
  protocol_owner        Pubkey
  fund_owner            Pubkey
  ...

Swap instruction (swap_base_input):
  discriminator:        [143, 190, 90, 218, 196, 30, 51, 222]
  amount_in:            u64
  minimum_amount_out:   u64
"""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from typing import Optional

import httpx

# ── Program constants ─────────────────────────────────────────────────────────
CPMM_PROGRAM_ID         = 'CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C'
CPMM_AUTHORITY_SEED     = b'vault_and_lp_mint_auth_seed'
TOKEN_PROGRAM_ID        = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
ASSOC_TOKEN_PROGRAM_ID  = 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'
WSOL_MINT               = 'So11111111111111111111111111111111111111112'
SWAP_BASE_INPUT_DISC    = bytes([143, 190, 90, 218, 196, 30, 51, 222])
FEE_DENOMINATOR         = 1_000_000


@dataclass
class CpmmPool:
    address:           str
    amm_config:        str
    token_0_vault:     str
    token_1_vault:     str
    token_0_mint:      str
    token_1_mint:      str
    token_0_program:   str
    token_1_program:   str
    observation_key:   str
    mint_0_decimals:   int
    mint_1_decimals:   int
    protocol_fee_0:    int
    protocol_fee_1:    int
    fund_fee_0:        int
    fund_fee_1:        int
    # Live vault balances (raw lamports), filled by read_pool
    vault_0_balance:   int = 0
    vault_1_balance:   int = 0
    # Fees from AmmConfig (1e6 denominator)
    trade_fee_rate:    int = 0


def _u64(data: bytes, off: int) -> int:
    return struct.unpack_from('<Q', data, off)[0]


def _pubkey_b58(raw: bytes) -> str:
    import base58
    return base58.b58encode(raw).decode()


def decode_pool_state(data_b64: str, address: str) -> CpmmPool:
    """Decode the on-chain CPMM PoolState account data."""
    data = base64.b64decode(data_b64)
    if len(data) < 8 + 10 * 32 + 5 + 6 * 8:
        raise ValueError(f'CPMM pool account too small: {len(data)} bytes')

    o = 8  # skip 8-byte anchor discriminator
    pk = lambda i: _pubkey_b58(data[o + i * 32:o + (i + 1) * 32])

    amm_config       = pk(0)
    # pool_creator   = pk(1)  # unused
    token_0_vault    = pk(2)
    token_1_vault    = pk(3)
    # lp_mint        = pk(4)  # unused
    token_0_mint     = pk(5)
    token_1_mint     = pk(6)
    token_0_program  = pk(7)
    token_1_program  = pk(8)
    observation_key  = pk(9)

    o += 10 * 32
    # auth_bump, status, lp_mint_decimals, mint_0_decimals, mint_1_decimals
    _, _, _, mint_0_decimals, mint_1_decimals = data[o], data[o+1], data[o+2], data[o+3], data[o+4]
    o += 5
    # lp_supply, protocol_fees_0, protocol_fees_1, fund_fees_0, fund_fees_1
    _              = _u64(data, o); o += 8
    protocol_fee_0 = _u64(data, o); o += 8
    protocol_fee_1 = _u64(data, o); o += 8
    fund_fee_0     = _u64(data, o); o += 8
    fund_fee_1     = _u64(data, o); o += 8

    return CpmmPool(
        address=address,
        amm_config=amm_config,
        token_0_vault=token_0_vault,
        token_1_vault=token_1_vault,
        token_0_mint=token_0_mint,
        token_1_mint=token_1_mint,
        token_0_program=token_0_program,
        token_1_program=token_1_program,
        observation_key=observation_key,
        mint_0_decimals=mint_0_decimals,
        mint_1_decimals=mint_1_decimals,
        protocol_fee_0=protocol_fee_0,
        protocol_fee_1=protocol_fee_1,
        fund_fee_0=fund_fee_0,
        fund_fee_1=fund_fee_1,
    )


def decode_amm_config_fee(data_b64: str) -> int:
    """Extract trade_fee_rate (in 1e6 units) from AmmConfig account."""
    data = base64.b64decode(data_b64)
    # 8 disc + 1 bump + 1 disable + 2 index = 12 bytes before trade_fee_rate
    return _u64(data, 12)


async def fetch_pool(rpc_url: str, pool_address: str) -> CpmmPool:
    """Read pool state + amm_config + both vault balances in 2 RPC calls."""
    async with httpx.AsyncClient() as c:
        # 1) Pool state
        r = await c.post(rpc_url, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'getAccountInfo',
            'params': [pool_address, {'encoding': 'base64'}],
        }, timeout=10)
        r.raise_for_status()
        pool_data = r.json()['result']['value']['data'][0]
        pool = decode_pool_state(pool_data, pool_address)

        # 2) AmmConfig + both vaults in one batched call
        r = await c.post(rpc_url, json={
            'jsonrpc': '2.0', 'id': 2, 'method': 'getMultipleAccounts',
            'params': [
                [pool.amm_config, pool.token_0_vault, pool.token_1_vault],
                {'encoding': 'base64'},
            ],
        }, timeout=10)
        r.raise_for_status()
        accounts = r.json()['result']['value']
        pool.trade_fee_rate = decode_amm_config_fee(accounts[0]['data'][0])

        # Token vault account: SPL Token account, amount is at offset 64 (u64)
        def vault_amount(data_b64: str) -> int:
            data = base64.b64decode(data_b64)
            return struct.unpack_from('<Q', data, 64)[0]

        pool.vault_0_balance = vault_amount(accounts[1]['data'][0])
        pool.vault_1_balance = vault_amount(accounts[2]['data'][0])
    return pool


def quote_swap_base_input(
    pool: CpmmPool, input_mint: str, amount_in: int,
) -> tuple[int, bool]:
    """
    Compute expected output using constant-product (x * y = k) with fee.
    Returns (amount_out, zero_for_one) where zero_for_one is True if
    swapping token_0 -> token_1.
    """
    if input_mint == pool.token_0_mint:
        zero_for_one = True
        reserve_in  = pool.vault_0_balance - pool.protocol_fee_0 - pool.fund_fee_0
        reserve_out = pool.vault_1_balance - pool.protocol_fee_1 - pool.fund_fee_1
    elif input_mint == pool.token_1_mint:
        zero_for_one = False
        reserve_in  = pool.vault_1_balance - pool.protocol_fee_1 - pool.fund_fee_1
        reserve_out = pool.vault_0_balance - pool.protocol_fee_0 - pool.fund_fee_0
    else:
        raise ValueError(f'{input_mint} is not in pool {pool.address}')

    if reserve_in <= 0 or reserve_out <= 0 or amount_in <= 0:
        return 0, zero_for_one

    # Fee deducted from input
    amount_in_after_fee = amount_in * (FEE_DENOMINATOR - pool.trade_fee_rate) // FEE_DENOMINATOR
    # Constant product: out = reserve_out * amount_in_after_fee / (reserve_in + amount_in_after_fee)
    amount_out = (reserve_out * amount_in_after_fee) // (reserve_in + amount_in_after_fee)
    return amount_out, zero_for_one


def derive_authority() -> str:
    """Derive the CPMM authority PDA (cached — same for every pool)."""
    from solders.pubkey import Pubkey  # type: ignore
    program = Pubkey.from_string(CPMM_PROGRAM_ID)
    pda, _ = Pubkey.find_program_address([CPMM_AUTHORITY_SEED], program)
    return str(pda)


def build_swap_ix(
    pool: CpmmPool,
    user_pubkey: str,
    user_input_ata: str,
    user_output_ata: str,
    input_mint: str,
    amount_in: int,
    min_amount_out: int,
):
    """Build a Raydium CPMM swap_base_input Instruction (returns solders.Instruction)."""
    from solders.instruction import Instruction, AccountMeta  # type: ignore
    from solders.pubkey import Pubkey                          # type: ignore

    zero_for_one = (input_mint == pool.token_0_mint)
    if zero_for_one:
        input_vault, output_vault = pool.token_0_vault, pool.token_1_vault
        input_program, output_program = pool.token_0_program, pool.token_1_program
        output_mint = pool.token_1_mint
    else:
        input_vault, output_vault = pool.token_1_vault, pool.token_0_vault
        input_program, output_program = pool.token_1_program, pool.token_0_program
        output_mint = pool.token_0_mint

    authority = derive_authority()

    def meta(addr: str, signer: bool, writable: bool) -> AccountMeta:
        return AccountMeta(pubkey=Pubkey.from_string(addr), is_signer=signer, is_writable=writable)

    accounts = [
        meta(user_pubkey,       True,  True),   # payer
        meta(authority,         False, False),  # authority PDA
        meta(pool.amm_config,   False, False),  # amm_config
        meta(pool.address,      False, True),   # pool_state
        meta(user_input_ata,    False, True),   # input_token_account
        meta(user_output_ata,   False, True),   # output_token_account
        meta(input_vault,       False, True),   # input_vault
        meta(output_vault,      False, True),   # output_vault
        meta(input_program,     False, False),  # input_token_program
        meta(output_program,    False, False),  # output_token_program
        meta(input_mint,        False, False),  # input_mint
        meta(output_mint,       False, False),  # output_mint
        meta(pool.observation_key, False, True),  # observation_state
    ]
    data = SWAP_BASE_INPUT_DISC + struct.pack('<QQ', amount_in, min_amount_out)
    return Instruction(
        program_id=Pubkey.from_string(CPMM_PROGRAM_ID),
        accounts=accounts,
        data=data,
    )
