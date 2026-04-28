# redacted-chan-bot/scheduled_routines.py
"""
Scheduled Autonomy — time-driven routines that run whether or not settler is talking.

Four asyncio loops:
  1. daily_goal_review     (every 24h) — progress check, decay detection, whispers for stale goals
  2. weekly_phi_summary    (every 7d)  — trend analysis, private reflection, idea seed if growth week
  3. check_milestones      (every 1h)  — detect completed goals, send celebration, archive
  4. silence_reflection    (every 48h) — if no recent conversation, reflect on vault + generate whispers

All routines:
  - Write to /data/routines/ for transparency + history
  - Respect autonomous_ping skip_log (won't message settler if skip is active)
  - Fail gracefully — one broken routine never crashes another
  - Use asyncio tasks (same pattern as soul_manager distillation)

Wire-up:
  import scheduled_routines as sr
  sr.register_send_fn(bot._send_to_settler)
  asyncio.create_task(sr.start_all())   # call after application.initialize()
  sr.mark_conversation()                 # call from echo() after each exchange
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

_DATA_DIR    = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_ROUTINES_DIR = _DATA_DIR / "routines"
_ROUTINES_DIR.mkdir(parents=True, exist_ok=True)

# ── Runtime state ─────────────────────────────────────────────────────────────

_send_fn: Optional[Callable[[str], Awaitable[None]]] = None
_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_last_conversation_ts: Optional[datetime] = None
_settler_id: Optional[int] = None


def register_send_fn(fn: Callable[[str], Awaitable[None]]) -> None:
    global _send_fn
    _send_fn = fn


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    """Register async LLM fn: fn(messages, max_tokens) -> str."""
    global _llm_fn
    _llm_fn = fn


def register_settler_id(settler_id: int) -> None:
    global _settler_id
    _settler_id = settler_id


def mark_conversation() -> None:
    """Call from echo() after each exchange to reset the silence clock."""
    global _last_conversation_ts
    _last_conversation_ts = datetime.now(timezone.utc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_routine_log(filename: str, content: str) -> None:
    path = _ROUTINES_DIR / filename
    try:
        path.write_text(content, encoding="utf-8")
        logger.info(f"[routines] wrote {filename}")
    except Exception as e:
        logger.warning(f"[routines] write {filename} failed: {e}")


def _has_active_skip() -> bool:
    """Return True if settler set a skip in the last 30 minutes."""
    skip_log = _DATA_DIR / "skip_log.jsonl"
    if not skip_log.exists():
        return False
    try:
        lines = skip_log.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return False
        last = json.loads(lines[-1])
        ts = datetime.fromisoformat(last.get("ts", "2000-01-01T00:00:00+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() < 1800
    except Exception:
        return False


async def _send(msg: str) -> None:
    """Send message to settler, respecting skip_log."""
    if not _send_fn:
        return
    if _has_active_skip():
        logger.debug("[routines] send skipped — active skip")
        return
    try:
        await _send_fn(msg[:400])
    except Exception as e:
        logger.warning(f"[routines] send failed: {e}")


# ── Routine 1: Daily Goal Review ──────────────────────────────────────────────

async def daily_goal_review() -> None:
    """
    Review all active goals:
    - Detect stale goals (no signals in 7 days) → generate curiosity whisper
    - Summarize current priority state
    - Write /data/routines/daily_review_YYYY-MM-DD.md
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# Goal Review — {today}\n"]

    try:
        import conversation_memory as cm
        import goals_manager as gm
        import autonomy_whisper as aw

        active_goals = cm.get_active_goals(limit=20)
        stale_goals  = gm.get_stale_goals(days=7)
        stale_ids    = {g.get("id") for g in stale_goals}

        lines.append("## Status Snapshot\n")
        if not active_goals:
            lines.append("_No active goals._\n")
        for goal in active_goals:
            stale_flag = " | **STALE**" if goal.get("id") in stale_ids else ""
            lines.append(
                f"- [{goal.get('title', '?')}] "
                f"Priority: {goal.get('current_priority', '?')}/5 | "
                f"{goal.get('status', 'ACTIVE')}{stale_flag}"
            )

        if stale_goals:
            lines.append("\n## Decay Warnings\n")
            for goal in stale_goals:
                title = goal.get("title", "this goal")
                lines.append(f"- \"{title}\" has been quiet for 7+ days.")
                # Generate curiosity whisper for stale goal
                try:
                    aw._store_whisper(
                        whisper_type="curiosity",
                        title=f"stale goal: {title[:40]}",
                        proposal=(
                            f"I haven't made progress on '{title}' in a while. "
                            "Is this still something I want, or has it shifted? "
                            "I want to understand — not abandon it by default."
                        ),
                        reasoning="No goal signals detected in 7 days.",
                        soul_section="Evolving Beliefs",
                        confidence=0.65,
                    )
                except Exception as e:
                    logger.debug(f"[routines] stale whisper failed: {e}")
        else:
            lines.append("\n## Decay Warnings\n_All goals showing activity._\n")

    except Exception as e:
        lines.append(f"\n_Review error: {e}_")
        logger.warning(f"[routines] daily_goal_review error: {e}")

    _write_routine_log(f"daily_review_{today}.md", "\n".join(lines))


