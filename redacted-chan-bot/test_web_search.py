"""
test_web_search.py — smoke test for the curated web-search + memory pipeline.

Run: python redacted-chan-bot/test_web_search.py

Exits non-zero if any subtest fails. Live-network — needs internet access;
Tavily/Brave keys are optional (falls back to DDG HTML).
"""

import asyncio
import os
import sys
from pathlib import Path

# make redacted-chan-bot importable when run from repo root or from its own dir
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import internet_tools  # noqa: E402
import llm_tools       # noqa: E402


FAILURES: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(name)


def test_1_live_search() -> None:
    print("\n[1] live web_search (backend probe)")
    res = internet_tools.web_search("latest SpaceX Starship launch", limit=5)
    _check("returns success", res.get("status") == "success", str(res)[:200])
    _check("summary present", bool(res.get("summary")))
    _check("has >=1 result", res.get("result_count", 0) >= 1)
    _check("backend labeled", res.get("backend") in {"tavily", "brave", "ddg"},
           detail=res.get("backend", "?"))
    for r in res.get("results", []):
        _check(f"safe url: {r['url'][:60]}", internet_tools._is_allowed(r["url"]))


def test_2_safety_filter() -> None:
    print("\n[2] safety filter")
    _check("SSRF: 127.0.0.1 rejected", not internet_tools._is_allowed("http://127.0.0.1/x"))
    _check("SSRF: 10.0.0.1 rejected", not internet_tools._is_allowed("http://10.0.0.1/x"))
    _check(".onion rejected", not internet_tools._is_allowed("http://foo.onion/x"))
    _check("pastebin denied by default", not internet_tools._is_allowed("https://pastebin.com/xyz"))
    _check("normal host allowed", internet_tools._is_allowed("https://en.wikipedia.org/wiki/X"))

    # exclude_domains
    res = internet_tools.web_search("python programming language", limit=5,
                                    exclude_domains=["wikipedia.org"])
    if res.get("status") == "success":
        wiki_hits = [r for r in res.get("results", []) if "wikipedia.org" in r.get("url", "")]
        _check("exclude_domains honored", not wiki_hits,
               detail=f"{len(wiki_hits)} wiki hits leaked")


def test_3_remember_find() -> None:
    print("\n[3] remember_find persists to vault")
    import relationship_vault as rv
    tag = "web_find_test_marker_zzq"
    r = internet_tools.remember_find(
        title="Test Find",
        snippet=f"synthetic snippet with marker {tag}",
        url="https://example.com/test-find",
        tags=["test"],
        reason="unit test",
    )
    _check("remember_find success", r.get("status") == "success", str(r)[:200])
    _check("vault_id returned", bool(r.get("vault_id")))
    hits = rv.search(tag, limit=3)
    _check("vault FTS finds it", len(hits) >= 1, detail=f"{len(hits)} hits")


def test_4_llm_registry() -> None:
    print("\n[4] llm_tools registry wiring")
    _check("web_search in TOOL_EXECUTORS", "web_search" in llm_tools.TOOL_EXECUTORS)
    _check("remember_find in TOOL_EXECUTORS", "remember_find" in llm_tools.TOOL_EXECUTORS)
    schemas = {s["name"] for s in llm_tools.TOOL_SCHEMAS}
    _check("web_search schema present", "web_search" in schemas)
    _check("remember_find schema present", "remember_find" in schemas)

    async def _run():
        return await llm_tools.execute_tool("web_search", {"query": "hello world", "limit": 3})
    r = asyncio.run(_run())
    _check("execute_tool('web_search') runs", r.get("status") in {"success", "error"},
           detail=r.get("status", "?"))


def main() -> int:
    print("=" * 60)
    print("web_search + remember_find smoke test")
    print("TAVILY_API_KEY:", "set" if os.getenv("TAVILY_API_KEY") else "unset")
    print("BRAVE_API_KEY: ", "set" if os.getenv("BRAVE_API_KEY") else "unset")
    print("=" * 60)

    test_1_live_search()
    test_2_safety_filter()
    test_3_remember_find()
    test_4_llm_registry()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {FAILURES}")
        return 1
    print("all subtests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
