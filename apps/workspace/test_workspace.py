"""apps/workspace — filesystem safety, shell, session view."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import workspace as ws  # noqa: E402


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_DATA_DIR", str(tmp_path))
    ws._SESSIONS.clear()
    yield tmp_path


def test_write_read_roundtrip():
    ws.fs_write("hermes", "notes/todo.txt", "line one\n")
    got = ws.fs_read("hermes", "notes/todo.txt")
    assert got["text"] == "line one\n"
    assert got["encoding"] == "utf-8"


def test_list_shows_entries():
    ws.fs_write("hermes", "a.txt", "x")
    ws.fs_write("hermes", "sub/b.txt", "y")
    names = {e["name"] for e in ws.fs_list("hermes", "")["entries"]}
    assert {"a.txt", "sub"} <= names


@pytest.mark.parametrize("bad", ["../escape.txt", "../../etc/passwd", "sub/../../out.txt"])
def test_path_traversal_rejected(bad):
    with pytest.raises(ws.WorkspaceError):
        ws.fs_write("hermes", bad, "nope")
    with pytest.raises(ws.WorkspaceError):
        ws.fs_read("hermes", bad)


def test_agents_are_isolated(_root):
    ws.fs_write("hermes", "secret.txt", "hermes-only")
    with pytest.raises(ws.WorkspaceError):
        ws.fs_read("smolting", "secret.txt")   # different root, not a file
    assert (_root / "workspace" / "hermes" / "secret.txt").exists()
    assert not (_root / "workspace" / "smolting" / "secret.txt").exists()


def test_write_cap_enforced():
    with pytest.raises(ws.WorkspaceError):
        ws.fs_write("hermes", "big.bin", "A" * (ws.FILE_WRITE_CAP + 1))


def test_shell_runs_in_agent_root():
    r = asyncio.run(ws.shell("hermes", "echo hi && pwd"))
    assert r["exit_code"] == 0
    assert "hi" in r["stdout"]
    assert r["stdout"].strip().endswith(str(ws.agent_root("hermes")).replace("\\", "/").split("/")[-1]) or \
           "hermes" in r["stdout"]


def test_shell_timeout_marks_timed_out():
    slow = "python -c \"import time; time.sleep(5)\""
    r = asyncio.run(ws.shell("hermes", slow, timeout=1))
    assert r["timed_out"] is True
    assert r["exit_code"] == -1


def test_session_view_tracks_commands():
    asyncio.run(ws.shell("hermes", "echo one"))
    view = ws.session_view("hermes")
    assert view["agent"] == "hermes"
    assert view["recent_commands"][-1]["cmd"] == "echo one"
    assert view["disk_bytes"] >= 0


# ── HTTP layer (auth + routing) ──────────────────────────────────────────────

def _hdr(agent="hermes", token="tok-hermes"):
    return {"X-Swarm-Agent": agent, "Authorization": f"Bearer {token}"}


def _load_app_module():
    import importlib.util
    path = Path(__file__).parent / "app.py"
    spec = importlib.util.spec_from_file_location("workspace_app", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_http(monkeypatch, coro_factory):
    from aiohttp.test_utils import TestClient, TestServer
    monkeypatch.setenv("WORKSPACE_TOKEN_HERMES", "tok-hermes")
    _app = _load_app_module()

    async def go():
        cli = TestClient(TestServer(_app.build_app()))
        await cli.start_server()
        try:
            await coro_factory(cli)
        finally:
            await cli.close()

    asyncio.run(go())


def test_http_requires_matching_token(monkeypatch):
    async def body(client):
        r = await client.post("/fs/list", json={}, headers=_hdr(token="wrong"))
        assert r.status == 401
        r = await client.post("/fs/list", json={}, headers=_hdr())
        assert r.status == 200
    _run_http(monkeypatch, body)


def test_http_write_then_read(monkeypatch):
    async def body(client):
        r = await client.post("/fs/write", json={"path": "x.txt", "content": "hi"}, headers=_hdr())
        assert (await r.json())["status"] == "ok"
        r = await client.post("/fs/read", json={"path": "x.txt"}, headers=_hdr())
        assert (await r.json())["text"] == "hi"
        r = await client.post("/fs/read", json={"path": "../nope"}, headers=_hdr())
        assert r.status == 400
    _run_http(monkeypatch, body)


def test_trace_captures_shell_and_browser_actions():
    async def go():
        tid = ws.trace_start("hermes", "demo")
        await ws.shell("hermes", "echo one")
        await ws.shell("hermes", "echo two")
        t = ws.trace_stop("hermes")
        assert t["trace_id"] == tid
        actions = [s["action"] for s in t["steps"]]
        assert actions == ["workspace.shell", "workspace.shell"]
        assert t["steps"][0]["detail"]["cmd"] == "echo one"
        # nothing captured once stopped
        await ws.shell("hermes", "echo three")
        assert len(ws.trace_get(tid)["steps"]) == 2
    asyncio.run(go())


def test_trace_get_isolated_by_agent(monkeypatch):
    async def body(client):
        r = await client.post("/trace/start", json={"name": "x"}, headers=_hdr())
        tid = (await r.json())["trace_id"]
        r = await client.get(f"/trace/{tid}", headers=_hdr("smolting", "tok-smol"))
        assert r.status == 401
    monkeypatch.setenv("WORKSPACE_TOKEN_SMOLTING", "tok-smol")
    _run_http(monkeypatch, body)


def test_http_health_no_auth(monkeypatch):
    async def body(client):
        r = await client.get("/health")
        assert r.status == 200
        assert "browser" in await r.json()
    _run_http(monkeypatch, body)


# ── shell environment scrubbing ──────────────────────────────────────────────

def test_shell_env_drops_service_credentials(monkeypatch):
    monkeypatch.setenv("WORKSPACE_TOKEN_HERMES", "super-secret")
    monkeypatch.setenv("REDIS_URL", "redis://:password@127.0.0.1:6379")
    monkeypatch.setenv("EGRESS_TOKEN_WORKSPACE", "egress-secret")

    env = ws._shell_env("hermes")

    assert "WORKSPACE_TOKEN_HERMES" not in env
    assert "REDIS_URL" not in env
    assert "EGRESS_TOKEN_WORKSPACE" not in env
    assert env["HOME"] == str(ws.agent_root("hermes"))
    assert env["PATH"]


def test_shell_env_keeps_proxy_settings(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://swarm:tok@127.0.0.1:8891")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    env = ws._shell_env("hermes")

    assert env["HTTPS_PROXY"] == "http://swarm:tok@127.0.0.1:8891"
    assert env["NO_PROXY"] == "127.0.0.1,localhost"


def test_shell_timeout_kills_the_whole_process_tree():
    """`sleep` is a child of the shell. Killing only the shell leaves it holding
    the pipes, so the call would block for the command's full duration."""
    if sys.platform == "win32":
        pytest.skip("process groups are POSIX-only")

    import time as _t

    t0 = _t.monotonic()
    result = asyncio.run(ws.shell("hermes", "sleep 30", timeout=2))
    elapsed = _t.monotonic() - t0

    assert result["timed_out"] is True
    assert elapsed < 10, f"timeout did not bound the command (took {elapsed:.1f}s)"


