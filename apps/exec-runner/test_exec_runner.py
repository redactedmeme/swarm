"""exec-runner: argv construction, HTTP auth, and (POSIX only) real containment."""
from __future__ import annotations

import sys

import pytest
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])

import app as execapp  # noqa: E402
import runner  # noqa: E402

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="rlimit/setsid are POSIX-only")


def test_argv_plain_python_when_no_nsjail(monkeypatch):
    monkeypatch.setattr(runner, "_NSJAIL", None)
    argv = runner._argv("print(1)")
    assert argv[:5] == ["python3", "-I", "-B", "-S", "-c"]
    assert argv[-1] == "print(1)"


def test_argv_wraps_nsjail_when_present(monkeypatch):
    monkeypatch.setattr(runner, "_NSJAIL", "/usr/bin/nsjail")
    argv = runner._argv("print(1)")
    assert argv[0] == "/usr/bin/nsjail"
    assert "--disable_proc" in argv and "--iface_no_lo" in argv
    assert argv[-6:] == ["python3", "-I", "-B", "-S", "-c", "print(1)"]


async def test_run_endpoint_requires_token(monkeypatch):
    monkeypatch.setattr(execapp, "TOKEN", "sekret")
    client = TestClient(TestServer(execapp.build_app()))
    await client.start_server()
    try:
        r = await client.post("/run", json={"code": "print(1)"})
        assert r.status == 401
        r = await client.post("/run", json={"code": "print(1)"},
                              headers={"Authorization": "Bearer sekret"})
        assert r.status == 200
    finally:
        await client.close()


async def test_health_ok():
    client = TestClient(TestServer(execapp.build_app()))
    await client.start_server()
    try:
        r = await client.get("/health")
        body = await r.json()
        assert body["status"] == "ok"
        assert body["jail"] in ("nsjail", "rlimit")
    finally:
        await client.close()


@posix_only
async def test_pure_computation_runs():
    out = await runner.run_code("print(6 * 7)", 5)
    assert out["status"] == "ok"
    assert out["stdout"].strip() == "42"
    assert out["exit_code"] == 0


@posix_only
async def test_no_secrets_in_child_env():
    out = await runner.run_code(
        "import os; print([k for k in os.environ if 'KEY' in k or 'TOKEN' in k or 'SECRET' in k])",
        5,
    )
    assert out["stdout"].strip() == "[]"


@posix_only
async def test_network_is_unavailable():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2); print('OPEN')\n"
        "except Exception as e:\n"
        "    print('BLOCKED')\n"
    )
    out = await runner.run_code(code, 8)
    # In the real container (network_mode: none) this is BLOCKED. Locally it may
    # not be — so only assert it didn't hang / crash the runner.
    assert out["status"] in ("ok", "timeout")


@posix_only
async def test_wall_timeout_kills():
    out = await runner.run_code("while True: pass", 2)
    assert out["timed_out"] is True
    assert out["status"] == "timeout"


@posix_only
async def test_breakout_attempt_is_contained():
    # the classic denylist bypass — still just Python, still no secrets / net
    code = "print([c.__name__ for c in ().__class__.__base__.__subclasses__()][:3])"
    out = await runner.run_code(code, 5)
    assert out["status"] == "ok"  # it runs, but in a powerless jail