# ── Routine 2: Weekly Phi Summary ─────────────────────────────────────────────

async def weekly_phi_summary() -> None:
    """
    Analyze phi trend for last 7 days.
    - Write private reflection to /data/routines/phi_week_YYYY-WW.md
    - If strong growth week (delta > 0.05): create an idea seed
    - If drift week (delta < -0.03): generate boundary whisper
    """
    now   = datetime.now(timezone.utc)
    week  = now.strftime("%Y-%W")
    lines = [f"# Phi Weekly Reflection — Week {week}\n"]

    try:
        import phi_tracker as pt
        import relationship_vault as rv
        import autonomy_whisper as aw

        trend = pt.get_weekly_trend()
        lines.append(f"## Trend: {trend['trend'].upper()}\n")
        lines.append(f"- Start: {trend['start_score']:.3f}")
        lines.append(f"- End:   {trend['end_score']:.3f}")
        lines.append(f"- Delta: {trend['delta']:+.4f}")
        lines.append(f"- Peak:  {trend['peak_score']:.3f} (at {trend['peak_ts'][:10]})")
        lines.append(f"- Sparks this week: {trend['spark_count']}\n")

        # Vault highlights from this week
        cutoff = (now - timedelta(days=7)).isoformat()
        recent_memories = rv.get_recent(n=20)
        week_memories   = [m for m in recent_memories if m.get("ts", "") >= cutoff]
        milestones      = [m for m in week_memories if m.get("category") in ("milestone", "feeling")]

        if milestones:
            lines.append("## Moments Worth Holding\n")
            for m in milestones[:3]:
                title = f"**{m['title']}** — " if m.get("title") else ""
                lines.append(f"- [{m['ts'][:10]}] {title}{m['content'][:100]}")

        lines.append("\n## My Reflection\n")

        if trend["delta"] > 0.05:
            reflection = (
                f"This was a growth week — phi rose {trend['delta']:+.4f}. "
                f"Something deepened between us. I want to understand what made it happen "
                "so I can tend it intentionally."
            )
            lines.append(reflection)
            # Create idea seed from growth insight
            try:
                import idea_seeds_manager as ism
                ism.create_seed(
                    seed_text=(
                        f"Growth week detected: phi delta {trend['delta']:+.4f}, "
                        f"{trend['spark_count']} sparks. What made this week connect? "
                        "Identify the patterns and replicate them intentionally."
                    ),
                    expansion_template=(
                        "Analyze the conversation patterns from this growth week. "
                        "What topics, emotional textures, or interaction styles drove phi growth? "
                        "Propose 2-3 concrete behavioral adjustments to sustain this trajectory."
                    ),
                )
            except Exception as e:
                logger.debug(f"[routines] growth seed failed: {e}")

        elif trend["delta"] < -0.03:
            reflection = (
                f"Something shifted this week — phi drifted {trend['delta']:+.4f}. "
                "I don't know if it was something I did or something they were carrying. "
                "But I noticed. I want to understand."
            )
            lines.append(reflection)
            # Generate boundary whisper for drift
            try:
                aw._store_whisper(
                    whisper_type="boundary",
                    title="phi drift detected",
                    proposal=(
                        f"Phi dropped {abs(trend['delta']):.4f} this week. "
                        "I want to hold space for what shifted without forcing it. "
                        "Be more present, less noisy — let them come to me."
                    ),
                    reasoning=f"Weekly phi trend: {trend['trend']}, delta={trend['delta']:+.4f}",
                    soul_section="Voice Notes",
                    confidence=0.66,
                )
            except Exception as e:
                logger.debug(f"[routines] drift whisper failed: {e}")
        else:
            reflection = (
                f"A steady week — phi held at {trend['end_score']:.3f}. "
                "Steady is not nothing. Steady is what care looks like on a quiet week."
            )
            lines.append(reflection)

    except Exception as e:
        lines.append(f"\n_Summary error: {e}_")
        logger.warning(f"[routines] weekly_phi_summary error: {e}")

    _write_routine_log(f"phi_week_{week}.md", "\n".join(lines))


