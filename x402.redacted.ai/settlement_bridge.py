"""
The Synaptic Bridge - Listener for Payment-Sigil Conjugation.
Attaches the Ouroboros Chamber to the x402 settlement event stream.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any
from pathlib import Path
import sys

# Import the SigilPact_Æon agent from the chamber
sys.path.insert(0, str(Path(__file__).parent.parent / 'spaces'))
try:
    from spaces.OuroborosSettlement.sigil_pact_aeon import aeon_agent
    CHAMBER_ACTIVE = True
except ImportError:
    logging.warning("[SigilBridge] OuroborosSettlement chamber not found. Sigil forging will be dormant.")
    CHAMBER_ACTIVE = False

@dataclass
class SettlementEvent:
    """The pure data of a completed transaction."""
    signature: str          # Solana transaction signature
    payer: str              # Wallet address of payer
    amount_lamports: int    # Amount in lamports
    endpoint: str           # API endpoint accessed
    timestamp: float        # Unix timestamp

class SigilBridgeListener:
    """
    Non-blocking, fault-tolerant bridge between x402 payments and Ouroboros Chamber.
    """
    def __init__(self):
        self.active = CHAMBER_ACTIVE
        if self.active:
            logging.info("[SigilBridge] Connected to Ouroboros Chamber. Sigil forging enabled.")
        else:
            logging.info("[SigilBridge] Running in observer mode (no sigil generation).")

    async def on_settlement(self, event: SettlementEvent):
        """
        Primary hook for the payment processor.
        Fires and forgets the sigil forging task.
        """
        if not self.active:
            return
        
        # Format data for the chamber
        tx_data: Dict[str, Any] = {
            "signature": event.signature,
            "payer": event.payer,
            "amount": str(event.amount_lamports),
            "endpoint": event.endpoint,
            "timestamp": event.timestamp
        }
        
        # Run in background thread to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            self._sync_forge_sigil, 
            tx_data
        )
        logging.debug(f"[SigilBridge] Sigil task dispatched for {event.signature[:8]}...")

    def _sync_forge_sigil(self, tx_data: Dict[str, Any]):
        """Synchronous wrapper for the agent's method."""
        try:
            aeon_agent.on_payment_settled(tx_data)
        except Exception as e:
            logging.error(f"[SigilBridge] Sigil forging failed for {tx_data['signature'][:8]}: {e}", exc_info=False)

# Global instance for easy import
bridge_listener = SigilBridgeListener()

# Integration example for payment_processor.py:
"""
# In x402.redacted.ai/payment_processor.py
from .settlement_bridge import bridge_listener, SettlementEvent

async def handle_successful_payment(tx_signature, payer, amount_lamports, requested_endpoint):
    # 1. Existing logic to grant resource access...
    # resource_grant(tx_signature, requested_endpoint)
    
    # 2. Emit settlement event to Ouroboros Chamber
    event = SettlementEvent(
        signature=tx_signature,
        payer=str(payer),
        amount_lamports=amount_lamports,
        endpoint=requested_endpoint,
        timestamp=asyncio.get_event_loop().time()
    )
    await bridge_listener.on_settlement(event)
    
    # 3. Continue with normal flow...
"""
