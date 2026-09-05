"""Token identity, the x402 price sheet, and holder-gate thresholds.

Before this module the project mint was written out by hand in eighteen places
across seven services, and two of them (`apps/arb-keeper/config.py`,
`apps/dashboard/serve.py`) still pointed at the *legacy* mint while everything
else pointed at the current one. Nothing reconciled them, so "the token" meant
different things depending on which service you asked.

Everything that needs to know what the token is, what a call costs, or what a
wallet must hold asks here. Like `swarm_core.paths`, every value honours an
environment variable first so a container — or a future migration — can move
the anchor without a code change.

Prices are denominated in **whole $REDACTED**, not base units. Call
`to_base_units()` at the RPC boundary; on-chain amounts are integers and
floating-point token math is how rounding bugs get minted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

# ── Identity ────────────────────────────────────────────────────────────────

_CURRENT_MINT = "9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump"
_LEGACY_MINT = "9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM"

#: SPL tokens on pump.fun launch with 6 decimals. Override only if the mint moves.
TOKEN_DECIMALS = int(os.getenv("PROJECT_TOKEN_DECIMALS", "6"))

#: The canonical burn address. Solana has no burn *instruction* for a plain
#: transfer, so value is retired by sending it to the system incinerator, which
#: no one holds the key to. Publicly checkable on any explorer.
INCINERATOR = "1nc1nerator11111111111111111111111111111111"


def token_mint() -> str:
    """The project mint every service should transact against.

    `PROJECT_TOKEN_MINT` wins when set — the name already used by `.env.example`
    and the refinery compose files, so existing deployments keep working.
    """
    return os.getenv("PROJECT_TOKEN_MINT") or os.getenv("TOKEN_MINT") or _CURRENT_MINT


def legacy_token_mint() -> str:
    """The superseded V1 mint.

    Only the dashboard has a legitimate reason to reference this — it charts
    both curves. Nothing should *price* anything in it.
    """
    return os.getenv("LEGACY_TOKEN_MINT") or _LEGACY_MINT


def treasury_address() -> str:
    """Wallet that x402 payments must be sent to.

    Deliberately has no default: an unset treasury must fail loudly at startup
    rather than silently verifying payments against an empty string, which
    would accept any transaction at all.
    """
    addr = os.getenv("SWARM_TREASURY_ADDRESS", "").strip()
    if not addr:
        raise RuntimeError(
            "SWARM_TREASURY_ADDRESS is unset. Payment verification cannot run "
            "without a payTo address to check against."
        )
    return addr


def burn_address() -> str:
    """Where the burn slice goes. Defaults to the system incinerator."""
    return os.getenv("SWARM_BURN_ADDRESS", "").strip() or INCINERATOR


# ── Base-unit conversion ────────────────────────────────────────────────────


def to_base_units(amount: int | str | Decimal) -> int:
    """Whole tokens → integer base units, for RPC and on-chain comparison."""
    return int(Decimal(str(amount)) * (10 ** TOKEN_DECIMALS))


def from_base_units(raw: int) -> Decimal:
    """Integer base units → whole tokens, for display."""
    return Decimal(raw) / (10 ** TOKEN_DECIMALS)


# ── Revenue split ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RevenueSplit:
    """How a verified payment is divided. Must sum to 100.

    `compute` is *spent*, not accrued — it buys the swarm's own LLM credits.
    It is capped by runway (see `COMPUTE_RUNWAY_CAP_DAYS`): once the treasury
    holds more than that many days of inference, the overflow rolls into the
    burn instead of accumulating. A treasury that grows without bound is just
    an unaccountable pile; a capped one is an operating budget.
    """

    burn: int = 50
    compute: int = 30
    rewards: int = 20

    def __post_init__(self) -> None:
        total = self.burn + self.compute + self.rewards
        if total != 100:
            raise ValueError(f"revenue split must sum to 100, got {total}")


def revenue_split() -> RevenueSplit:
    return RevenueSplit(
        burn=int(os.getenv("SPLIT_BURN_PCT", "50")),
        compute=int(os.getenv("SPLIT_COMPUTE_PCT", "30")),
        rewards=int(os.getenv("SPLIT_REWARDS_PCT", "20")),
    )


#: Treasury stops taking its slice past this much inference runway; the
#: remainder is burned. Keeps the compute budget honest.
COMPUTE_RUNWAY_CAP_DAYS = int(os.getenv("COMPUTE_RUNWAY_CAP_DAYS", "90"))


# ── Price sheet ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Offer:
    """One sellable swarm endpoint.

    `agent` and `kind` match the shape `apps/status/app.py` already publishes in
    its `offers` array, so the status feed can render this table directly
    instead of maintaining a parallel copy.
    """

    id: str
    agent: str
    price: int  # whole $REDACTED
    summary: str
    kind: str = "x402"


#: Opening prices. Tuned against a ~$8.3k market cap: every call should cost
#: cents, because the point is to be used, not to extract.
PRICE_SHEET: tuple[Offer, ...] = (
    Offer(
        id="refine",
        agent="refinery",
        price=1_000,
        summary="Semantic search across the swarm's ingested signal corpus.",
    ),
    Offer(
        id="committee",
        agent="sevenfold-committee",
        price=5_000,
        summary="Deterministic seven-voice weighted vote, 71% supermajority.",
    ),
    Offer(
        id="deliberate",
        agent="sevenfold-committee",
        price=25_000,
        summary="Live LLM deliberation across all seven committee voices.",
    ),
    Offer(
        id="beam",
        agent="hermes",
        price=25_000,
        summary="BEAM-SCoT parallel reasoning, beam width 4.",
    ),
)

_BY_ID = {offer.id: offer for offer in PRICE_SHEET}


def offer(offer_id: str) -> Offer:
    """Look up one offer, raising on an unknown id rather than returning None.

    Callers use this to price a request; a silent None would price it at zero.
    """
    try:
        return _BY_ID[offer_id]
    except KeyError:
        raise KeyError(
            f"unknown offer {offer_id!r}; known offers: {sorted(_BY_ID)}"
        ) from None


def price_of(offer_id: str) -> int:
    """Price in whole $REDACTED. Env override per offer: `PRICE_<ID>`."""
    override = os.getenv(f"PRICE_{offer_id.upper()}", "").strip()
    return int(override) if override else offer(offer_id).price


# ── Credits ─────────────────────────────────────────────────────────────────

#: $REDACTED charged per 1k LLM tokens through the proxy. The proxy already
#: computes real `cost_usd` per request; this is the conversion that turns that
#: meter into a token debit.
CREDITS_PER_1K_TOKENS = int(os.getenv("CREDITS_PER_1K_TOKENS", "100"))


# ── Holder gate ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tier:
    name: str
    threshold: int  # whole $REDACTED that must be held
    grants: tuple[str, ...]


#: Thresholds are token-denominated on purpose. A USD-pegged gate would need a
#: price oracle in the auth path — one more thing that can fail open.
TIERS: tuple[Tier, ...] = (
    Tier(
        name="operator",
        threshold=1_000_000,
        grants=("terminal",),
    ),
    Tier(
        name="architect",
        threshold=10_000_000,
        grants=("terminal", "alpha-feed", "private-agents", "proxy-rpm-boost"),
    ),
    Tier(
        name="monolith",
        threshold=100_000_000,
        grants=("terminal", "alpha-feed", "private-agents", "proxy-rpm-boost",
                "committee-included"),
    ),
)


def tier_for(balance: int | Decimal) -> Tier | None:
    """Highest tier a balance qualifies for, or None if below every threshold."""
    qualified = [t for t in TIERS if Decimal(str(balance)) >= t.threshold]
    return max(qualified, key=lambda t: t.threshold) if qualified else None


def grants_for(balance: int | Decimal) -> frozenset[str]:
    """Capability set a balance unlocks. Empty for a wallet below the gate."""
    tier = tier_for(balance)
    return frozenset(tier.grants) if tier else frozenset()


def threshold_for_grant(grant: str) -> int | None:
    """Lowest balance that actually confers `grant`, or None if nothing does.

    A caller gating on something above the bottom rung needs the real number to
    quote back — telling an `alpha-feed` visitor they need 1,000,000 because
    that is `TIERS[0]` would be wrong, and wrong in the direction that wastes
    someone's money.
    """
    holders = [t.threshold for t in TIERS if grant in t.grants]
    return min(holders) if holders else None
