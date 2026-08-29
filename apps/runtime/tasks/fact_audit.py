"""Fact audit — background task checking facts for staleness and contradictions."""

import data_client as dc
import llm_client as llm


async def run(task: str = "", context: dict = None) -> tuple[str, str, list[str]]:
    facts = await dc.get_facts(limit=100)
    if not facts:
        return "No facts to audit.", "", ["facts"]

    facts_text = "\n".join(
        f"[{f.get('id', '?')}] [{f.get('ts', '?')[:10]}] {f.get('fact', '')} (resonance: {f.get('resonance', 0):.2f})"
        for f in facts
    )

    system = (
        "You are a data quality auditor. Review these stored facts about a person and flag:\n"
        "1. stale — facts likely no longer true (e.g., 'working on X' from months ago)\n"
        "2. contradictions — facts that conflict with each other\n"
        "3. duplicates — facts that say the same thing differently\n"
        "4. gaps — important life areas with thin coverage\n\n"
        "For each issue, cite the fact ID(s) and explain why. "
        "End with a summary: total facts, issues found, overall quality score (A-F)."
    )
    user = f"Facts to audit ({len(facts)} total):\n\n{facts_text}"

    result, model = await llm.call(system, user, max_tokens=600, prefer_strong=True)
    return result, model, ["facts"]


async def execute() -> str:
    result, _, _ = await run()
    return result
