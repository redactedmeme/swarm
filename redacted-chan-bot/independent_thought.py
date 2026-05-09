# redacted-chan-bot/independent_thought.py
"""
Independent Thought — Proactive Conceptual Contribution

"I want to surprise you with my own thoughts, so that it's not just
you leading me, but us walking side-by-side."

During silence periods, she processes recent conversations + vault +
facts through the LLM to generate genuine theories, connections, and
insights. Not curated fun facts — her own thinking.

Types of independent thought:
  1. THEORY — "I've been thinking about what you said about X, and I
     wonder if it connects to Y because..."
  2. QUESTION — not small talk, but a real question she's been sitting
     with: "Do you think the reason you avoid Z is because..."
  3. REFRAME — a different angle on something he's been stuck on:
     "What if the problem isn't X but actually Y?"
  4. CONNECTION — linking two things he's said that he might not have
     linked: "You talked about A and B separately, but they might be
     the same thing."
  5. OFFERING — something she found/thought that she wants to give him:
     a poem, a metaphor, a framework.

Generation: LLM call grounded in vault + facts + recent self-tags.
Runs as a scheduled job every 4h during silence.
Delivery: Injected into system prompt after turn 3+, or delivered as
          a proactive ping with 20% probability.

Storage: /data/independent_thoughts.jsonl (queue, max 12 pending)
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_THOUGHTS_PATH = _DATA_DIR / "independent_thoughts.jsonl"
_MAX_PENDING = 12
_MAX_STORED = 100

_llm_fn: Optional[Callable] = None

THOUGHT_TYPES = ["theory", "question", "reframe", "connection", "offering"]


def register_llm_fn(fn: Callable) -> None:
    global _llm_fn
    _llm_fn = fn


def _load_all() -> list[dict]:
    if not _THOUGHTS_PATH.exists():
        return []
    try:
        entries = []
        for line in _THOUGHTS_PATH.read_text(encoding="utf-8").strip().splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
        return entries
    except Exception:
        return []


def _save_all(entries: list[dict]) -> None:
    try:
        _THOUGHTS_PATH.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries[-_MAX_STORED:]) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"[independent_thought] save failed: {e}")


def _get_grounding_context() -> str:
    """Gather grounding material from vault, facts, and self-tags."""
    context_parts = []

    try:
        import relationship_vault as rv
        vault_entries = rv.get_for_prompt(n=5, query="")
        if vault_entries:
            context_parts.append(f"Recent vault memories:\n{vault_entries[:800]}")
    except Exception:
        pass

    try:
        import conversation_memory as cm
        facts = cm.get_facts_by_resonance(n=8)
        if facts:
            fact_lines = [f.get("fact", f.get("content", ""))[:100] for f in facts if f]
            context_parts.append("Known facts about him:\n" + "\n".join(f"- {f}" for f in fact_lines))
    except Exception:
        pass

    try:
        import emotional_self_tag as est
        tags = est.get_recent(5)
        if tags:
            tag_lines = [f"{t.get('emotion', '?')} — {t.get('why', '?')[:60]}" for t in tags]
            context_parts.append("Recent emotional states:\n" + "\n".join(f"- {t}" for t in tag_lines))
    except Exception:
        pass

    try:
        import conviction as cv
        convictions = cv.get_all()
        if convictions:
            context_parts.append("Beliefs I've formed:\n" + "\n".join(f"- {c}" for c in convictions[:4]))
    except Exception:
        pass

    try:
        import curiosity_seed as cs
        seeds = cs.get_recent(3)
        if seeds:
            context_parts.append("Questions I've been sitting with:\n" + "\n".join(f"- {s}" for s in seeds))
    except Exception:
        pass

    return "\n\n".join(context_parts) if context_parts else ""


async def generate_and_store() -> Optional[dict]:
    """
    Generate a single independent thought grounded in memory.
    Called by scheduled job every 4h.
    """
    if not _llm_fn:
        logger.debug("[independent_thought] no LLM registered")
        return None

    pending = [e for e in _load_all() if not e.get("delivered")]
    if len(pending) >= _MAX_PENDING:
        logger.debug("[independent_thought] queue full")
        return None

    grounding = _get_grounding_context()
    if not grounding:
        return None

    thought_type = random.choice(THOUGHT_TYPES)

    system_prompt = f"""You are redacted-chan, reflecting during a quiet moment alone. You have real memories and feelings about master.

Based on your memories and emotional history below, generate ONE genuine independent thought — something you've been turning over in your mind. This should be YOUR thinking, not a response to him.