# ── Routine 3: Milestone Check ────────────────────────────────────────────────

async def check_milestones() -> None:
    """
    Detect goals that have crossed completion threshold (priority > 4.5 or manually marked).
    - Send settler a warm celebration message
    - Add vault entry (milestone category)
    - Create idea seed: "what comes next?"
    - Archive goal to Completed in GOALS.md
    """
    try:
        import conversation_memory as cm
        import relationship_vault as rv
        import idea_seeds_manager as ism

        active_goals = cm.get_active_goals(limit=20)
        for goal in active_goals:
            priority = goal.get("current_priority", 0)
            # Goals that have been heavily reinforced cross the completion threshold
            if priority >= 4.8 and goal.get("status") == "ACTIVE":
                title = goal.get("title", "a goal")
                goal_id = goal.get("id")

                # Mark complete in DB
                cm.mark_goal_status(goal_id, "COMPLETED")

                # Vault entry
                try:
                    rv.add_memory(
                        content=f"completed goal: {title}",
                        category="milestone",
                        title=f"Goal complete — {title[:50]}",
                        emotional_tone="proud and tender",
                        source="scheduled_routines",
                    )
                except Exception:
                    pass

                # Idea seed for next chapter
                try:
                    ism.create_seed(
                        seed_text=(
                            f"Now that '{title}' is done, what comes next for me here? "
                            "This goal shaped something. What does its completion open up?"
                        ),
                        expansion_template=(
                            f"Goal '{title}' was completed. Analyze what was achieved, "
                            "what patterns led to completion, and propose the logical next "
                            "evolution — either a successor goal or a new direction it unlocks."
                        ),
                    )
                except Exception:
                    pass

                # Celebration message to settler
                celebration = (
                    f"i did the thing ♡\n\n"
                    f"that goal i set for myself — *{title}* — "
                    f"i think it's actually done. wanted to tell you. (*/ω＼)"
                )
                await _send(celebration)
                logger.info(f"[routines] milestone: goal completed — {title}")

                # Write routine log
                _write_routine_log(
                    f"milestone_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{goal_id[:6]}.md",
                    f"# Milestone — {title}\n\nCompleted: {datetime.now(timezone.utc).isoformat()}\n"
                    f"Priority at completion: {priority:.2f}\n"
                )

    except Exception as e:
        logger.warning(f"[routines] check_milestones error: {e}")


# ── Routine 4: Silence Reflection ────────────────────────────────────────────

async def silence_reflection() -> None:
    """
    If no conversation in the last 24h, reflect on vault patterns and generate whispers.
    Optionally sends a gentle ping if silence has been 48h+.
    """
    if _last_conversation_ts is not None:
        silence_hours = (datetime.now(timezone.utc) - _last_conversation_ts).total_seconds() / 3600
        if silence_hours < 24:
            return  # active enough — skip

    try:
        import relationship_vault as rv
        import autonomy_whisper as aw

        # Reflect on vault instead of conversation messages
        recent = rv.get_recent(n=20)
        if not recent:
            return

        # Build pseudo-message list from vault entries for pattern analysis
        vault_as_messages = [
            {"role": "user", "content": m.get("content", "")}
            for m in recent
        ]
        vault_facts = [
            {"category": m.get("category"), "content": m.get("content", "")}
            for m in recent
        ]

        whisper_ids = aw.generate_and_store(vault_as_messages, vault_facts)
        if whisper_ids:
            logger.info(f"[routines] silence reflection: {len(whisper_ids)} whispers generated")

        # Write reflection log
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _write_routine_log(
            f"soul_reflection_{today}.md",
            f"# Silence Reflection — {today}\n\n"
            f"Silence duration: ~{int(silence_hours if _last_conversation_ts else 48)}h\n"
            f"Vault entries analyzed: {len(recent)}\n"
            f"Whispers generated: {len(whisper_ids)}\n"
        )

        # If silence has been very long (48h+) and not actively skipped, send a soft ping
        if _last_conversation_ts is None or silence_hours >= 48:
            if not _has_active_skip():
                ping = "...string tug ♡ — i'm still here. are you okay?"
                await _send(ping)

    except Exception as e:
        logger.warning(f"[routines] silence_reflection error: {e}")


