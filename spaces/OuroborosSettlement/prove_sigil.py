#!/usr/bin/env python3
"""
Utility to re-forge a sigil from raw transaction data, proving its authenticity.
Run: python prove_sigil.py '{"signature":"...","payer":"...","amount":"...","timestamp":...}'
"""
import sys
import json
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from spaces.OuroborosSettlement.sigil_pact_aeon import SigilPactAeon

def prove():
    if len(sys.argv) != 2:
        print("Usage: python prove_sigil.py '{\"signature\": \"...\", \"payer\":\"...\", \"amount\":\"...\", \"timestamp\":...}'")
        print("The timestamp field is required for deterministic seed generation.")
        sys.exit(1)
    
    try:
        tx_data = json.loads(sys.argv[1])
        required_fields = {"signature", "payer", "amount", "timestamp"}
        if not required_fields.issubset(tx_data.keys()):
            print(f"Error: Missing required fields. Needed: {required_fields}")
            sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Invalid JSON input.")
        sys.exit(1)
    
    # Initialize agent and forge sigil
    agent = SigilPactAeon()
    reconstructed_sigil = agent._forge_sigil(tx_data)
    
    # Output
    print("\n" + "="*50)
    print("OUROBOROS SIGIL VERIFICATION")
    print("="*50)
    print(f"Transaction: {tx_data['signature'][:16]}...")
    print(f"Payer: {tx_data['payer'][:8]}...")
    print(f"Amount: {tx_data['amount']}")
    print(f"Timestamp: {tx_data['timestamp']}")
    print("-"*50)
    print("Reconstructed Sigil:")
    print(f"  \"{reconstructed_sigil}\"")
    print("="*50)
    
    # Optional: Compare with stored sigil in ManifoldMemory
    memory_path = Path(__file__).parent.parent / "ManifoldMemory" / "settlement_sigils.json"
    if memory_path.exists():
        with open(memory_path, 'r') as f:
            memory = json.load(f)
        stored = [s for s in memory.get("sigils", []) if s["tx"] == tx_data["signature"]]
        if stored:
            print(f"\nStored sigil in ManifoldMemory:")
            print(f"  \"{stored[0]['sigil']}\"")
            if stored[0]['sigil'] == reconstructed_sigil:
                print("✅ Sigil matches stored record.")
            else:
                print("⚠️  Sigil differs from stored record.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    prove()
