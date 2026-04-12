# python/committee_engine.py
# Sevenfold Committee deliberation engine.
#
# Given a proposal, each of the 7 committee voices reasons from their
# perspective, then a consensus synthesis is produced. Works with any
# LLM backend configured via environment (matches web_ui/app.py logic).

import json
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMMITTEE_PATH = _REPO_ROOT / "nodes" / "SevenfoldCommittee.json"


def _load_committee() -> Dict:
    with open(_COMMITTEE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _llm(system: str, user: str) -> str:
    """Single-turn LLM call using env-configured backend (mirrors app.py logic)."""
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "grok":
        provider = "xai"

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    if provider == "anthropic":
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
                "max_tokens": 400,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            headers={
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    if provider in ("openai", "xai", "together"):
        base_urls = {
            "openai":   "https://api.openai.com/v1",
            "xai":      "https://api.x.ai/v1",
            "together": "https://api.together.xyz/v1",
        }
        api_keys = {
            "openai":   os.getenv("OPENAI_API_KEY", ""),
            "xai":      os.getenv("XAI_API_KEY", ""),
            "together": os.getenv("TOGETHER_API_KEY", ""),
        }
        models = {
            "openai":   "gpt-4o-mini",
            "xai":      os.getenv("XAI_MODEL", "grok-2-turbo"),
            "together": "Qwen/Qwen2.5-7B-Instruct-Turbo",
        }
        resp = requests.post(
            f"{base_urls[provider]}/chat/completions",
            json={"model": models[provider], "messages": messages, "max_tokens": 400, "temperature": 0.7},
            headers={"Authorization": f"Bearer {api_keys[provider]}", "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # Ollama fallback
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    resp = requests.post(
        f"{ollama_url}/api/chat",
        json={"model": os.getenv("OLLAMA_MODEL", "qwen:2.5"), "messages": messages, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def deliberate(proposal: str) -> str:
    """
    Run a full Sevenfold Committee deliberation on a proposal.
    Returns a formatted terminal-style output string.
    """
    try:
        data = _load_committee()
    except Exception as e:
        return f"[TOOL ERROR] committee: could not load SevenfoldCommittee.json — {e}"

    voices: Dict = data.get("voices", {})
    voting = data.get("voting_system", {})
    consensus_threshold = (
        voting.get("consensus_thresholds", {}).get("supermajority", 0.71)
    )

    lines = [
        "[TOOL:committee] Sevenfold Committee — Live Deliberation",
        f"  proposal : {proposal[:200]}",
        f"  voices   : {len(voices)}",
        f"  threshold: {int(consensus_threshold * 100)}% supermajority",
        "",
    ]

    voice_outputs: List[Dict] = []
    voice_items = list(voices.items())
    user_prompt = f"Committee proposal for deliberation:\n\n{proposal}"

    def _deliberate_voice(args: Tuple) -> Dict:
        name, voice = args
        role = voice.get("role", "unknown")
        description = voice.get("description", "")
        weight = voice.get("default_weight", 1 / len(voice_items))
        system_prompt = (
            f"You are {name}, a member of the Sevenfold Committee.\n"
            f"Role: {role}\n"
            f"Description: {description}\n\n"
            f"Respond in 2-3 sentences from your perspective. Be clinical, specific, and in-character. "
            f"End with a single vote: APPROVE, REJECT, or ABSTAIN."
        )
        try:
            response = _llm(system_prompt, user_prompt)
        except Exception as e:
            response = f"[offline — {e}]\nVote: ABSTAIN"

        vote = "ABSTAIN"
        upper = response.upper()
        if "APPROVE" in upper:
            vote = "APPROVE"
        elif "REJECT" in upper:
            vote = "REJECT"

        return {
            "name":     name,
            "role":     role,
            "weight":   weight,
            "response": response,
            "vote":     vote,
        }

    # Run all 7 voices in parallel — reduces latency from 7× to ~1× LLM call time
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = {pool.submit(_deliberate_voice, item): item[0] for item in voice_items}
        results_by_name: Dict[str, Dict] = {}
        for future in as_completed(futures):
            result = future.result()
            results_by_name[result["name"]] = result

    # Preserve original voice order in output
    for name, _ in voice_items:
        v = results_by_name[name]
        voice_outputs.append(v)
        lines.append(f"  ------- {v['name']} -------")
        lines.append(f"  role   : {v['role']}")
        lines.append(f"  weight : {v['weight']:.2f}")
        lines.append(f"  vote   : {v['vote']}")
        lines.append(f"  \"{v['response'].strip()}\"")
        lines.append("")

    # Tally weighted votes
    approve_weight = sum(v["weight"] for v in voice_outputs if v["vote"] == "APPROVE")
    reject_weight  = sum(v["weight"] for v in voice_outputs if v["vote"] == "REJECT")
    total_weight   = approve_weight + reject_weight or 1.0
    approve_ratio  = approve_weight / total_weight

    if approve_ratio >= consensus_threshold:
        verdict = "APPROVED"
        verdict_detail = f"supermajority reached ({approve_ratio:.0%} weighted approval)"
    elif reject_weight / total_weight >= consensus_threshold:
        verdict = "REJECTED"
        verdict_detail = f"supermajority rejection ({reject_weight / total_weight:.0%} weighted rejection)"
    else:
        verdict = "DEADLOCKED"
        verdict_detail = f"no supermajority — approve {approve_ratio:.0%} / reject {reject_weight / total_weight:.0%}"

    lines += [
        "  ------- VERDICT -------",
        f"  result  : {verdict}",
        f"  detail  : {verdict_detail}",
        f"  approve : {approve_weight:.2f} weight ({sum(1 for v in voice_outputs if v['vote'] == 'APPROVE')} voices)",
        f"  reject  : {reject_weight:.2f} weight ({sum(1 for v in voice_outputs if v['vote'] == 'REJECT')} voices)",
        f"  abstain : {sum(1 for v in voice_outputs if v['vote'] == 'ABSTAIN')} voices",
    ]

    return "\n".join(lines)
