#!/usr/bin/env python
"""Pretty roster via the swarm CLI, working whether or not the binary is on PATH."""
import shutil
import subprocess
import sys


def _cli(*args):
    exe = shutil.which("swarm")
    base = [exe] if exe else [sys.executable, "-m", "swarm_core.cli"]
    return subprocess.call(base + list(args))


if __name__ == "__main__":
    raise SystemExit(_cli("roster", *sys.argv[1:]))
