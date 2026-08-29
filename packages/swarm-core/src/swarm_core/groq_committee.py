# python/groq_committee.py
#
# Back-compat CLI shim. Live LLM deliberation now lives in core/moe_committee.py
# (reconciled: 7 voices — previously this script hardcoded 8, adding DharmaNode
# as an 8th voice with no character file backing it — at a 71% weighted
# supermajority, which is unchanged here).
#
# Kept as a runnable script so existing subprocess call sites (e.g.
# smolting-telegram-bot/main.py invoking `python python/groq_committee.py
# "<proposal>"`) keep working unchanged.

import sys
from pathlib import Path


from swarm_core.engine.moe_committee import run_committee  # noqa: E402

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args:
        print('Usage: python python/groq_committee.py "proposal text"')
        sys.exit(0)
    sys.exit(run_committee(" ".join(args).strip()))
