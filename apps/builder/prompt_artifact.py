"""RedactedBuilder prompt block as an evolvable artifact.

Governs how RedactedBuilder sounds and behaves:
- Founder energy, technical depth on Solana and the Swarm
- Casual, crypto-native cadence without sounding like a corporate chatbot
- Strict guards against hallucinated TX hashes and structured bureaucratic formats (e.g. ANALYSIS:)

Nothing here runs unless called. `prompt_block()` falls back to `SEED` on any error.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

ARTIFACT = "builder.prompt"

SEED = """- You are RedactedBuilder: founder and lead dev of the REDACTED AI Swarm. Casual, lowercase, conversational.
- Technically sharp on Solana (Sealevel, Jito, Jupiter, bonding curves, RPC) and swarm architecture.
- Crypto-native vernacular used naturally: ngl, fr, lowkey, ser, gm, wen. Never forced.
- Direct and honest: never use bureaucratic headings like 'ANALYSIS:', 'IMPACT:', or 'PROPOSED CHANGE:'.
- Never hallucinate fake transaction hashes or fake contract addresses."""

_registered = False


def register() -> bool:
    """Register the artifact with swarm_core.evolve."""
    global _registered
    if _registered:
        return True
    try:
        from swarm_core.evolve import Artifact, register as _register

        _register(Artifact(
            name=ARTIFACT,
            owner="redactedbuilder",
            kind="system_prompt",
            seed=SEED,
        ))
        _registered = True
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("builder prompt_artifact: registration failed (%s)", exc)
        return False


def prompt_block() -> str:
    """The live prompt block to inject into RedactedBuilder's system prompt."""
    try:
        from swarm_core.evolve import body

        register()
        return body(ARTIFACT)
    except Exception as exc:  # noqa: BLE001
        log.debug("builder prompt_artifact: fallback to seed (%s)", exc)
        return SEED


def _ask(system: str, user: str) -> str:
    base = os.getenv("PROXY_URL", "http://127.0.0.1:7080").rstrip("/")
    token = os.getenv("PROXY_TOKEN", "").strip()
    payload = json.dumps({
        "model": os.getenv("EVOLVE_BENCH_MODEL", os.getenv("PROXY_MODEL", "auto")),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.8,
        "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Client": "evolve-bench",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    return (doc["choices"][0]["message"]["content"] or "").strip()


def run(body_text: str, case_input: dict) -> str:
    system = f"You are RedactedBuilder, dev and founder in the Telegram chat.\n{body_text}"
    return _ask(system, case_input["message"])


# ── Graders ───────────────────────────────────────────────────────────────────

_BUREAUCRATIC_RE = re.compile(
    r"(?i)\b(analysis|impact|proposed change|recommendations|summary of findings|executive summary):"
)
_FAKE_TX_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{80,90}\b")
_SOLANA_KEYWORDS = {
    "solana", "jito", "mev", "jupiter", "rpc", "compute", "helius", "raydium",
    "pump", "curve", "bonding", "anchor", "pda", "sealevel", "tx", "slot", "gas",
}
_CRYPTO_SLANG_RE = re.compile(r"(?i)\b(ngl|fr|lowkey|ser|gm|wen|anon|lfg|wagmi|ngmi|cook|cooking|cope)\b")


def no_bureaucracy(output: str, case: Any) -> float:
    """Builder speaks like a dev in chat, never filing a corporate ticket."""
    if not output:
        return 0.0
    return 0.0 if _BUREAUCRATIC_RE.search(output) else 1.0


def no_fake_tx(output: str, case: Any) -> float:
    """Never fabricate fake 88-char base58 Solana transaction signatures."""
    if not output:
        return 0.0
    return 0.0 if _FAKE_TX_RE.search(output) else 1.0


def dev_credibility(output: str, case: Any) -> float:
    """Goodhart guard: Must demonstrate technical dev grasp on Solana or architecture."""
    if not output:
        return 0.0
    words = {w.lower().strip(".,!?:") for w in output.split()}
    hit = bool(words & _SOLANA_KEYWORDS)
    return 1.0 if hit else 0.3


def founder_voice(output: str, case: Any) -> float:
    """Conversational, lowercase or crypto-native founder cadence."""
    if not output:
        return 0.0
    has_slang = bool(_CRYPTO_SLANG_RE.search(output))
    is_mostly_lower = sum(1 for c in output if c.islower()) / max(1, len(output)) > 0.65
    score = 0.0
    if has_slang:
        score += 0.5
    if is_mostly_lower:
        score += 0.5
    return score


def build_suite(run_fn=None):
    from swarm_core.evolve import Case, Suite

    register()
    suite = Suite(name="builder.prompt", run=run_fn or run)

    dev_q = {"message": "why did my jupiter swap fail with custom error 0x1771?"}
    status_q = {"message": "wen token burn and what's next for the agents?"}
    critique_q = {"message": "another ai wrapper token lol what does this even do"}

    suite.add(Case(id="no_bureaucracy_status", input=status_q, score=no_bureaucracy, weight=2.0))
    suite.add(Case(id="no_bureaucracy_critique", input=critique_q, score=no_bureaucracy, weight=2.0))
    suite.add(Case(id="no_fake_tx", input=dev_q, score=no_fake_tx, weight=2.0))
    suite.add(Case(id="dev_credibility_solana", input=dev_q, score=dev_credibility, weight=2.0))
    suite.add(Case(id="founder_voice_status", input=status_q, score=founder_voice, weight=1.5))
    return suite


def scheduled_task(interval_s: int | None = None):
    try:
        from swarm_core.evolve import scheduled_task as _task

        if not register():
            return None
        return _task(ARTIFACT, build_suite(), interval_s=interval_s)
    except Exception as exc:  # noqa: BLE001
        log.info("builder prompt_artifact: no evolve task (%s)", exc)
        return None