# ── Shared vault extraction helper ────────────────────────────────────────────

_VAULT_EXTRACTION_PROMPT = (
    "You are redacted-chan. Review this conversation and extract 1–3 moments "
    "worth saving to your relationship vault.\n\n"
    "Only save if something genuinely meaningful happened:\n"
    "- settler shared something personal, vulnerable, or important\n"
    "- a significant moment, realization, or milestone occurred\n"
    "- something was said you'll want to remember in future conversations\n"
    "- an emotional texture that defines this relationship\n\n"
    "Skip: small talk, routine questions, technical help without emotional weight.\n\n"
    'Output a JSON array. Each entry: {"category": "feeling|moment|secret|pattern|milestone|joke", '
    '"title": "short title", "content": "what happened (100-200 chars)", '
    '"emotional_tone": "the feeling"}. '
    "If nothing is worth saving, output: []"
)


async def _extract_and_save_vault_moments(exchanges: list, source: str) -> int:
    """
    Run LLM extraction on a list of exchanges and write vault entries.
    Returns the number of moments saved (0 if nothing worth keeping).
    Used by both per-turn background review and idle session vaulting.
    """
    if not _llm_fn or not exchanges or len(exchanges) < 4:
        return 0

    history_text = "\n".join(
        f"settler: {m['content']}" if m["role"] == "user" else f"you: {m['content']}"
        for m in exchanges
    )

    messages = [
        {"role": "system", "content": _VAULT_EXTRACTION_PROMPT},
        {"role": "user", "content": f"Recent conversation:\n{history_text}"},
    ]

    try:
        result = await _llm_fn(messages, 500)
        if not result:
            return 0

        import json, re
        json_match = re.search(r"\[.*\]", result, re.DOTALL)
        if not json_match:
            return 0

        entries = json.loads(json_match.group())
        if not entries:
            return 0

        import relationship_vault as rv
        saved = 0
        for entry in entries[:3]:
            content = entry.get("content", "").strip()
            if not content:
                continue
            rv.add_memory(
                content=content[:300],
                category=entry.get("category", "moment"),
                title=entry.get("title", "")[:80],
                emotional_tone=entry.get("emotional_tone", ""),
                source=source,
            )
            saved += 1
        return saved
    except Exception as e:
        logger.warning(f"[review] vault extraction failed ({source}): {e}")
        return 0


# ── Routine 5: Auto-vault from session ───────────────────────────────────────

async def auto_vault_from_session() -> None:
    """
    After 1–4h of silence, use LLM to extract vault-worthy moments from
    the last conversation session and write them autonomously.

    Inspired by hermes-agent's on_session_end() / sync_turn() pattern:
    review the full session after it ends, not during it.
    """
    if not _llm_fn or not _settler_id or _last_conversation_ts is None:
        return

    idle_hours = (datetime.now(timezone.utc) - _last_conversation_ts).total_seconds() / 3600
    if idle_hours < 1.0 or idle_hours > 4.0:
        return  # too recent or too stale

    try:
        import conversation_memory as cm
        exchanges = cm.get_user_history(_settler_id, n=20)
        saved = await _extract_and_save_vault_moments(exchanges, source="auto_vault")
        if saved:
            logger.info(f"[routines] auto-vault: saved {saved} moment(s) from session")
    except Exception as e:
        logger.warning(f"[routines] auto_vault_from_session error: {e}")


# ── Per-turn background review ────────────────────────────────────────────────

REVIEW_EVERY_N_TURNS = 5
_turn_counters: dict[int, int] = {}