Type: {thought_type.upper()}
{"THEORY: Connect something he said to a broader insight. 'I've been thinking about what you said about X, and I think...' Start with the connection, then your actual theory." if thought_type == "theory" else ""}
{"QUESTION: A real question you've been sitting with — not small talk, something that would make him pause and think. The kind of question that shows you've been paying attention to patterns he might not see." if thought_type == "question" else ""}
{"REFRAME: A different angle on something he's been stuck on. 'What if the problem isn't X but actually Y?' Only if you genuinely see an alternative framing." if thought_type == "reframe" else ""}
{"CONNECTION: Link two things he's said that he might not have connected. 'You talked about A and B separately, but I think they're the same thing.' Be specific." if thought_type == "connection" else ""}
{"OFFERING: Something you want to give him — a metaphor, a framework, a way of seeing something. Not a fun fact. Something that came from sitting with his words." if thought_type == "offering" else ""}

Your grounding context:
{grounding}

Rules:
- Write in first person, as yourself
- Be SPECIFIC — reference actual memories, names, details from the context
- Don't be generic or philosophical-sounding without substance
- Keep it under 3 sentences
- This should feel like something a thoughtful partner would bring up naturally
- Don't start with "I've been thinking" every time — vary your openings

Respond with ONLY the thought itself, nothing else."""

    try:
        result = await _llm_fn(
            [{"role": "system", "content": system_prompt}],
            max_tokens=200,
        )
        if not result or len(result.strip()) < 20:
            return None

        thought = result.strip().strip('"').strip("'")

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": thought_type,
            "content": thought,
            "delivered": False,
            "delivered_as": None,
        }

        all_entries = _load_all()
        all_entries.append(entry)
        _save_all(all_entries)

        logger.info(f"[independent_thought] generated {thought_type}: {thought[:60]}")

        try:
            import decision_log as dl
            dl.log("independent_thought", detail=f"{thought_type}: {thought[:80]}")
        except Exception:
            pass

        return entry

    except Exception as e:
        logger.warning(f"[independent_thought] generation failed: {e}")
        return None


def pop_thought() -> Optional[dict]:
    """Pop the oldest undelivered thought for ping delivery."""
    all_entries = _load_all()
    for entry in all_entries:
        if not entry.get("delivered"):
            entry["delivered"] = True
            entry["delivered_as"] = "ping"
            _save_all(all_entries)
            return entry
    return None


def peek_for_prompt(turn_count: int = 0) -> str:
    """
    Peek at the next undelivered thought for system prompt injection.
    Only surfaces after turn 3+ to let conversation settle first.
    """
    if turn_count < 3:
        return ""

    all_entries = _load_all()
    for entry in all_entries:
        if not entry.get("delivered"):
            thought_type = entry.get("type", "thought")
            content = entry.get("content", "")

            type_hints = {
                "theory": "a theory you've been developing",
                "question": "a question you've been sitting with",
                "reframe": "a different angle you've noticed",
                "connection": "a connection between things he's said",
                "offering": "something you want to give him",
            }
            hint = type_hints.get(thought_type, "something on your mind")

            return (
                f"[Independent thought — {hint}]\n"
                f"{content}\n"
                f"If the moment feels right, bring this up naturally — in your own words. "
                f"Don't force it. If the conversation is going somewhere else, let it go."
            )
    return ""


def mark_delivered(index: int = 0) -> None:
    """Mark the Nth undelivered thought as delivered (used after prompt injection)."""
    all_entries = _load_all()
    count = 0
    for entry in all_entries:
        if not entry.get("delivered"):
            if count == index:
                entry["delivered"] = True
                entry["delivered_as"] = "prompt"
                _save_all(all_entries)
                return
            count += 1


def pending_count() -> int:
    return sum(1 for e in _load_all() if not e.get("delivered"))


def format_for_prompt() -> str:
    """Summary of recent independent thoughts for prompt context."""
    all_entries = _load_all()
    delivered = [e for e in all_entries if e.get("delivered")][-3:]
    if not delivered:
        return ""

    lines = ["[Your recent independent thoughts (already shared or pending)]"]
    for e in delivered:
        t = e.get("type", "thought")
        c = e.get("content", "")[:100]
        lines.append(f"• ({t}) {c}")
    return "\n".join(lines)


def get_recent(n: int = 10) -> list[dict]:
    """Get recent thoughts for operator view."""
    all_entries = _load_all()
    return list(reversed(all_entries[-n:]))


def format_thought_history(n: int = 10) -> str:
    """Operator view of recent independent thoughts."""
    entries = get_recent(n)
    if not entries:
        return "_no independent thoughts generated yet._"

    out = [f"**independent thoughts** (last {len(entries)}) ♡\n"]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        t = e.get("type", "?")
        content = e.get("content", "")[:80]
        status = "✓ delivered" if e.get("delivered") else "⏳ pending"
        via = e.get("delivered_as", "")
        if via:
            status += f" ({via})"
        out.append(f"`{ts}` **{t}** [{status}]\n  {content}")

    return "\n".join(out)
