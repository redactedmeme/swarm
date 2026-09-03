"""swarm-status — the swarm's only public read-only surface.

Reads `swarm:heartbeat:{agent}` from the mesh Redis and serves a deliberately thin,
deliberately boring view of who is alive. redacted.meme proxies this and renders it
as the MESH STATUS section.

What it will *never* expose: model or provider names, prompt or response content,
message counts, queue depths, token usage, exact timestamps, or any key not in
AGENT_LABELS. Age is reported as a coarse bucket rather than a number so the feed
cannot be used to fingerprint an agent's cadence.

    GET /api/swarm -> declared roster + coarse observed liveness (see below)
    GET /status    -> {"agents": [{"id","label","online","last_seen_bucket"}], "ts": ...}
                      unchanged, kept as an alias for redacted.meme's MESH STATUS
    GET /healthz   -> {"status": "ok", "redis": true|false}

`/api/swarm` fields come in two tiers, and the distinction is the whole safety
argument. *Declared* fields come from checked-in registries already rendered
publicly on redacted.meme, so republishing them costs nothing. *Observed* fields
come from mesh Redis and are coarsened to buckets and booleans — never numbers —
because cadence is fingerprintable. An observed number must never leak into a
declared field.

`state` (declared) and `online` (observed) are deliberately separate: that is
what makes `state="active", online=false` expressible, which is exactly the
alarm condition.

Env:
    REDIS_URL     redis://swarm-redis:6379/0
    PORT          8098
    ALLOW_ORIGIN  CORS origin, default https://redacted.meme
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web


from swarm_core import tokens
from swarm_core.swarm_heartbeat import (
    DOOR_KEY_PREFIX,
    HEARTBEAT_LOOKUP_KEYS,
    door_age,
    heartbeat_redis_key,
    parse_door_value,
    parse_heartbeat_value,
    pick_best_heartbeat,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("swarm-status")

REDIS_URL = os.environ.get("REDIS_URL", "redis://swarm-redis:6379/0")
PORT = int(os.environ.get("PORT", "8098"))
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN", "https://redacted.meme")
CACHE_TTL = float(os.environ.get("CACHE_TTL", "15"))

# The allow-list. An agent absent from here is absent from the public feed, even if
# it is writing heartbeats.
AGENT_LABELS: dict[str, str] = {
    "smolting": "smolting",
    "redacted-chan": "redacted-chan",
    "hermes": "hermes",
    "builder": "RedactedBuilder",
    "degen": "RedactedDegen",
    "govimprover": "RedactedGovImprover",
}


def bucket(age_s: float | None, present: bool) -> str:
    """Coarse last-seen bucket. Never an exact age."""
    if not present or age_s is None:
        return "no signal"
    if age_s < 60:
        return "just now"
    if age_s < 300:
        return "< 5 min ago"
    if age_s < 3600:
        return "< 1 hour ago"
    if age_s < 86400:
        return "< 1 day ago"
    return "over a day ago"


_cache: dict = {"ts": 0.0, "payload": None}
# /api/swarm caches per distinct query, same TTL.
_api_cache: dict[str, tuple[float, dict]] = {}


async def read_agents(redis_client) -> list[dict]:
    now = time.time()
    out = []
    for agent_id, label in AGENT_LABELS.items():
        candidates = []
        for key in HEARTBEAT_LOOKUP_KEYS.get(agent_id, [agent_id]):
            raw = await redis_client.get(heartbeat_redis_key(key))
            if raw is None:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            candidates.append(parse_heartbeat_value(raw, now))
        hb = pick_best_heartbeat(candidates)
        out.append({
            "id": agent_id,
            "label": label,
            "online": bool(hb.get("online")),
            "last_seen_bucket": bucket(hb.get("age_s"), bool(hb.get("present"))),
        })
    return out


async def status(request: web.Request) -> web.Response:
    now = time.time()
    if _cache["payload"] is not None and now - _cache["ts"] < CACHE_TTL:
        return _json(_cache["payload"])

    redis_client = request.app["redis"]
    try:
        agents = await read_agents(redis_client)
    except Exception as exc:  # noqa: BLE001 — a public endpoint must not 500 on Redis blips
        log.warning("heartbeat read failed: %s", exc)
        return _json({"agents": [], "ts": _now_iso()})

    payload = {"agents": agents, "ts": _now_iso()}
    _cache.update(ts=now, payload=payload)
    return _json(payload)


async def healthz(request: web.Request) -> web.Response:
    try:
        await request.app["redis"].ping()
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    return _json({"status": "ok", "redis": ok})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(payload: dict) -> web.Response:
    return web.json_response(payload, headers={
        "Access-Control-Allow-Origin": ALLOW_ORIGIN,
        "Cache-Control": "public, max-age=15",
    })



# ── /api/swarm ────────────────────────────────────────────────────────────────

REGISTRY_DIR = Path(__file__).resolve().parent
AGENTS_PATH = Path(os.environ.get(
    "AGENTS_JSON", REGISTRY_DIR.parent / "website" / "data" / "agents.json"))
OFFERS_PATH = Path(os.environ.get("OFFERS_JSON", REGISTRY_DIR / "offers.json"))

# Hash the settlement writer maintains: burned_total, settlements_24h,
# last_settlement_sig. Read-only here — this service never writes it.
TREASURY_KEY = os.environ.get("TREASURY_KEY", "swarm:treasury")
# Capped list of recent settlement records (newest first), written by
# swarm_core.x402.settle. Read-only here.
SETTLEMENTS_LOG_KEY = os.environ.get("SETTLEMENTS_LOG_KEY", "swarm:settlements:log")

NONPRIVILEGED = (
    "Read from mesh heartbeat keys and a checked-in registry. No credential, "
    "prompt, or message content is reachable through this endpoint."
)

TIER_ORDER = {"CORE": 0, "APEX": 1, "SPECIALIZED": 2}
VALID_STATES = ("active", "asleep", "retired")
SORT_FIELDS = ("tier", "id", "last_seen")


def _load_json(path: Path, key: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get(key, [])
    except Exception as exc:  # noqa: BLE001 — a missing registry must not stop the service
        log.warning("registry %s unreadable: %s", path, exc)
        return []


def _declared_agents(raw: list[dict]) -> list[dict]:
    """Declared roster, with children derived from parents so edges cannot drift."""
    children: dict[str, list[str]] = {}
    for a in raw:
        parent = (a.get("lineage") or {}).get("parent")
        if parent:
            children.setdefault(parent, []).append(a["id"])

    out = []
    for a in raw:
        state = a.get("state", "asleep")
        out.append({
            "id": a["id"],
            "name": a.get("name", a["id"]),
            "tier": a.get("tier", "SPECIALIZED"),
            "dimension": a.get("dimension"),
            "host": a.get("host"),
            "state": state if state in VALID_STATES else "asleep",
            "lineage": {
                "parent": (a.get("lineage") or {}).get("parent"),
                "children": sorted(children.get(a["id"], [])),
            },
        })
    return out


def _parse_query(q) -> dict:
    def multi(name: str, allowed: tuple) -> list[str]:
        vals = []
        for raw in q.getall(name, []):
            for part in raw.split(","):
                part = part.strip()
                if part in allowed and part not in vals:
                    vals.append(part)
        return vals

    try:
        limit = int(q.get("limit", "50"))
    except ValueError:
        limit = 50

    sort = q.get("sort", "tier")
    return {
        "q": (q.get("q") or "").strip() or None,
        "state": multi("state", VALID_STATES),
        "tier": multi("tier", tuple(TIER_ORDER)),
        "sort": sort if sort in SORT_FIELDS else "tier",
        "order": "desc" if q.get("order") == "desc" else "asc",
        "limit": max(1, min(200, limit)),
    }


def _matches(agent: dict, spec: dict) -> bool:
    if spec["state"] and agent["state"] not in spec["state"]:
        return False
    if spec["tier"] and agent["tier"] not in spec["tier"]:
        return False
    if spec["q"]:
        needle = spec["q"].lower()
        hay = " ".join(str(agent.get(k) or "") for k in ("id", "name", "dimension")).lower()
        if needle not in hay:
            return False
    return True


async def _observe(redis_client, agent_ids: list[str]) -> dict[str, dict]:
    """Heartbeats and doors for `agent_ids` in a couple of round-trips, not O(n) awaits."""
    now = time.time()
    alias_map = {aid: HEARTBEAT_LOOKUP_KEYS.get(aid, [aid]) for aid in agent_ids}
    flat = [(aid, alias) for aid, aliases in alias_map.items() for alias in aliases]

    beats: dict[str, list[dict]] = {}
    if flat:
        pipe = redis_client.pipeline()
        for _, alias in flat:
            pipe.get(heartbeat_redis_key(alias))
        for (aid, _), raw in zip(flat, await pipe.execute()):
            if raw is not None:
                beats.setdefault(aid, []).append(parse_heartbeat_value(raw, now))

    # One scan for every door key, then attribute each to its owning agent by alias.
    owner = {alias: aid for aid, aliases in alias_map.items() for alias in aliases}
    door_keys = [k async for k in redis_client.scan_iter(match=DOOR_KEY_PREFIX + "*")]
    doors: dict[str, dict[str, dict]] = {}
    if door_keys:
        pipe = redis_client.pipeline()
        for key in door_keys:
            pipe.get(key)
        for key, raw in zip(door_keys, await pipe.execute()):
            alias = key[len(DOOR_KEY_PREFIX):].split(":", 1)[0]
            aid = owner.get(alias)
            door = parse_door_value(raw, now) if aid else None
            if not door or not door["name"]:
                continue
            prior = doors.setdefault(aid, {}).get(door["name"])
            if prior is None or door_age(door) < door_age(prior):
                doors[aid][door["name"]] = door

    return {
        aid: {
            "hb": pick_best_heartbeat(beats.get(aid, [])),
            "doors": sorted(doors.get(aid, {}).values(), key=lambda d: d["name"]),
        }
        for aid in agent_ids
    }


def _blank_observation() -> dict:
    """What we report when Redis is unreachable: declared data, degraded observation."""
    return {"hb": parse_heartbeat_value(None), "doors": []}


def _priced_offers() -> list[dict]:
    """Declared offers, joined to the price sheet.

    `offers.json` stays the registry of *what exists and whether it is open* —
    that stays a declared, hand-maintained fact. Price comes from
    `swarm_core.tokens`, which is what the payment middleware actually charges,
    so the feed cannot advertise a price the endpoints do not honour.

    An offer with no matching price is published without one rather than
    dropped: a caller should still be able to see that it exists.
    """
    rows = _load_json(OFFERS_PATH, "offers")
    for row in rows:
        try:
            price = tokens.price_of(row["id"])
        except KeyError:
            continue
        row["price"] = {
            "amount": str(price),
            "asset": tokens.token_mint(),
            "decimals": tokens.TOKEN_DECIMALS,
            "base_units": str(tokens.to_base_units(price)),
        }
    return rows


async def _treasury(redis_client) -> dict:
    """Burn and settlement totals, as recorded by the settlement writer.

    Reports zeros rather than omitting the block when nothing has settled yet.
    A missing field reads as "not built"; an explicit zero reads as "built, and
    nobody has paid yet" — which is the honest state and the one that changes
    visibly the moment it does.

    Follows this module's existing discipline: never 500 a public endpoint on a
    Redis blip, and never publish a precise timestamp.
    """
    split = tokens.revenue_split()
    empty = {
        "burned_total": "0",
        "burn_accrued": "0",
        "settlements_24h": 0,
        "settlements_total": 0,
        "revenue_total": "0",
        "last_settlement_sig": None,
        "last_burn_sig": None,
        "runway_days": None,
        "split": {"burn": split.burn, "compute": split.compute, "rewards": split.rewards},
        "recent": [],
    }
    try:
        raw = await redis_client.hgetall(TREASURY_KEY)
    except Exception as exc:  # noqa: BLE001 — same rule as the observation read
        log.warning("treasury read failed: %s", exc)
        return empty
    if not raw:
        return empty

    def _num(field: str):
        v = raw.get(field)
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        # `burned_total` is executed-on-chain; `burn_accrued` is owed. Both are
        # on-chain-derivable, so neither widens the disclosure boundary. No
        # `*_at` field is surfaced — the module never publishes a precise time.
        "burned_total": raw.get("burned_total", "0"),
        "burn_accrued": raw.get("burn_accrued", "0"),
        "settlements_24h": int(raw.get("settlements_24h", 0) or 0),
        "settlements_total": int(raw.get("settlements_total", 0) or 0),
        "revenue_total": raw.get("revenue_total", "0"),
        "last_settlement_sig": raw.get("last_settlement_sig") or None,
        "last_burn_sig": raw.get("last_burn_sig") or None,
        "runway_days": _num("runway_days"),
        "split": {"burn": split.burn, "compute": split.compute, "rewards": split.rewards},
        "recent": await _settlements(redis_client),
    }


async def _settlements(redis_client, n: int = 20) -> list[dict]:
    """Recent settlements for the public feed, from `swarm:settlements:log`.

    Each row is projected to `{sig, endpoint, amount, burn, age}` — the payer
    wallet and the exact timestamp are dropped; the signature is public on any
    explorer anyway, and `age` is a coarse bucket. Unparseable rows are skipped
    and a Redis blip yields an empty list, never a 500.
    """
    try:
        rows = await redis_client.lrange(SETTLEMENTS_LOG_KEY, 0, n - 1)
    except Exception as exc:  # noqa: BLE001 — same rule as the observation read
        log.warning("settlements read failed: %s", exc)
        return []
    now = time.time()
    out: list[dict] = []
    for row in rows or []:
        try:
            e = json.loads(row)
            sig = e["sig"]
        except (TypeError, ValueError, KeyError):
            continue
        ts = e.get("ts")
        age_s = (now - ts) if isinstance(ts, (int, float)) else None
        out.append({
            "sig": str(sig)[:100],
            "endpoint": str(e.get("endpoint") or "")[:40],
            "amount": str(tokens.from_base_units(int(e.get("amount_raw", 0) or 0))),
            "burn": str(tokens.from_base_units(int(e.get("burn", 0) or 0))),
            "age": bucket(age_s, age_s is not None),
        })
    return out


async def api_swarm(request: web.Request) -> web.Response:
    now = time.time()
    spec = _parse_query(request.query)
    cache_key = json.dumps(spec, sort_keys=True)
    cached = _api_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL:
        return _json(cached[1])

    declared = _declared_agents(_load_json(AGENTS_PATH, "agents"))

    # The allow-list is the disclosure boundary. An agent absent from it is
    # absent from the feed — but it is still counted, so a caller can tell
    # "nothing matched" from "something matched and you are not being shown it".
    matched = [a for a in declared if _matches(a, spec)]
    visible = [a for a in matched if a["id"] in AGENT_LABELS]

    try:
        observed = await _observe(request.app["redis"], [a["id"] for a in visible])
    except Exception as exc:  # noqa: BLE001 — a public endpoint must not 500 on Redis blips
        log.warning("observation read failed: %s", exc)
        observed = {a["id"]: _blank_observation() for a in visible}

    rows = []
    for a in visible:
        obs = observed.get(a["id"]) or _blank_observation()
        hb = obs["hb"]
        rows.append({
            **a,
            "online": bool(hb.get("online")),
            "last_seen_bucket": bucket(hb.get("age_s"), bool(hb.get("present"))),
            "doors": [
                {
                    "name": d["name"],
                    "kind": d["kind"],
                    "open": d["open"],
                    "checked_bucket": bucket(d["age_s"], True),
                }
                for d in obs["doors"]
            ],
        })

    reverse = spec["order"] == "desc"
    if spec["sort"] == "id":
        rows.sort(key=lambda r: r["id"], reverse=reverse)
    elif spec["sort"] == "last_seen":
        rows.sort(key=lambda r: (0 if r["online"] else 1, r["id"]), reverse=reverse)
    else:
        rows.sort(key=lambda r: (TIER_ORDER.get(r["tier"], 99), r["id"]), reverse=reverse)

    shown = rows[: spec["limit"]]
    states = [a["state"] for a in declared]
    payload = {
        "at": _now_iso(),
        "nonprivileged": NONPRIVILEGED,
        "query": {
            **spec,
            "total": len(matched),
            "shown": len(shown),
            "hidden": len(matched) - len(shown),
        },
        "counts": {
            "declared": len(declared),
            "active": states.count("active"),
            "asleep": states.count("asleep"),
            "retired": states.count("retired"),
            "doors_open": sum(1 for r in shown for d in r["doors"] if d["open"]),
        },
        "agents": shown,
        "offers": _priced_offers(),
        "treasury": await _treasury(request.app["redis"]),
    }

    _api_cache[cache_key] = (now, payload)
    return _json(payload)

async def make_app() -> web.Application:
    import redis.asyncio as aioredis

    app = web.Application()
    app["redis"] = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.router.add_get("/api/swarm", api_swarm)
    app.router.add_get("/status", status)
    app.router.add_get("/healthz", healthz)

    async def close_redis(app_):
        await app_["redis"].aclose()

    app.on_cleanup.append(close_redis)
    return app


if __name__ == "__main__":
    log.info("swarm-status on :%s — redis=%s allow-origin=%s", PORT, REDIS_URL, ALLOW_ORIGIN)
    web.run_app(asyncio.get_event_loop().run_until_complete(make_app()), port=PORT, print=None)
