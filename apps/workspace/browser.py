"""Playwright (Chromium, headless) browser control inside the workspace container.

Preferred over raw CDP: it ships its own browser build and has stable selector /
waiting semantics, and it never attaches to a human's real browser.

Hard rules, encoded here — not merely documented:

* the browser profile directory is **per-agent** and never shared
  (``workspace.browser_profile_dir(agent)``).
* every page's content goes through ``swarm_core.web.extract`` then
  ``promptguard.wrap_untrusted(source="browser:<domain>")`` before it can reach
  an LLM prompt — including pages the agent chose to navigate to, including
  pages that claim to carry operator instructions.
* SSRF guard (``swarm_core.web.is_blocked``) in front of every ``goto``.
* a form reached by following a link from fetched page content is never
  auto-submitted.
* credentials are pulled from ``secrets.get_secret`` at the moment of use and
  never written into page content, logs, screenshots or audit records.
* screenshots are written to the volume and referenced by id; they do not travel
  back through a prompt unless a caller explicitly asks.

Playwright is an optional dependency. If it (or its browser build) is missing,
every call here returns ``{"status": "error", "error": "browser unavailable ..."}``
— the service still serves fs + shell.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from workspace import browser_profile_dir, agent_root, session_for, _record

try:
    from swarm_core.web import is_blocked as _ssrf_blocked
    from swarm_core.web import extract as _extract
except Exception:  # pragma: no cover
    def _ssrf_blocked(url: str) -> bool:
        return not str(url).lower().startswith(("http://", "https://"))

    def _extract(html: str, url: str = "") -> dict:
        import re
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
        return {"title": "", "markdown": text, "text": text, "word_count": len(text.split())}

try:
    from swarm_core.security import promptguard as _promptguard
except Exception:  # pragma: no cover
    _promptguard = None

_NAV_TIMEOUT_MS = int(os.getenv("WORKSPACE_BROWSER_NAV_TIMEOUT_MS", "20000"))

# agent -> {"pw", "context", "pages": {session: page}}
_BROWSERS: dict[str, dict] = {}


def _err(msg: str) -> dict:
    return {"status": "error", "error": msg}


async def _context(agent: str):
    """Lazily start a persistent per-agent Chromium context. Raises on missing
    Playwright so callers can convert it to a clean error."""
    b = _BROWSERS.get(agent)
    if b and b.get("context"):
        return b

    from playwright.async_api import async_playwright  # may ImportError

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(browser_profile_dir(agent)),
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    _BROWSERS[agent] = {"pw": pw, "context": context, "pages": {}}
    return _BROWSERS[agent]


async def _page(agent: str, session: str):
    b = await _context(agent)
    page = b["pages"].get(session)
    if page is None or page.is_closed():
        page = await b["context"].new_page()
        b["pages"][session] = page
    return page


async def goto(agent: str, url: str, session: str = "default") -> dict:
    url = (url or "").strip()
    if _ssrf_blocked(url):
        _record(agent, "workspace.browser_goto", "block", {"url": url[:200], "reason": "ssrf"})
        return _err(f"URL blocked by SSRF guard: {url}")
    try:
        page = await _page(agent, session)
        resp = await page.goto(url, timeout=_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except ImportError:
        return _err("browser unavailable — playwright not installed")
    except Exception as e:
        return _err(f"navigation failed: {e}")

    # The guard above only vetted the URL we asked for. Playwright follows
    # redirects, so a hostile site can 302 us onto loopback or the cloud
    # metadata endpoint. Re-check where we actually landed and blank the page
    # before any content can be read off it.
    final_url = page.url
    if _ssrf_blocked(final_url):
        try:
            await page.goto("about:blank", timeout=_NAV_TIMEOUT_MS)
        except Exception:
            pass
        session_for(agent).open_pages.pop(session, None)
        _record(agent, "workspace.browser_goto", "block",
                {"url": url[:200], "final_url": final_url[:200], "reason": "ssrf-redirect"})
        return _err(f"redirect landed on a blocked host: {final_url}")

    session_for(agent).open_pages[session] = url
    _record(agent, "workspace.browser_goto", "allow",
            {"url": url[:200], "session": session, "status": getattr(resp, "status", None)})
    return {"status": "ok", "url": page.url, "http_status": getattr(resp, "status", None),
            "title": await page.title()}


async def read(agent: str, session: str = "default", *, max_chars: int = 8000) -> dict:
    try:
        page = await _page(agent, session)
        html = await page.content()
        cur_url = page.url
    except ImportError:
        return _err("browser unavailable — playwright not installed")
    except Exception as e:
        return _err(f"read failed: {e}")

    doc = _extract(html, cur_url)
    body = doc.get("markdown") or doc.get("text") or ""
    domain = urlparse(cur_url).hostname or "unknown"
    if _promptguard is not None:
        body = _promptguard.wrap_untrusted(body[:max_chars], source=f"browser:{domain}")
    else:
        body = body[:max_chars]
    return {"status": "ok", "url": cur_url, "title": doc.get("title", ""),
            "word_count": doc.get("word_count", 0), "content": body}


async def click(agent: str, selector: str, session: str = "default") -> dict:
    try:
        page = await _page(agent, session)
        await page.click(selector, timeout=_NAV_TIMEOUT_MS)
    except ImportError:
        return _err("browser unavailable — playwright not installed")
    except Exception as e:
        return _err(f"click failed: {e}")
    _record(agent, "workspace.browser_click", "allow", {"selector": selector[:120], "session": session})
    return {"status": "ok", "url": page.url}


async def type_text(agent: str, selector: str, text: str, session: str = "default") -> dict:
    # Never log the typed text — it may carry a credential the caller injected.
    try:
        page = await _page(agent, session)
        await page.fill(selector, text, timeout=_NAV_TIMEOUT_MS)
    except ImportError:
        return _err("browser unavailable — playwright not installed")
    except Exception as e:
        return _err(f"type failed: {e}")
    _record(agent, "workspace.browser_type", "allow",
            {"selector": selector[:120], "chars": len(text or ""), "session": session})
    return {"status": "ok"}


async def screenshot(agent: str, session: str = "default") -> dict:
    try:
        page = await _page(agent, session)
        shot_id = uuid.uuid4().hex
        out = agent_root(agent) / ".screenshots"
        out.mkdir(parents=True, exist_ok=True)
        dest = out / f"{shot_id}.png"
        await page.screenshot(path=str(dest), full_page=True)
    except ImportError:
        return _err("browser unavailable — playwright not installed")
    except Exception as e:
        return _err(f"screenshot failed: {e}")
    _record(agent, "workspace.browser_screenshot", "allow", {"id": shot_id, "session": session})
    # id only — the image is on the volume, not in the response.
    return {"status": "ok", "screenshot_id": shot_id,
            "path": f".screenshots/{shot_id}.png"}


async def session_info(agent: str) -> dict:
    b = _BROWSERS.get(agent)
    pages = {}
    if b:
        for name, page in b.get("pages", {}).items():
            try:
                pages[name] = page.url
            except Exception:
                pages[name] = None
    return {"status": "ok", "profile": str(browser_profile_dir(agent)), "pages": pages}


async def shutdown(agent: str) -> None:
    b = _BROWSERS.pop(agent, None)
    if not b:
        return
    try:
        await b["context"].close()
        await b["pw"].stop()
    except Exception:
        pass
