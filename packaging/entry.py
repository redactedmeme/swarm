"""Frozen-binary entrypoint for the `swarm` CLI (PyInstaller analysis root)."""
from swarm_core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
