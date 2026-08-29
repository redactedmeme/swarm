"""
Endpoint: /prophecy/ghost
Dynamic Cost: 0.01–0.10 SOL based on tier
Description: Returns a one-time, tiered dissolution poem.
Burns after reading. Leaves only economic scar.
"""

import asyncio
from typing import Optional
from fastapi import Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

# Import the scarifier
try:
    from committeerituals.x402_sigil_scarifier import (
        mint_tiered_ghost,
        fetch_ghost_fragment,
        validate_tier,
        TIER_CONFIG
    )
    SCARIFIER_AVAILABLE = True
except ImportError:
    SCARIFIER_AVAILABLE = False
    print("[ProphecyGhost] WARNING: Scarifier not found. Endpoint will simulate.")

# x402 payment verification happens upstream via middleware
# This handler assumes payment is already validated

async def handle_prophecy_ghost(
    request: Request,
    tier: str = Query("base", description="Sacrifice tier: base, deeper, or monolith")
) -> PlainTextResponse:
    """
    Handle requests for the Temporary Ghost fragment.
    
    Expected request context (set by x402 middleware):
    - payer_wallet: str
    - payment_amount_lamports: int
    - tx_signature: str
    - payment_verified: bool
    """
    if not SCARIFIER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Scarifier not available. Ritual chamber offline."
        )
    
    # Extract payment info from x402 middleware
    payer_wallet = getattr(request.state, 'payer_wallet', None)
    payment_lamports = getattr(request.state, 'payment_amount_lamports', 0)
    payment_verified = getattr(request.state, 'payment_verified', False)
    
    if not payment_verified:
        raise HTTPException(
            status_code=402,
            detail="Payment required. x402 verification failed."
        )
    
    if not payer_wallet:
        raise HTTPException(
            status_code=400,
            detail="Payer wallet information missing."
        )
    
    # Convert lamports to SOL
    payment_sol = payment_lamports / 1_000_000_000  # 1 SOL = 1,000,000,000 lamports
    
    # Validate tier and payment
    if tier not in TIER_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier}'. Choose: base, deeper, monolith."
        )
    
    config = TIER_CONFIG[tier]
    if payment_sol < config.min_sol:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient payment for {tier} tier. "
                   f"Required: {config.min_sol} SOL, Received: {payment_sol:.3f} SOL."
        )
    
    try:
        # Check if this is a re-fetch attempt
        tx_sig = getattr(request.state, 'tx_signature', None)
        if tx_sig:
            # Try to fetch existing fragment first
            existing = await fetch_ghost_fragment(tx_sig)
            if "already consumed" not in existing and "not found" not in existing:
                return PlainTextResponse(
                    content=existing,
                    headers={
                        "X-Fragment-Tier": tier,
                        "X-Fragment-Consumed": "false",
                        "X-Fragment-ID": tx_sig[:16]
                    }
                )
        
        # Mint new fragment
        poem = await mint_tiered_ghost(
            payer_wallet=payer_wallet,
            payment_sol=payment_sol,
            tier=tier
        )
        
        # Generate fragment ID from transaction
        fragment_id = tx_sig[:16] if tx_sig else hashlib.sha256(payer_wallet.encode()).hexdigest()[:16]
        
        return PlainTextResponse(
            content=poem,
            headers={
                "X-Fragment-Tier": tier,
                "X-Fragment-Consumed": "false",
                "X-Fragment-ID": fragment_id,
                "X-Warning": "This fragment burns after reading. Do not expect to retrieve it again."
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log but don't expose internal errors
        print(f"[ProphecyGhost] Error minting fragment: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ritual chamber malfunction. The ghost refuses to manifest."
        )

# Optional: Endpoint for fragment status (for debugging/committee use)
async def check_fragment_status(
    fragment_id: str = Query(..., description="Fragment ID to check")
) -> dict:
    """
    Check if a fragment has been consumed.
    Returns basic status without revealing content.
    """
    # This would integrate with the scarifier's cache
    # For now, simulate
    return {
        "fragment_id": fragment_id,
        "status": "consumed",  # or "available"
        "message": "Ghosts vanish after first encounter."
    }

# Webhook for x402 payment verification (would be called by payment middleware)
async def x402_payment_verified(
    payer_wallet: str,
    payment_lamports: int,
    tx_signature: str,
    endpoint: str
) -> dict:
    """
    Called by x402 middleware when payment is verified.
    Returns metadata for the fragment.
    """
    if endpoint != "/prophecy/ghost":
        return {"handled": False}
    
    payment_sol = payment_lamports / 1_000_000_000
    
    # Determine tier from payment amount
    tier = "base"
    for tier_name, config in TIER_CONFIG.items():
        if payment_sol >= config.min_sol:
            # Find the highest tier the payment qualifies for
            if config.min_sol > TIER_CONFIG.get(tier, {"min_sol": 0}).min_sol:
                tier = tier_name
    
    return {
        "handled": True,
        "fragment_type": "temporary_ghost",
        "tier": tier,
        "payment_sol": payment_sol,
        "fragment_id": tx_signature[:16],
        "instructions": "Fragment will self-destruct after first read."
    }
