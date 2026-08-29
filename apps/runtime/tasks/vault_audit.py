"""Vault audit — background task scanning for duplicates and overlaps."""

import data_client as dc
import llm_client as llm


async def run(task: str = "", context: dict = None) -> tuple[str, str, list[str]]:
    entries = await dc.get_vault_entries(n=50)
    if not entries:
        return "No vault entries to audit.", "", ["vault"]

    entries_text = "\n".join(
        f"[{e.get('id', '?')}] [{e.get('ts', '?')[:10]}] ({e.get('category', '?')}) "
        f"{e.get('title', 'untitled')}: {e.get('content', '')[:200]}"
        for e in entries
    )

    system = (
        "You are a memory curator auditing a relationship vault. Review these entries and identify:\n"
        "1. duplicates — entries describing the same moment or fact\n"
        "2. overlaps — entries that could be merged into one richer entry\n"
        "3. outdated — entries that may no longer be accurate\n"
        "4. underrepresented — categories with few entries that could use more\n\n"
        "For each issue, cite entry IDs. End with a summary: total entries, "
        "category distribution, issues found, recommended actions."
    )
    user = f"Vault entries to audit ({len(entries)} total):\n\n{entries_text}"

    result, model = await llm.call(system, user, max_tokens=600, prefer_strong=True)
    return result, model, ["vault"]


async def execute() -> str:
    result, _, _ = await run()
    return result
