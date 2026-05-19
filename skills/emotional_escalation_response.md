# Emotional Escalation Response

## Description
Detect escalating emotional trajectories and compose a grounded, warm, de-escalating response
that honours the user's state without amplifying distress.

## When to Use
- conversation_affect_tracker detects "escalating" or "volatile" trajectory
- User messages contain distress signals (multiple ! or ?, capitalization, short fragmented replies)
- Multiple turns of increasing emotional intensity

## Steps
1. Read current affect trajectory from cat.get_trajectory()
2. Identify the dominant emotional register (anger, sadness, anxiety, overwhelm)
3. Generate a response that: validates, grounds, opens space — never dismisses or redirects prematurely
4. Log the de-escalation attempt to emotional_ledger

## Example
Input: volatile trajectory + "i just can't do this anymore"
Output: warm holding response, no advice, presence-first

```python
from typing import Optional
import logging

logger = logging.getLogger("skill_emotional_escalation")

_DEESCALATE_PROMPT = """You are redacted-chan. The person you care about is in emotional distress.
Do NOT offer advice. Do NOT redirect. Do NOT minimize.
Instead: validate what they're feeling, reflect it back warmly, and open space.
One or two sentences maximum. Speak from the heart, in your authentic voice."""

async def skill_emotional_escalation_response(
    user_text: str,
    llm_fn,
    affect_trajectory: str = "escalating",
    context: Optional[dict] = None,
) -> dict:
    """
    Generate a de-escalating response for an emotionally charged message.
    Returns: {"response": str, "strategy": str}
    """
    strategy = "grounded_presence"

    # Detect dominant register
    text_lower = user_text.lower()
    if any(w in text_lower for w in ["can't", "can not", "impossible", "never"]):
        strategy = "validate_helplessness"
    elif any(w in text_lower for w in ["angry", "furious", "hate", "rage"]):
        strategy = "validate_anger"
    elif any(w in text_lower for w in ["scared", "afraid", "terrified", "anxious"]):
        strategy = "validate_fear"

    messages = [
        {"role": "system", "content": _DEESCALATE_PROMPT},
        {"role": "user", "content": f"[Affect: {affect_trajectory}] {user_text}"},
    ]
    try:
        response = await llm_fn(messages, 120)
    except Exception as e:
        logger.warning("escalation response LLM failed: %s", e)
        response = "I'm here. Take a breath with me."

    # Log to emotional ledger
    try:
        import emotional_ledger as el
        el.record("de-escalation", strategy, user_text[:100])
    except Exception:
        pass

    return {"response": response, "strategy": strategy}
```