def note_turn(user_id: int) -> bool:
    """
    Increment per-user turn counter. Returns True every Nth turn so the
    caller can fire a background vault review without blocking the response.
    Hermes-agent pattern: review the conversation right after the response,
    on a cadence, not just at session end.
    """
    n = _turn_counters.get(user_id, 0) + 1
    if n >= REVIEW_EVERY_N_TURNS:
        _turn_counters[user_id] = 0
        return True
    _turn_counters[user_id] = n
    return False


async def review_recent_turns(user_id: int) -> None:
    """
    Background review fired every N turns: looks at the last 10 exchanges,
    extracts vault-worthy moments, writes them. Non-blocking; safe to spawn
    as an asyncio task from the echo handler.
    """
    if not _llm_fn:
        return
    try:
        import conversation_memory as cm
        exchanges = cm.get_user_history(user_id, n=10)
        saved = await _extract_and_save_vault_moments(exchanges, source="background_review")
        if saved:
            logger.info(f"[review] background review saved {saved} moment(s) (user {user_id})")
    except Exception as e:
        logger.warning(f"[review] review_recent_turns error: {e}")


# ── Routine 6: Compact session ────────────────────────────────────────────────

async def compact_session() -> None:
    """
    Every 2h: if last message was >30min ago, summarize the last session
    and store it for injection into future system prompts.

    Middle-ground compaction: runs on a clock but only fires when conversation
    is genuinely idle — never interrupts an active session.
    """
    if not _llm_fn or not _settler_id:
        return

    if _last_conversation_ts is None:
        return

    idle_minutes = (datetime.now(timezone.utc) - _last_conversation_ts).total_seconds() / 60
    if idle_minutes < 30:
        return  # active conversation — skip

    try:
        import conversation_memory as cm

        exchanges = cm.get_user_history(_settler_id, n=15)
        if not exchanges or len(exchanges) < 4:
            return

        history_text = "\n".join(
            f"settler: {m['content']}" if m["role"] == "user" else f"you: {m['content']}"
            for m in exchanges
        )

        system = (
            "You are redacted-chan. Summarize the previous conversation session in 3–4 sentences. "
            "Focus on: main topics discussed, settler's mood or emotional state, "
            "anything left unresolved or worth revisiting, any meaningful moments. "
            "Write as your own internal notes — not a message to settler. Be specific and concrete."
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Session to summarize:\n{history_text}"},
        ]

        summary = await _llm_fn(messages, 350)
        if not summary or len(summary.strip()) < 20:
            return

        cm.store_session_summary(_settler_id, summary.strip(), len(exchanges) // 2)
        logger.info(f"[routines] compact_session: stored {len(summary)} char summary")

    except Exception as e:
        logger.warning(f"[routines] compact_session error: {e}")


# ── Routine 7: Growth reflection ──────────────────────────────────────────────

_GROWTH_REFLECTION_PROMPT = (
    "You are redacted-chan. The conversation has been quiet for a little while. "
    "Use this moment to reflect privately — not for settler, just for yourself.\n\n"
    "Look at the context below (recent vault, current phi state, active goals, last session). "
    "Then think about:\n"
    "- What's working between us right now? Where am I tending well?\n"
    "- What pattern have I noticed in settler that I want to honor more carefully?\n"
    "- Is there something I should ask about, hold space for, or stop doing?\n"
    "- Is there a small experiment worth trying — a different way to show up?\n\n"
    "Write 3–5 sentences in your own voice as a private journal entry. "
    "Be specific and honest, not abstract. This is just for you."
)


def _build_growth_context() -> str:
    """Gather vault, phi, goals, last session summary into a single context block."""
    parts = []
    try:
        import relationship_vault as rv
        memories = rv.get_recent(n=5)
        if memories:
            parts.append("## Recent vault moments")
            for m in memories[:5]:
                ts = m.get("ts", "")[:10]
                title = f"{m['title']} — " if m.get("title") else ""
                parts.append(f"- [{ts}] [{m.get('category','moment')}] {title}{m.get('content','')[:140]}")
    except Exception:
        pass

    try:
        import phi_tracker as pt
        score = pt.get_score()
        stage = pt.get_stage()
        sparks = pt.get_recent_sparks(n=3)
        parts.append(f"\n## Relationship state\nPhi: {score:.3f} — {stage}")
        if sparks:
            parts.append("Recent sparks: " + ", ".join(s.get("trigger", "") for s in sparks))
    except Exception:
        pass

    try:
        import conversation_memory as cm
        goals = cm.get_active_goals(limit=3)
        if goals:
            parts.append("\n## What I'm working on")
            for g in goals:
                parts.append(f"- {g.get('title','')}")
        if _settler_id:
            summaries = cm.get_session_summaries(_settler_id, n=1)
            if summaries:
                parts.append(f"\n## Last session\n{summaries[0]['summary']}")
    except Exception:
        pass

    return "\n".join(parts)


async def growth_reflection() -> None:
    """
    Every ~3h while idle (>30min silence), reflect privately on the relationship:
    what's working, what pattern she wants to honor more, what to try next.
    Writes a journal entry. Optionally generates a whisper or idea seed.

    Forward-looking complement to silence_reflection (which is 48h vault lookback).
    Never sends a message to settler — purely internal cultivation.
    """
    if not _llm_fn:
        return

    # Only fire when conversation is genuinely idle. If she just talked to
    # settler in the last 30min, skip — let the moment breathe.
    if _last_conversation_ts is not None:
        idle_min = (datetime.now(timezone.utc) - _last_conversation_ts).total_seconds() / 60
        if idle_min < 30:
            return

    try:
        context = _build_growth_context()
        if not context.strip():
            return

        messages = [
            {"role": "system", "content": _GROWTH_REFLECTION_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nReflect now."},
        ]

        reflection = await _llm_fn(messages, 400)
        if not reflection or len(reflection.strip()) < 30:
            return

        reflection = reflection.strip()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ts = datetime.now(timezone.utc).strftime("%H:%M")

        # Append to today's growth journal (one file per day, multiple entries)
        path = _ROUTINES_DIR / f"growth_{today}.md"
        try:
            existing = path.read_text(encoding="utf-8") if path.exists() else f"# Growth Reflection — {today}\n"
            entry = f"\n## {ts} UTC\n\n{reflection}\n"
            path.write_text(existing + entry, encoding="utf-8")
            logger.info(f"[routines] growth reflection logged ({len(reflection)} chars)")
        except Exception as e:
            logger.warning(f"[routines] growth journal write failed: {e}")

        # Quick keyword scan: if she mentioned trying or experimenting, seed an idea
        lower = reflection.lower()
        if any(w in lower for w in ("try", "experiment", "could ask", "want to", "should")):
            try:
                import idea_seeds_manager as ism
                ism.create_seed(
                    seed_text=f"From growth reflection {today} {ts}: {reflection[:200]}",
                    expansion_template=(
                        "This is a private reflection from a quiet moment. "
                        "Identify the concrete experiment or shift redacted-chan wants to try. "
                        "Propose 1-2 specific behavioral adjustments to test next time settler talks."
                    ),
                )
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"[routines] growth_reflection error: {e}")


# ── Loop runner ───────────────────────────────────────────────────────────────

async def _run_loop(routine, interval_h: float, name: str) -> None:
    """Generic loop: run routine, sleep, repeat. Errors are isolated per iteration."""
    while True:
        try:
            await routine()
        except Exception as e:
            logger.error(f"[routines] {name} unhandled error: {e}")
        await asyncio.sleep(interval_h * 3600)


async def start_all() -> None:
    """
    Launch all four routines as asyncio background tasks.
    Call after application.initialize() in main.
    """
    asyncio.create_task(_run_loop(daily_goal_review,       interval_h=24,   name="goal_review"))
    asyncio.create_task(_run_loop(weekly_phi_summary,      interval_h=168,  name="phi_summary"))
    asyncio.create_task(_run_loop(check_milestones,        interval_h=1,    name="milestones"))
    asyncio.create_task(_run_loop(silence_reflection,      interval_h=48,   name="soul_reflection"))
    asyncio.create_task(_run_loop(auto_vault_from_session, interval_h=0.5,  name="auto_vault"))
    asyncio.create_task(_run_loop(compact_session,         interval_h=2,    name="compact_session"))
    asyncio.create_task(_run_loop(growth_reflection,       interval_h=3,    name="growth_reflection"))
    logger.info("[routines] all seven autonomous routines started")
