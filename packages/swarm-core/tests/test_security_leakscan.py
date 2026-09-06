"""leakscan: does it catch real secret shapes and leave prose alone?"""
from __future__ import annotations

from swarm_core.security import leakscan


def test_catches_provider_keys():
    samples = {
        "openai_key": "here is the key sk-proj-abcd1234EFGH5678ijkl9012mnop",  # leakscan: allow
        "anthropic_key": "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFFGGGG1234",  # leakscan: allow
        "xai_key": "xai-abcdefghijklmnopqrstuvwxyz012345",  # leakscan: allow
        "groq_key": "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",  # leakscan: allow
        "github_token": "ghp_" + "a" * 36,
        "aws_access_key": "creds AKIAZ7XYQR3PLMNO2WVB here",  # leakscan: allow
    }
    for expected_rule, text in samples.items():
        matches = leakscan.scan(text)
        assert matches, f"{expected_rule}: nothing matched in {text!r}"
        assert any(m.rule == expected_rule for m in matches), (
            f"{expected_rule}: got {[m.rule for m in matches]}"
        )
        assert leakscan.worst(matches) == "block"


def test_pem_and_mnemonic_block():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1r\n-----END"  # leakscan: allow
    assert leakscan.worst(leakscan.scan(pem)) == "block"
    mnemonic = "legal winner thank year wave sausage worth useful legal winner thank yellow"  # leakscan: allow
    assert any(m.rule == "bip39_mnemonic" for m in leakscan.scan(mnemonic))


def test_prose_is_clean():
    prose = (
        "The swarm orchestrator decomposes a task into at most five subtasks and "
        "routes each to the agent whose capabilities match. Nothing secret here."
    )
    assert leakscan.scan(prose) == []


def test_allowlist_suppresses_examples():
    assert leakscan.scan("set OPENAI_API_KEY=sk-your-key-here in the .env") == []
    assert leakscan.scan("example: sk-proj-" + "x" * 24) == []


def test_redact_masks_and_reports():
    text = "curl -H 'Authorization: Bearer sk-proj-abcd1234EFGH5678ijkl9012'"  # leakscan: allow
    clean, matches = leakscan.redact(text)
    assert "sk-proj-abcd1234" not in clean
    assert "redacted-secret" in clean
    assert matches


def test_scan_never_raises_on_junk():
    for junk in (None, "", 12345, b"bytes", {"a": 1}):
        leakscan.scan(junk)  # type: ignore[arg-type]


# ── Hardening added after the 2026-09 review ─────────────────────────────────
# The provider-prefix rules only cover providers we thought of. These cover the
# shapes this repo actually stores, plus the false positives that made the
# first attempt unusable.

def _blocked(text: str) -> list[str]:
    return [m.rule for m in leakscan.scan(text) if m.severity == "block"]


def test_solana_base58_secret_key_is_blocked():
    # The export form of a keypair; the JSON-array rule does not see this.
    key = "4NMwxzmYj2uvHuq8xoqhY8RXg63KSVJM1DXkpbmkUY7YQWuoyQgFnnzn6yo3CMnqZasnNPNuAT2TLwQsCaKkUddg"  # leakscan: allow
    assert "solana_base58_key" in _blocked(key)


def test_secret_named_variable_with_a_literal_is_blocked():
    # Catches providers with no prefix rule: the wallet KEK, the inbox HMAC
    # key, a Railway token, a WireGuard private key.
    for line in (
        "SWARM_WALLET_KEK=dGhpc19pc19hcmVhbF9rZWtfdmFsdWVfMzJieXRlcw=",   # leakscan: allow
        "SWARM_INBOX_HMAC_KEY=9f8e7d6c5b4a39281706f5e4d3c2b1a09f8e7d6c5b4a39281706f5e4d3c2b1a0",  # leakscan: allow
        "RAILWAY_TOKEN=8f3a91c2-4d5e-4b7a-9c1d-2e3f4a5b6c7d",  # leakscan: allow
        "PrivateKey = mB1s8QweRtYu0PaSdFgHjKlZxCvBnM2345678aBcDe=",  # leakscan: allow
    ):
        assert "assigned_secret" in _blocked(line), line


def test_secret_named_variable_ignores_references_and_identifiers():
    # These are what made the rule unusable at first: it fired on ordinary
    # code, on env-var NAMES, on paths, and on documented placeholders.
    for line in (
        "TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}",
        'TOKEN = os.getenv("BUILDER_BOT_TOKEN")',
        "self.api_key = self._get_api_key()",
        "is_buy_token = compute_rebalance_delta(sol_balance, price)",
        "api.telegram.org: { secret: TELEGRAM_BOT_TOKEN, mode: path_bot }",
        "SWARM_SECRETS_FILE=/run/secrets/swarm.env",
        "OPENAI_API_KEY=your_openai_api_key_here",
        "BUILDER_BOT_TOKEN=",
    ):
        assert "assigned_secret" not in _blocked(line), line


def test_mnemonic_rule_does_not_fire_on_english_prose():
    # The shape rule is a run of lowercase words, which is also a sentence.
    # At block severity that refused ordinary documentation commits.
    prose = (
        "These myths are not fixed they represent the current compilation of "
        "what the manifold expands into over the course of a long project"
    )
    assert "bip39_mnemonic" not in _blocked(prose)


def test_mnemonic_rule_still_catches_a_real_mnemonic():
    # Regression guard for the above: the prose fix must not blind the rule.
    words = "legal winner thank year wave sausage worth useful legal winner thank yellow"  # leakscan: allow
    assert "bip39_mnemonic" in _blocked(words)
