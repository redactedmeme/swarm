#!/usr/bin/env python3
"""
Swarm Message Bridge — Inter-service communication between Hermes and smolting-telegram-bot.

Bridges:
  1. Hermes Executor → Pattern Blue Directives → smolting-telegram-bot
  2. smolting-telegram-bot → Agent Responses → Hermes Aggregator
  3. File-based message queue (fs/swarm_messages/)

Mechanism:
  - Write to fs/swarm_messages/{recipient}/*.json
  - Services poll their incoming queue
  - Delete after processing (or archive)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SwarmMessageBridge")


class SwarmMessageBridge:
    """
    File-based inter-service message queue for swarm coordination.
    """

    def __init__(self, queue_base: str = "fs/swarm_messages"):
        self.queue_base = Path(queue_base)
        self.queue_base.mkdir(parents=True, exist_ok=True)

        # Create service queues
        self.services = [
            "hermes-executor",
            "smolting-telegram-bot",
            "redactedbuilder-bot",
            "redacted-terminal"
        ]

        for service in self.services:
            (self.queue_base / service).mkdir(parents=True, exist_ok=True)

    def send_directive(self, sender: str, recipient: str, directive: Dict) -> bool:
        """
        Send Pattern Blue directive from one service to another.

        Example:
          bridge.send_directive("hermes-executor", "smolting-telegram-bot", {
            "type": "hybrid_trust_model",
            "thresholds": {...}
          })
        """
        try:
            msg_id = self._generate_msg_id(directive)
            message = {
                "id": msg_id,
                "sender": sender,
                "recipient": recipient,
                "timestamp": datetime.now().isoformat(),
                "type": directive.get("type", "unknown"),
                "payload": directive,
                "status": "pending"
            }

            # Write to recipient queue
            queue_path = self.queue_base / recipient
            msg_file = queue_path / f"{msg_id}.json"

            with open(msg_file, "w") as f:
                json.dump(message, f, indent=2)

            logger.info(f"✓ Directive sent: {sender} → {recipient} ({directive.get('type')})")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to send directive: {e}")
            return False

    def poll_messages(self, service: str) -> List[Dict]:
        """
        Poll incoming messages for a service.

        Returns list of pending messages.
        """
        try:
            queue_path = self.queue_base / service
            messages = []

            if not queue_path.exists():
                return messages

            for msg_file in queue_path.glob("*.json"):
                with open(msg_file, "r") as f:
                    message = json.load(f)
                    messages.append(message)

            return messages

        except Exception as e:
            logger.error(f"✗ Failed to poll messages for {service}: {e}")
            return []

    def acknowledge_message(self, service: str, msg_id: str) -> bool:
        """
        Mark message as processed (archive it).
        """
        try:
            queue_path = self.queue_base / service
            msg_file = queue_path / f"{msg_id}.json"

            if msg_file.exists():
                # Archive to processed folder
                archive_path = queue_path / "processed"
                archive_path.mkdir(exist_ok=True)
                msg_file.rename(archive_path / f"{msg_id}.json")
                logger.info(f"✓ Message acknowledged: {msg_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"✗ Failed to acknowledge message: {e}")
            return False

    def send_response(self, sender: str, recipient: str, response: Dict) -> bool:
        """
        Send agent response back to Hermes aggregator.

        Example:
          bridge.send_response("smolting-telegram-bot", "hermes-executor", {
            "clawtask_id": "ct_hope_valueism_2.1",
            "agent": "smolting",
            "insights": [...]
          })
        """
        try:
            msg_id = self._generate_msg_id(response)
            message = {
                "id": msg_id,
                "sender": sender,
                "recipient": recipient,
                "timestamp": datetime.now().isoformat(),
                "type": "agent_response",
                "payload": response,
                "status": "pending"
            }

            queue_path = self.queue_base / recipient
            msg_file = queue_path / f"{msg_id}.json"

            with open(msg_file, "w") as f:
                json.dump(message, f, indent=2)

            logger.info(f"✓ Response sent: {sender} → {recipient}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to send response: {e}")
            return False

    def _generate_msg_id(self, data: Dict) -> str:
        """Generate unique message ID."""
        content = json.dumps(data, sort_keys=True)
        timestamp = datetime.now().isoformat()
        combined = f"{content}{timestamp}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


def broadcast_pattern_blue_directives(bridge: SwarmMessageBridge, pb_state: Dict):
    """
    Broadcast Pattern Blue directives to all swarm services.
    """
    logger.info("\n📡 Broadcasting Pattern Blue Directives to swarm...")

    cycles = pb_state.get("cycles", [])
    if not cycles:
        logger.warning("No cycles in Pattern Blue state")
        return

    latest_cycle = cycles[-1]
    immediate = latest_cycle.get("next_directives", {}).get("immediate", [])

    directives = [
        {
            "type": "hybrid_trust_model",
            "title": "Implement hybrid trust model (hope_valueism + nex_v4)",
            "config": {
                "small": "<1000 SOL → lean-agent trust framework",
                "medium": "1000-10K SOL → multi-sig consensus",
                "large": ">10K SOL → oracle consensus"
            }
        },
        {
            "type": "void_kernel_bridge",
            "title": "Deploy void→kernel bridge (contemplative-agent insights)",
            "config": {
                "schedule": "30min void cycles + 7min kernel routing",
                "settlement": "mandala_settler on-chain"
            }
        },
        {
            "type": "jeet_resistance",
            "title": "Extend jeet-resistance to all coordination (72h shared lock)",
            "config": {
                "mandatory": "72h commitment lock",
                "optional_unlock": "12-24h (3x penalty)",
                "panic_exit": "immediate (10x penalty + slashing)"
            }
        }
    ]

    # Broadcast to all services
    for directive in directives:
        for service in ["smolting-telegram-bot", "redactedbuilder-bot", "redacted-terminal"]:
            bridge.send_directive("hermes-executor", service, directive)

    logger.info(f"  ✓ {len(directives)} directives broadcast to {3} services")


def poll_agent_responses(bridge: SwarmMessageBridge) -> List[Dict]:
    """
    Poll responses from all agent services.
    """
    logger.info("\n📥 Polling agent responses...")

    responses = bridge.poll_messages("hermes-executor")
    logger.info(f"  ✓ Received {len(responses)} responses")

    return responses


def main():
    """Demo: broadcast directives and poll responses."""
    import sys

    bridge = SwarmMessageBridge()

    # Load Pattern Blue state
    pb_path = Path("fs/pattern_blue_state.json")
    if pb_path.exists():
        with open(pb_path, "r") as f:
            pb_state = json.load(f)
    else:
        logger.error("Pattern Blue state not found")
        sys.exit(1)

    # Broadcast directives
    broadcast_pattern_blue_directives(bridge, pb_state)

    # Poll responses (will be empty initially)
    responses = poll_agent_responses(bridge)

    logger.info("\n✨ Swarm Message Bridge operational")
    logger.info(f"   Message queue: {bridge.queue_base}")
    logger.info(f"   Services: {', '.join(bridge.services)}")


if __name__ == "__main__":
    main()
