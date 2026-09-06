#!/usr/bin/env python3
"""Scan for credential-shaped material, using the repo's own leakscan rules.

One implementation, three entry points:

    secret_scan.py --staged        the staged diff        (.githooks/pre-commit)
    secret_scan.py --range A..B    the diff of a range    (CI, pull requests)
    secret_scan.py --tree          every tracked file     (CI, pushes)

Only `block`-severity rules fail; `redact`/`warn` are advisory and not reported.
leakscan is loaded straight from the working tree so this runs with no install.

Exemptions, for deliberate synthetic fixtures only:
  * a `leakscan: allow` comment on the offending line or the line above it
  * files whose name marks them as documentation of variable NAMES
    (`.env.example`, `config.example.env`, anything matching *.example*)
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRAGMA = "leakscan: allow"
EXEMPT_PATHS = ("*.example", "*.example.*", "*.*.example", "*example.env", ".env.example")


def _load_leakscan():
    src = ROOT / "packages/swarm-core/src/swarm_core/security/leakscan.py"
    if not src.is_file():
        sys.exit("secret_scan: leakscan.py not found — is this a full checkout?")
    spec = importlib.util.spec_from_file_location("_leakscan_scan", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolves via sys.modules
    spec.loader.exec_module(mod)
    return mod


leakscan = _load_leakscan()


def _exempt_path(path: str) -> bool:
    name = Path(path).name
    return any(fnmatch.fnmatch(name, pat) for pat in EXEMPT_PATHS)


def _blocking(line: str):
    return [m for m in leakscan.scan(line) if m.severity == "block"]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, errors="replace", cwd=ROOT
    ).stdout


def scan_diff(diff_args: list[str]) -> list[tuple[str, int, object]]:
    """Scan only the ADDED lines of a diff."""
    diff = _git("diff", "--unified=0", "--no-color", "--diff-filter=ACMR", *diff_args)
    found, path, lineno, prev = [], "?", 0, ""
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            path, lineno, prev = raw[6:], 0, ""
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno, prev = (int(m.group(1)) - 1 if m else 0), ""
        elif raw.startswith("+") and not raw.startswith("+++"):
            lineno += 1
            line = raw[1:]
            if not _exempt_path(path) and PRAGMA not in line and PRAGMA not in prev:
                found += [(path, lineno, m) for m in _blocking(line)]
            prev = line
    return found


def scan_tree() -> list[tuple[str, int, object]]:
    found = []
    for f in _git("ls-files").split("\n"):
        if not f or _exempt_path(f):
            continue
        fp = ROOT / f
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            continue
        prev = ""
        for n, line in enumerate(text.splitlines(), 1):
            if PRAGMA not in line and PRAGMA not in prev:
                found += [(f, n, m) for m in _blocking(line)]
            prev = line
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--tree", action="store_true")
    g.add_argument("--range", metavar="A..B")
    args = ap.parse_args()

    if args.staged:
        found, what = scan_diff(["--cached"]), "the staged changes"
    elif args.range:
        found, what = scan_diff([args.range]), f"the diff {args.range}"
    else:
        found, what = scan_tree(), "the tracked tree"

    if not found:
        print(f"secret_scan: no credential-shaped material in {what}.")
        return 0

    print(f"\nsecret_scan: credential-shaped material in {what}.\n", file=sys.stderr)
    for path, lineno, m in found:
        print(f"  {path}:{lineno}  [{m.rule}]  {m.preview}", file=sys.stderr)
    print(
        "\nIf this is a synthetic fixture, append a `leakscan: allow` comment.\n"
        "If it is real, do NOT commit it — rotate the credential first.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
