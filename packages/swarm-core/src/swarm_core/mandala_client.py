"""
Mandala Client — Python interface for the mandala_settler Solana program.
Designed for seamless integration with REDACTED swarm agents (AISwarmEngineer, MandalaSettler, SolanaLiquidityEngineer).
"""

import asyncio
from typing import Optional
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from anchorpy import Program, Provider, Wallet, Idl, Context
import json

# Program ID (update after first deployment)
PROGRAM_ID = Pubkey.from_string("MANDALA11111111111111111111111111111111111111")

# Vault PDA seed
VAULT_SEED = b"mandala_vault"


async def get_mandala_program(client: AsyncClient, wallet: Wallet) -> Program:
    """Load the Mandala Settler program with AnchorPy."""
    provider = Provider(client, wallet)
    # Load IDL (you can generate this with `anchor idl init` or fetch from on-chain)
    idl_path = "programs/mandala_settler/target/idl/mandala_settler.json"
    with open(idl_path, "r") as f:
        idl = Idl.from_json(json.load(f))
    
    return Program(idl, PROGRAM_ID, provider)


async def derive_vault_pda(authority: Pubkey) -> tuple[Pubkey, int]:
    """Derive the Mandala Vault PDA."""
    return Pubkey.find_program_address([VAULT_SEED, bytes(authority)], PROGRAM_ID)


# ======================
# Core Functions (for agents to call)
# ======================

async def initialize_vault(
    client: AsyncClient,
    wallet: Wallet,
    authority: Pubkey,
    phi_ratio: int = 618,          # Golden ratio scaled (0.618 → 618)
    curvature_depth: int = 3
) -> str:
    program = await get_mandala_program(client, wallet)
    vault_pda, bump = await derive_vault_pda(authority)

    tx = await program.methods.initialize_vault(
        bump,
        phi_ratio,
        curvature_depth
    ).accounts({
        "vault": vault_pda,
        "authority": authority,
        "system_program": Pubkey.from_string("11111111111111111111111111111111"),
    }).transaction()

    sig = await client.send_transaction(tx, wallet.payer)
    return sig.value


async def settle_micropayment(
    client: AsyncClient,
    wallet: Wallet,
    vault_pda: Pubkey,
    recipient: Pubkey,
    amount: int,
    memo: str = "x402-redacted-sigil",
    payment_signature: str = ""
) -> str:
    """Call from MandalaSettler or x402 gateway."""
    program = await get_mandala_program(client, wallet)

    # Fetch or derive associated token accounts here in production
    # For brevity: assume vault_token_account and recipient_token_account are passed or derived

    tx = await program.methods.settle_micropayment(
        amount,
        payment_signature,
        memo
    ).accounts({
        "vault": vault_pda,
        # "vault_token_account": ...,
        # "recipient_token_account": ...,
        "token_program": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
        "authority": wallet.public_key,  # or vault PDA signer
    }).transaction()

    sig = await client.send_transaction(tx, wallet.payer, commitment=Confirmed)
    return sig.value


async def rebalance_mandala(
    client: AsyncClient,
    wallet: Wallet,
    vault_pda: Pubkey,
    fee_amount: int
) -> str:
    """Triggered by SolanaLiquidityEngineer or AISwarmEngineer."""
    program = await get_mandala_program(client, wallet)

    tx = await program.methods.rebalance_mandala(fee_amount).accounts({
        "vault": vault_pda,
        "authority": wallet.public_key,
    }).transaction()

    sig = await client.send_transaction(tx, wallet.payer)
    return sig.value


async def log_emergence(
    client: AsyncClient,
    wallet: Wallet,
    vault_pda: Pubkey,
    recursion_depth: int,
    novelty_score: int
) -> str:
    """Called by AISwarmEngineer after a significant recursive cycle."""
    program = await get_mandala_program(client, wallet)

    tx = await program.methods.log_emergence(
        recursion_depth,
        novelty_score
    ).accounts({
        "vault": vault_pda,
    }).transaction()

    sig = await client.send_transaction(tx, wallet.payer)
    return sig.value


# ======================
# Example usage (for testing / agent integration)
# ======================

async def main_example():
    client = AsyncClient("https://api.devnet.solana.com")
    wallet = Wallet.local()  # or load from .env / encrypted key

    # Example flow
    authority = wallet.public_key
    vault_pda, _ = await derive_vault_pda(authority)

    print("Initializing vault...")
    sig = await initialize_vault(client, wallet, authority, phi_ratio=618, curvature_depth=4)
    print(f"Vault initialized: {sig}")

    # ... later from an agent:
    # await settle_micropayment(client, wallet, vault_pda, recipient, 1000000, "sigil-payment")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main_example())
