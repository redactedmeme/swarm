"""``swarm`` - one entrypoint for driving and observing the REDACTED swarm.

Every sub-command is a thin wrapper over code that already exists in
``swarm_core`` / ``swarm_tg``. Nothing here is a new subsystem; it is the
console face of the mesh, wallets, reserve and committee.

    swarm roster                       agent registry (tier / tools / wallet)
    swarm status                       Phi + kernel snapshot
    swarm wallets list|address|balance per-agent Solana wallets
    swarm reserve status|refuel        SOL auto-refuel (dry-run unless RESERVE_EXECUTE)
    swarm delegate --from --to --task  put a task_request on the bus, wait for the result
    swarm mesh tail|send               inbox tail / hand-send
    swarm committee "<proposal>"       Sevenfold deliberation
    swarm phi                          raw phi_compute JSON
    swarm skill install [--project]    install the bundled Claude skill
    swarm terminal                     NERV cloud terminal REPL
    swarm daemon                       inbox poll + reserve loop (standalone operator)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


# ── roster / status / phi ─────────────────────────────────────────────────────

def _cmd_roster(args) -> int:
    from swarm_core import agent_registry as reg

    entries = reg.index()
    if args.json:
        _print_json(entries)
        return 0
    tier = None
    for e in entries:
        if e["tier"] != tier:
            tier = e["tier"]
            print(f"\n[{tier}]")
        w = f"  wallet={e['wallet_address'][:8]}…" if e.get("wallet_address") else ""
        tools = f" ({e['tool_count']} tools)" if e["tool_count"] else ""
        print(f"  {e['name']:<34} {e['description'][:48]}{tools}{w}")
    print(f"\n{len(entries)} agents")
    return 0


def _cmd_phi(args) -> int:
    from swarm_core.phi_compute import compute_phi

    _print_json(compute_phi())
    return 0


def _cmd_status(args) -> int:
    from swarm_core.phi_compute import compute_phi

    p = compute_phi()
    print("REDACTED swarm status")
    print(f"  phi        : {p.get('phi')}")
    print(f"  tiles      : {p.get('living')}/{p.get('tiles')} living (vitality {p.get('vitality')})")
    print(f"  dna_gen    : {p.get('dna_gen')}")
    print(f"  kernel     : {'loaded' if p.get('state_loaded') else 'fresh'}")
    try:
        from swarm_core.solana import keystore

        n = len(keystore.all_addresses())
        print(f"  wallets    : {n} agent wallet(s) in keystore")
    except Exception:
        pass
    return 0


# ── wallets ───────────────────────────────────────────────────────────────────

def _cmd_wallets(args) -> int:
    from swarm_core.solana import keystore, wallets

    if args.wallet_cmd == "list":
        addrs = keystore.all_addresses()
        if not addrs:
            print("no wallets - run: swarm wallets generate  (needs SWARM_WALLET_KEK)")
            return 1
        for a, addr in sorted(addrs.items()):
            print(f"  {a:<20} {addr}")
        return 0
    if args.wallet_cmd == "generate":
        from swarm_core.solana import LIVE_WALLET_AGENTS

        names = args.agents or list(LIVE_WALLET_AGENTS)
        made = keystore.generate(names, overwrite=args.overwrite)
        _print_json(made)
        return 0
    if args.wallet_cmd == "address":
        addr = keystore.get_address(args.agent)
        print(addr or f"(no wallet for {args.agent})")
        return 0 if addr else 1
    if args.wallet_cmd == "balance":
        rows = [asyncio.run(wallets.manifest_async([args.agent]))] if args.agent else [wallets.manifest()]
        _print_json(rows[0] if args.agent else rows[0])
        return 0
    return 2


# ── reserve ───────────────────────────────────────────────────────────────────

def _cmd_reserve(args) -> int:
    from swarm_core.solana import reserve

    cfg = reserve._cfg()
    if args.reserve_cmd == "status":
        _print_json({k: v for k, v in cfg.items()})
        return 0
    if args.reserve_cmd == "refuel":
        url = os.getenv("REDIS_URL")
        if not url:
            print("REDIS_URL not set", file=sys.stderr)
            return 1
        import redis.asyncio as aioredis

        async def _go():
            r = aioredis.from_url(url, decode_responses=True)
            try:
                if args.agent:
                    return [await reserve.check_and_refuel_agent(r, args.agent)]
                return await reserve.refuel_all_low_agents(r)
            finally:
                await r.aclose()

        _print_json(asyncio.run(_go()))
        return 0
    return 2


# ── mesh / delegate ───────────────────────────────────────────────────────────

def _cmd_delegate(args) -> int:
    from swarm_core.security import inbox

    payload = {"task_type": args.task, "instruction": args.instruction or ""}
    if args.data:
        payload.update(json.loads(args.data))
    mid = inbox.write_message(getattr(args, "from"), args.to, "task_request", payload)
    print(f"sent {mid} -> {args.to}")
    if args.wait:
        import time

        deadline = time.time() + args.wait
        while time.time() < deadline:
            for m in inbox.read_results(getattr(args, "from")):
                if m.get("reply_to") == mid or m.get("id") == mid:
                    _print_json(m.get("result") or m.get("error"))
                    return 0
            time.sleep(2)
        print("(timed out waiting for result)")
        return 1
    return 0


def _cmd_mesh(args) -> int:
    from swarm_core.security import inbox

    if args.mesh_cmd == "tail":
        for m in inbox.recent_messages(limit=args.n, for_agent=args.agent):
            print(f"{m.get('ts','')}  {m.get('from'):>14} -> {m.get('to'):<14} "
                  f"{m.get('type'):<16} {m.get('status')}")
        return 0
    if args.mesh_cmd == "send":
        mid = inbox.write_message(getattr(args, "from"), args.to, args.type,
                                  json.loads(args.data) if args.data else {})
        print(mid)
        return 0
    return 2


def _cmd_committee(args) -> int:
    from swarm_core.engine.moe_committee import deliberate

    print(deliberate(args.proposal))
    return 0


# ── skill / terminal / daemon ─────────────────────────────────────────────────

def _cmd_skill(args) -> int:
    from swarm_core.paths import repo_root

    installer = repo_root() / "scripts" / "install_claude_skill.py"
    if not installer.is_file():
        print(f"installer not found: {installer}", file=sys.stderr)
        return 1
    argv = [sys.executable, str(installer)]
    if args.project:
        argv.append("--project")
    if args.link:
        argv.append("--link")
    import subprocess

    return subprocess.call(argv)


def _cmd_terminal(args) -> int:
    from swarm_core.redacted_terminal_cloud import main as _t

    return _t() or 0


def _cmd_daemon(args) -> int:
    url = os.getenv("REDIS_URL")
    if not url:
        print("REDIS_URL not set", file=sys.stderr)
        return 1
    import redis.asyncio as aioredis

    from swarm_core.solana import reserve

    async def _go():
        r = aioredis.from_url(url, decode_responses=True)
        print("swarm daemon: reserve loop only (agent processes run as services)")
        try:
            await reserve.run_reserve_loop(r)
        finally:
            await r.aclose()

    try:
        asyncio.run(_go())
    except KeyboardInterrupt:
        pass
    return 0


# ── parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="swarm", description="REDACTED AI swarm control")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("roster", help="list agents")
    r.add_argument("--json", action="store_true")
    r.set_defaults(fn=_cmd_roster)

    s = sub.add_parser("status", help="phi + kernel snapshot")
    s.set_defaults(fn=_cmd_status)

    ph = sub.add_parser("phi", help="raw phi_compute JSON")
    ph.set_defaults(fn=_cmd_phi)

    w = sub.add_parser("wallets", help="per-agent Solana wallets")
    ws = w.add_subparsers(dest="wallet_cmd", required=True)
    ws.add_parser("list")
    g = ws.add_parser("generate")
    g.add_argument("agents", nargs="*")
    g.add_argument("--overwrite", action="store_true")
    wa = ws.add_parser("address")
    wa.add_argument("agent")
    wb = ws.add_parser("balance")
    wb.add_argument("agent", nargs="?")
    w.set_defaults(fn=_cmd_wallets)

    rs = sub.add_parser("reserve", help="SOL auto-refuel")
    rss = rs.add_subparsers(dest="reserve_cmd", required=True)
    rss.add_parser("status")
    rr = rss.add_parser("refuel")
    rr.add_argument("agent", nargs="?")
    rs.set_defaults(fn=_cmd_reserve)

    d = sub.add_parser("delegate", help="send a task_request and (optionally) wait")
    d.add_argument("--from", required=True)
    d.add_argument("--to", required=True)
    d.add_argument("--task", required=True)
    d.add_argument("--instruction", "--inst")
    d.add_argument("--data", help="extra payload as JSON")
    d.add_argument("--wait", type=float, default=0, metavar="SECONDS")
    d.set_defaults(fn=_cmd_delegate)

    m = sub.add_parser("mesh", help="inbox tail / send")
    ms = m.add_subparsers(dest="mesh_cmd", required=True)
    mt = ms.add_parser("tail")
    mt.add_argument("-n", type=int, default=20)
    mt.add_argument("--agent")
    msend = ms.add_parser("send")
    msend.add_argument("--from", required=True)
    msend.add_argument("--to", required=True)
    msend.add_argument("--type", default="status_update")
    msend.add_argument("--data")
    m.set_defaults(fn=_cmd_mesh)

    c = sub.add_parser("committee", help="Sevenfold deliberation")
    c.add_argument("proposal")
    c.set_defaults(fn=_cmd_committee)

    sk = sub.add_parser("skill", help="manage the bundled Claude skill")
    sks = sk.add_subparsers(dest="skill_cmd", required=True)
    ski = sks.add_parser("install")
    ski.add_argument("--project", action="store_true", help="install into ./.claude/skills")
    ski.add_argument("--link", action="store_true", help="symlink instead of copy")
    sk.set_defaults(fn=_cmd_skill)

    sub.add_parser("terminal", help="NERV cloud terminal REPL").set_defaults(fn=_cmd_terminal)
    sub.add_parser("daemon", help="reserve loop (standalone operator)").set_defaults(fn=_cmd_daemon)
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # keep the CLI's failure surface small + readable
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
