"""leakscan: does it catch real secret shapes and leave prose alone?"""
from __future__ import annotations

from swarm_core.security import leakscan


def test_catches_provider_keys():
    samples = {
        "openai_key": "here is the key sk-proj-abcd1234EFGH5678ijkl9012mnop",
        "anthropic_key": "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFFGGGG1234",
        "xai_key": "xai-abcdefghijklmnopqrstuvwxyz012345",
        "groq_key": "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "github_token": "ghp_" + "a" * 36,
        "aws_access_key": "creds AKIAZ7XYQR3PLMNO2WVB here",
    }
    for expected_rule, text in samples.items():
        matches = leakscan.scan(text)
        assert matches, f"{expected_rule}: nothing matched in {text!r}"
        assert any(m.rule == expected_rule for m in matches), (
            f"{expected_rule}: got {[m.rule for m in matches]}"
        )
        assert leakscan.worst(matches) == "block"


def test_pem_and_mnemonic_block():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1r\n-----END"
    assert leakscan.worst(leakscan.scan(pem)) == "block"
    mnemonic = "legal winner thank year wave sausage worth useful legal winner thank yellow"
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
    text = "curl -H 'Authorization: Bearer sk-proj-abcd1234EFGH5678ijkl9012'"
    clean, matches = leakscan.redact(text)
    assert "sk-proj-abcd1234" not in clean
    assert "redacted-secret" in clean
    assert matches


def test_scan_never_raises_on_junk():
    for junk in (None, "", 12345, b"bytes", {"a": 1}):
        leakscan.scan(junk)  # type: ignore[arg-type]
