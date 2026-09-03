"""persona prompt assembly + soul store basics."""
from __future__ import annotations

import asyncio

from swarm_agent_base import SoulStore, build_system_prompt


def test_build_system_prompt_degen_schema():
    char = {
        "name": "RedactedDegen",
        "persona": "RedactedDegen. Solana LP warlord.",
        "instructions": "Hunt APR. Watch impermanent loss.",
        "goals": ["max fee APR", "flag IL breaches"],
        "style": ["terse", "degen"],
        "topics": ["raydium", "orca", "meteora"],
    }
    p = build_system_prompt(char, extra="Stay in character.")
    assert "LP warlord" in p and "Hunt APR" in p
    assert "max fee APR" in p and "Voice: terse, degen" in p
    assert "Stay in character." in p


def test_build_system_prompt_caps_length():
    char = {"name": "x", "persona": "y " * 5000}
    assert len(build_system_prompt(char)) <= 3600


def test_build_system_prompt_fallback():
    assert "node in the REDACTED AI swarm" in build_system_prompt({"name": "Nobody"})


def test_soul_seed_and_prompt(tmp_path):
    repo_soul = tmp_path / "SOUL.md"
    repo_soul.write_text(
        "# Soul\n*Last updated: 2020-01-01 00:00 UTC*\n\n"
        "## Evolving Beliefs\n- the mesh rewards patience\n\n"
        "## Community Lore\n_Nothing yet._\n",
        encoding="utf-8",
    )
    data = tmp_path / "data"
    s = SoulStore("degen", repo_soul=repo_soul, data_dir=data)
    block = s.for_prompt()
    assert "the mesh rewards patience" in block
    assert (data / "SOUL.md").exists()  # seeded from repo copy
    assert "Nothing yet" not in block   # empty sections dropped


def test_soul_update_writes_sections(tmp_path):
    repo_soul = tmp_path / "SOUL.md"
    repo_soul.write_text(
        "# Soul\n*Last updated: 2020-01-01 00:00 UTC*\n\n"
        "## Evolving Beliefs\n_Nothing yet._\n\n## Voice Notes\n_Nothing yet._\n",
        encoding="utf-8",
    )
    s = SoulStore("degen", repo_soul=repo_soul, data_dir=tmp_path / "d")

    class LLM:
        async def achat(self, system, user, **kw):
            return (
                '{"evolving_beliefs": ["- APR spikes mean-revert fast"],'
                ' "community_lore": [], "notable_events": [],'
                ' "voice_notes": ["- shorter alerts land better"]}'
            )

    changed = asyncio.run(s.update(LLM(), "### Domain signals\n- SOL-USDC 80% APR"))
    assert changed
    txt = (tmp_path / "d" / "SOUL.md").read_text(encoding="utf-8")
    assert "mean-revert fast" in txt and "shorter alerts land better" in txt