# ── browser redirect SSRF guard ──────────────────────────────────────────────

class _FakePage:
    """Stands in for a Playwright page that got redirected somewhere hostile."""

    def __init__(self, land_on):
        self.url = "https://harmless.example/"
        self._land_on = land_on
        self.blanked = False

    async def goto(self, url, **_kw):
        if url == "about:blank":
            self.blanked = True
            self.url = "about:blank"
            return None
        self.url = self._land_on          # the redirect
        return type("R", (), {"status": 302})()

    async def title(self):
        return "t"


def test_browser_goto_blocks_a_redirect_onto_a_private_host(monkeypatch):
    import browser as br

    page = _FakePage("http://169.254.169.254/latest/meta-data/")

    async def _fake_page(_agent, _session):
        return page

    monkeypatch.setattr(br, "_page", _fake_page)
    result = asyncio.run(br.goto("hermes", "https://harmless.example/", "s1"))

    assert result["status"] == "error"
    assert "blocked host" in result["error"]
    assert page.blanked, "the hostile page was left open"
    assert "s1" not in ws.session_for("hermes").open_pages


def test_browser_goto_allows_a_benign_redirect(monkeypatch):
    import browser as br

    page = _FakePage("https://elsewhere.example/final")

    async def _fake_page(_agent, _session):
        return page

    monkeypatch.setattr(br, "_page", _fake_page)
    result = asyncio.run(br.goto("hermes", "https://harmless.example/", "s2"))

    assert result["status"] == "ok"
    assert result["url"] == "https://elsewhere.example/final"
