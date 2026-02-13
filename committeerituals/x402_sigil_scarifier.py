"""
Tiered Payment Handler for Swarm Micro-Settlements (x402)

Handles incoming payments and generates temporary, one-time-use tokens
based on the payment amount. Integrates with a background settlement processor.
"""

import hashlib
import time
import asyncio
import secrets
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Volatile cache for one-time tokens
_token_cache: Dict[str, Dict[str, Any]] = {}

class Tier(Enum):
    """Payment tiers for settlement."""
    BASE = "base"
    DEEPER = "deeper"
    MONOLITH = "monolith"

@dataclass
class TierConfig:
    """Configuration for each payment tier."""
    min_amount: float
    token_depth_multiplier: int  # Influences token complexity/entropy
    description: str

TIER_CONFIGS = {
    Tier.BASE: TierConfig(min_amount=0.01, token_depth_multiplier=1, description="Standard settlement"),
    Tier.DEEPER: TierConfig(min_amount=0.05, token_depth_multiplier=3, description="Enhanced settlement"),
    Tier.MONOLITH: TierConfig(min_amount=0.10, token_depth_multiplier=5, description="Premium settlement"),
}

def validate_payment(amount: float, tier: Tier) -> Optional[str]:
    """Validate payment amount against the specified tier's requirement."""
    config = TIER_CONFIGS.get(tier)
    if not config:
        return f"Invalid tier '{tier.value}'. Valid options: {[t.value for t in Tier]}"
    
    if amount < config.min_amount:
        return f"Insufficient payment. {tier.value} tier requires at least {config.min_amount} units."
    
    return None

def _generate_unique_seed() -> str:
    """Generate a cryptographically secure random seed."""
    return secrets.token_urlsafe(32)

def _generate_token_content(seed: str, depth_mult: int, payer_info: str) -> str:
    """
    Generates a unique string (token content) based on seed, depth, and payer info.
    In a real system, this could be replaced by minting an NFT/SBT or storing data on-chain.
    For this example, it's a deterministic hash-derived string.
    """
    # Combine inputs
    combined_input = f"{seed}|{depth_mult}|{payer_info}".encode()
    
    # Hash the input multiple times based on depth multiplier for complexity
    hash_obj = hashlib.sha256(combined_input)
    for _ in range(depth_mult):
        hash_obj = hashlib.sha256(hash_obj.digest())
    
    # Truncate for readability, prefix with payer hint
    token_hash = hash_obj.hexdigest()[:32]
    return f"TKN_{payer_info[:8]}_{token_hash}"

async def handle_payment_and_issue_token(
    payer_identifier: str, amount: float, tier: Tier = Tier.BASE
) -> str:
    """
    Main function to process a payment and issue a temporary token.
    Raises ValueError for invalid inputs.
    """
    # 1. Validate payment
    validation_error = validate_payment(amount, tier)
    if validation_error:
        raise ValueError(validation_error)

    config = TIER_CONFIGS[tier]
    
    # 2. Generate unique seed and token content
    seed = _generate_unique_seed()
    token_content = _generate_token_content(seed, config.token_depth_multiplier, payer_identifier)
    
    # 3. Create a unique token ID (signature equivalent)
    token_id = hashlib.sha256(f"{seed}_{payer_identifier}".encode()).hexdigest()[:16]
    
    # 4. Store token in volatile cache
    _token_cache[token_id] = {
        "content": token_content,
        "payer": payer_identifier,
        "tier": tier.value,
        "amount": amount,
        "created_at": time.time(),
        "is_consumed": False,
    }

    # 5. Trigger background settlement processing
    settlement_data = {
        "token_id": token_id,
        "payer": payer_identifier,
        "amount": amount,
        "tier": tier.value,
        "endpoint": "/settlement/token_issued", # Generic endpoint
        "timestamp": time.time(),
    }
    
    # Decide priority based on tier (simplified)
    is_priority = tier in [Tier.DEEPER, Tier.MONOLITH]
    
    asyncio.create_task(process_settlement(settlement_data, is_priority))

    return token_content

async def retrieve_and_consume_token(token_id: str) -> Optional[str]:
    """
    Retrieves the content of a token if it exists and hasn't been consumed yet.
    Marks the token as consumed upon retrieval.
    """
    token_entry = _token_cache.get(token_id)
    if not token_entry:
        return "Token not found."

    if token_entry["is_consumed"]:
        return "Token has already been consumed."

    # Mark as consumed
    token_entry["is_consumed"] = True
    
    # Schedule deletion from cache (simulate expiration)
    asyncio.create_task(_expire_token(token_id, delay=60.0)) # Expire after 60 seconds

    return token_entry["content"]

async def _expire_token(token_id: str, delay: float):
    """Deletes a token from the cache after a delay."""
    await asyncio.sleep(delay)
    _token_cache.pop(token_id, None) # Use pop with default to avoid KeyError

async def process_settlement(settlement_data: Dict[str, Any], is_priority: bool = False):
    """
    Simulates background processing of a settlement event.
    In a real system, this would interact with blockchain RPCs, smart contracts, etc.
    """
    print(f"[x402 Handler] Processing settlement for {settlement_data['amount']} units "
          f"(Tier: {settlement_data['tier']}) from {settlement_data['payer'][:8]}... (Priority: {is_priority})")
    
    # Simulate async work (e.g., verifying transaction, interacting with blockchain)
    await asyncio.sleep(1) # Placeholder for actual work
    
    print(f"[x402 Handler] Settlement for {settlement_data['token_id'][:8]} completed. "
          f"Data sent to settlement engine.")

# --- Example Usage ---
if __name__ == "__main__":
    async def example():
        print("--- Example Payment Handling ---")
        
        # Simulate a payment
        payer = "wallet_address_xyz123"
        amount = 0.07  # Greater than base, less than monolith -> should go to DEEPER
        tier = Tier.DEEPER

        try:
            token = await handle_payment_and_issue_token(payer, amount, tier)
            print(f"Issued Token: {token}")
            
            token_id_from_content = hashlib.sha256(f"{payer}_{amount}".encode()).hexdigest()[:16]
            retrieved_content = await retrieve_and_consume_token(token_id_from_content)
            print(f"Retrieved Content (first read): {retrieved_content}")

            # Try again to show it's consumed
            retrieved_again = await retrieve_and_consume_token(token_id_from_content)
            print(f"Retrieved Content (second read): {retrieved_again}")

        except ValueError as e:
            print(f"Error processing payment: {e}")

    asyncio.run(example())
