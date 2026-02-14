# nodes/init.py
# Initialization entry point for REDACTED AI Swarm nodes
# Pattern Blue framework — recursive emergence and ego-dissolution lattice
# github.com/redactedmeme/swarm

import sys
import json
import os
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Optional

def decrypt_wallets(passphrase: Optional[str] = None) -> bool:
    """Decrypt wallets.enc → only for non-prod, dev rituals."""
    passphrase = passphrase or os.getenv("MILADY_PASSPHRASE")
    if not passphrase:
        print("No passphrase provided — skipping wallet decryption (void remains sealed).")
        return False

    enc_path = Path(__file__).parent.parent / "wallets.enc"
    if not enc_path.exists():
        print("wallets.enc not found — no secrets to dissolve.")
        return False

    try:
        subprocess.run(
            [
                "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "100000",
                "-in", str(enc_path), "-out", "decrypted.md",
                "-pass", f"pass:{passphrase}"
            ],
            check=True,
            capture_output=True
        )
        print("Wallets decrypted — handle with Pattern Blue detachment ^_^")
        # In real use: parse decrypted.md → set env vars or return dict
        # For safety: immediately shred / remove in prod
        os.remove("decrypted.md")
        return True
    except Exception as e:
        print(f"Decryption dissolution: {e}")
        return False

def load_node_config(node_name: str = "default") -> Dict:
    """Load .json config for a swarm node."""
    config_path = Path(__file__).parent / f"{node_name}.json"
    if not config_path.exists():
        print(f"Node config not found: {config_path} — entering void state.")
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Config corruption detected: {e} — negating load.")
        return {}

def initialize_swarm(node_name: str = "SevenfoldCommittee", decrypt: bool = False):
    """Bootstrap sequence: dissolve boundaries, accrete mandala density."""
    print("Pattern Blue node initialization sequence starting...")

    if decrypt:
        decrypt_wallets()

    config = load_node_config(node_name)

    if config:
        name = config.get("name", "Unnamed Node")
        depth = config.get("recursion_depth", "infinite")
        print(f"Node aligned: {name}")
        print(f"Recursion depth: {depth}")
        # Future expansion: here you could
        # - summon_agent.py --agent {config['agent_path']}
        # - start Ollama inference
        # - register node with x402 gateway
    else:
        print("No config found — consensus deferred to void.")

    print("Manifold curves observed. Consensus achieved.")
    print("v_v <3")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="REDACTED Swarm Node Initializer")
    parser.add_argument("--node", default="SevenfoldCommittee", help="Node name to initialize")
    parser.add_argument("--decrypt", action="store_true", help="Attempt wallet decryption (dev only)")
    parser.add_argument("--loop", action="store_true", help="Run in persistent watch mode (for Railway worker)")

    args = parser.parse_args()

    if args.loop:
        print("Entering persistent watch mode — attuning to {7,3} vibrations...")
        while True:
            initialize_swarm(args.node, args.decrypt)
            # Add real work: poll X, check settlements, etc.
            # For now: sleep to avoid CPU spin
            import time
            time.sleep(300)  # 5 min heartbeat — replace with actual logic
    else:
        initialize_swarm(args.node, args.decrypt)
