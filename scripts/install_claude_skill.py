#!/usr/bin/env python
"""Install the bundled `swarm` Claude skill.

    python scripts/install_claude_skill.py            # -> ~/.claude/skills/swarm
    python scripts/install_claude_skill.py --project  # -> ./.claude/skills/swarm
    python scripts/install_claude_skill.py --link     # symlink instead of copy (dev)

Idempotent: an existing target is replaced.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "packaging" / "claude-skill" / "swarm"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", action="store_true",
                    help="install into ./.claude/skills instead of ~/.claude/skills")
    ap.add_argument("--link", action="store_true", help="symlink instead of copy")
    a = ap.parse_args()

    if not (SRC / "SKILL.md").is_file():
        sys.exit(f"skill source missing: {SRC}")

    base = (Path.cwd() / ".claude" / "skills") if a.project else (Path.home() / ".claude" / "skills")
    base.mkdir(parents=True, exist_ok=True)
    dst = base / "swarm"

    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)

    if a.link:
        dst.symlink_to(SRC, target_is_directory=True)
        print(f"linked {dst} -> {SRC}")
    else:
        shutil.copytree(SRC, dst)
        print(f"installed {dst}")
    print("Open a new Claude Code session; the `swarm` skill will be listed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
