# smolting-telegram-bot/multisig_signer.py
"""
Multisig countersigning for redactedintern.

When RedactedBuilder requests a 2-of-2 countersignature via SwarmInbox,
this module signs the raw Solana transaction message bytes using
redactedintern's ed25519 private key (SOLANA_PRIVATE_KEY).

No solders required — uses the `cryptography` library (already a transitive
dependency of python-telegram-bot) for pure-Python ed25519 signing.

Solana transaction signing is plain ed25519 over the raw serialised Message
bytes. This output is wire-compatible with any Solana validator.
"""

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

INTERN_PUBKEY  = "FaZMc2NXbMFiiaFuvzBJtrS66hM3kaedKXEdxFZNPQ9c"
BUILDER_PUBKEY = "H4QKqLX3jdFTPAzgwFVGbytnbSGkZCcFQqGxVLR53pn"


def _load_seed() -> Optional[bytes]:
    """
    Load intern's ed25519 private key seed (first 32 bytes of the keypair).
    Accepts base58-encoded 64-byte keypair (standard Solana/Phantom export).
    Returns 32-byte seed, or None if not configured.
    """
    raw = os.environ.get("SOLANA_PRIVATE_KEY", "").strip()
    if not raw:
        logger.warning("[multisig] SOLANA_PRIVATE_KEY not set — cannot countersign")
        return None

    try:
        from wallet import _b58decode
        decoded = _b58decode(raw)
        if len(decoded) == 64:
            return decoded[:32]
        elif len(decoded) == 32:
            return decoded
        else:
            logger.error(f"[multisig] Unexpected key length: {len(decoded)} bytes")
            return None
    except Exception as e:
        logger.error(f"[multisig] Failed to load keypair: {e}")
        return None


def sign_tx_message(tx_message_b64: str) -> Optional[str]:
    """
    Sign a Solana transaction message with redactedintern's private key.

    Parameters
    ----------
    tx_message_b64 : base64-encoded serialised Solana Message bytes
                     (produced by builder_core.build_countersign_request)

    Returns
    -------
    base64-encoded 64-byte ed25519 signature, or None on failure.
    """
    seed = _load_seed()
    if seed is None:
        return None

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        priv      = Ed25519PrivateKey.from_private_bytes(seed)
        msg_bytes = base64.b64decode(tx_message_b64)
        sig       = priv.sign(msg_bytes)   # 64-byte ed25519 signature

        sig_b64 = base64.b64encode(sig).decode()
        logger.info(f"[multisig] Countersigned tx message ({len(msg_bytes)} bytes)")
        return sig_b64

    except Exception as e:
        logger.error(f"[multisig] sign_tx_message error: {e}")
        return None


def get_intern_pubkey() -> str:
    """Return intern's hardcoded public address."""
    return INTERN_PUBKEY
