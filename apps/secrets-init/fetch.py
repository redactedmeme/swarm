"""secrets-init — populate a tmpfs secrets file at container start (IronClaw
control 2).

Run this as an init step (or a one-shot sidecar sharing a tmpfs volume) before
the agent process. It resolves each name in the manifest from Vaultwarden and
writes ``SWARM_SECRETS_FILE`` as ``KEY=VALUE`` lines, mode 0600. The agent then
calls ``swarm_core.security.secrets.get_secret(...)`` instead of ``os.getenv``
and never carries the raw values in its own environment or image.

Config (env):
    SWARM_SECRETS_FILE        output path (default /run/secrets/swarm.env)
    SECRETS_MANIFEST          comma-separated secret names, OR
    SECRETS_MANIFEST_FILE     path to a file with one name per line
    SECRETS_BACKEND           "bw" (default) | "env" (passthrough, for dev)
    BW_SESSION                Bitwarden/Vaultwarden CLI session (backend=bw)
    SECRETS_STRICT            "1" → exit non-zero if any secret is missing

Values are never logged.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

OUT = os.getenv("SWARM_SECRETS_FILE", "/run/secrets/swarm.env")
BACKEND = os.getenv("SECRETS_BACKEND", "bw").lower()
STRICT = os.getenv("SECRETS_STRICT", "0") == "1"


def _manifest() -> list[str]:
    names: list[str] = []
    inline = os.getenv("SECRETS_MANIFEST", "")
    if inline:
        names += [n.strip() for n in inline.replace(";", ",").split(",") if n.strip()]
    path = os.getenv("SECRETS_MANIFEST_FILE", "")
    if path and Path(path).is_file():
        names += [ln.strip() for ln in Path(path).read_text("utf-8").splitlines()
                  if ln.strip() and not ln.startswith("#")]
    # de-dup, keep order
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _resolve_bw(name: str) -> str | None:
    try:
        r = subprocess.run(["bw", "get", "password", name], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _resolve_env(name: str) -> str | None:
    return os.getenv(name)


_RESOLVERS = {"bw": _resolve_bw, "env": _resolve_env}


def main() -> int:
    names = _manifest()
    if not names:
        print("secrets-init: empty manifest, nothing to do")
        return 0
    resolve = _RESOLVERS.get(BACKEND, _resolve_bw)

    out_path = Path(OUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    missing: list[str] = []
    for name in names:
        val = resolve(name)
        if val is None:
            missing.append(name)
            continue
        lines.append(f"{name}={val}")

    tmp = out_path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(out_path)

    print(f"secrets-init: wrote {len(lines)}/{len(names)} secrets to {OUT}")
    if missing:
        print(f"secrets-init: MISSING {len(missing)}: {', '.join(missing)}", file=sys.stderr)
        if STRICT:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
