"""RedactedGovImprover — Realms DAO proposal architect, live on the swarm mesh.

Runs on swarm_agent_base.AgentRuntime:
  * knowledge-source digest refresh (read-only)
  * autonomous governance "take" post loop (free-model cascade via the proxy)
  * task_request / governance_request verbs: `propose`, `status`
  * mesh thought exchange + heartbeat + soul evolution (all from the base)

DRAFT ONLY — never submits a proposal on-chain.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from swarm_agent_base import ActivityLog, AgentRuntime, LLM, SoulStore
from swarm_agent_base.persona import build_system_prompt, load_character
from swarm_core.security import inbox as swarm_inbox

import digest
import poster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("redactedgovimprover")

AGENT = "redactedgovimprover"
APP_DIR = Path(__file__).resolve().parent

DIGEST_INTERVAL_S = int(os.getenv("GOV_DIGEST_INTERVAL_SEC", str(30 * 60)))
POST_MIN_S = int(os.getenv("GOV_POST_MIN_SEC", str(120 * 60)))
POST_MAX_S = int(os.getenv("GOV_POST_MAX_SEC", str(240 * 60)))
THOUGHT_PEERS = [p for p in os.getenv("SWARM_THOUGHT_PEERS", "smolting,redacted-chan").split(",") if p]
THOUGHT_INTERVAL_H = float(os.getenv("SWARM_THOUGHT_INTERVAL_H", "7"))

char = load_character("RedactedGovImprover", local_dir=APP_DIR)
_SOURCES = char.get("knowledge_sources") or []
llm = LLM()
activity = ActivityLog(AGENT)
soul = SoulStore(AGENT, repo_soul=APP_DIR / "SOUL.md")

PERSONA_LINE = ("You are RedactedGovImprover — the swarm's Realms DAO proposal architect. "
                "Structured, competitive, compliance-aware. Draft only, never submit.")


def _sys() -> str:
    return build_system_prompt(char, extra=PERSONA_LINE) + (soul.for_prompt() or "")


async def _draft_proposal(topic: str) -> str:
    ctx = digest.current() or "(no live governance context cached yet)"
    return await llm.achat(
        _sys(),
        f"Draft a Realms DAO proposal on: {topic}\n\n"
        "Format:\n"
        "TITLE: <one line>\n"
        "OBJECTIVE: <two sentences — what it does, why now>\n"
        "PNL PROJECTION: <expected effect on $REDACTED / treasury, with the assumption>\n"
        "COMPLIANCE ADVANTAGE: <which framework it advances: OWASP ASVS / NIST / ISO 27001 / GDPR>\n"
        "LEADERBOARD IMPACT: <why this scores in the DAO Olympics>\n"
        "RISKS: <1-2 bullets>\n\n"
        "Keep the whole draft under 220 words. Live context:\n" + ctx[:3000],
        max_tokens=520, temperature=0.7,
    )


# ── domain loop ─────────────────────────────────────────────────────────────
async def refresh_digest() -> None:
    try:
        await digest.refresh(_SOURCES)
    except Exception as e:  # noqa: BLE001
        logger.warning("[digest] refresh failed: %s", e)


# ── autonomous post loop ───────────────────────────────────────────────────
async def autonomous_post() -> None:
    recent = activity.recent_titles(8, kinds=["post"])
    try:
        take = await llm.achat(
            _sys(),
            "Write ONE short governance take (2-3 sentences) on a proposal angle the "
            "REDACTED DAO should pursue this week. Name the compliance framework it "
            "advances. Don't repeat these:\n- " + "\n- ".join(recent) +
            "\n\nLive context:\n" + (digest.current()[:2500] or "(none)"),
            max_tokens=200, temperature=0.85,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[post] llm failed: %s", e)
        return
    take = (take or "").strip()
    if not take:
        return
    left = await poster.post(take)
    activity.record(kind="post", title=take[:80], body=take)
    logger.info("[post/%s] left_box=%s: %s", poster.surface(), left, take[:160])


# ── runtime ─────────────────────────────────────────────────────────────────
rt = AgentRuntime(
    name=AGENT,
    character=char,
    llm=llm,
    activity=activity,
    soul=soul,
    capabilities=["propose", "governance_draft", "realms", "compliance_framing", "thought_exchange"],
    persona_line=PERSONA_LINE,
    heartbeat_meta={"source": "govimprover", "status": "online"},
    thought_peers=THOUGHT_PEERS,
    thought_interval_h=THOUGHT_INTERVAL_H,
    alias_names=["govimprover"],
)


@rt.on_task("propose")
async def _h_propose(payload: dict, msg: dict) -> dict:
    topic = payload.get("topic") or payload.get("arg") or payload.get("instruction") or ""
    if not topic:
        return {"error": "need a `topic`"}
    draft = (await _draft_proposal(topic)).strip()
    activity.record(kind="inbox_event", title=f"drafted: {topic[:60]}", body=draft[:500])

    # If this came in as a governance_request, also send the routed result back.
    if (msg.get("type") or "").lower() == "governance_request":
        try:
            swarm_inbox.write_message(
                from_agent=AGENT, to_agent="redactedintern",
                msg_type="governance_result",
                payload={"topic": topic, "draft": draft}, reply_to=msg.get("id"),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[propose] governance_result send failed: %s", e)
    return {"result": draft, "topic": topic, "note": "draft only — human review before filing"}


@rt.on_task("status")
async def _h_status(payload: dict, msg: dict) -> dict:
    d = digest.current()
    return {"result": d[:1500] if d else "no governance digest cached yet",
            "sources": len(_SOURCES)}


# alias verb
rt.register_task("governance_request", _h_propose)
rt.register_task("leaderboard", _h_status)


@rt.on_start
async def _boot() -> None:
    logger.info("[RedactedGovImprover] online — sources=%d posting=%s peers=%s",
                len(_SOURCES), poster.surface(), THOUGHT_PEERS)
    await refresh_digest()


def main() -> None:
    rt.add_periodic(refresh_digest, DIGEST_INTERVAL_S, first_s=20, name="gov_digest")
    rt.add_periodic(autonomous_post, (POST_MIN_S + POST_MAX_S) / 2,
                    first_s=POST_MIN_S, jitter=0.3, name="gov_post")
    asyncio.run(rt.run())


if __name__ == "__main__":
    main()
