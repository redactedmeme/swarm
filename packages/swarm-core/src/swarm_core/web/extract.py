"""Readable-content extraction.

``extract(html, url)`` -> ``{"title", "markdown", "text", "word_count"}``

Primary path is `trafilatura` (optional extra ``swarm-core[web]``): it removes
nav chrome, cookie banners and script bodies and emits markdown directly. When
trafilatura is not installed, or returns nothing usable, fall back to the same
regex tag-strip the call sites used before. umbrel images must not hard-fail on
a missing wheel — the fallback is load-bearing, not politeness.

The result is still untrusted text. Callers MUST pass it through
``swarm_core.security.promptguard.wrap_untrusted`` before it reaches a prompt.
"""
from __future__ import annotations

import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|template)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

try:  # optional
    import trafilatura as _trafilatura
except Exception:  # pragma: no cover - absence is a supported state
    _trafilatura = None


def _regex_fallback(html: str) -> tuple[str, str]:
    """Return (title, text) from a naive strip. Never raises."""
    html = html or ""
    m = _TITLE_RE.search(html)
    title = _WS_RE.sub(" ", _TAG_RE.sub(" ", m.group(1))).strip() if m else ""
    body = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", body)).strip()
    return title, text


def extract(html: str, url: str = "") -> dict:
    """Extract readable content from an HTML document.

    Always returns the full dict shape; falls back to a regex strip when
    trafilatura is unavailable or yields nothing.
    """
    html = html or ""
    title = ""
    markdown = ""
    text = ""

    if _trafilatura is not None and html.strip():
        try:
            markdown = (
                _trafilatura.extract(
                    html,
                    url=url or None,
                    output_format="markdown",
                    include_links=False,
                    include_images=False,
                    favor_precision=True,
                )
                or ""
            ).strip()
            text = (
                _trafilatura.extract(
                    html,
                    url=url or None,
                    output_format="txt",
                    include_links=False,
                    include_images=False,
                    favor_precision=True,
                )
                or ""
            ).strip()
            try:
                meta = _trafilatura.extract_metadata(html)
                if meta and getattr(meta, "title", None):
                    title = (meta.title or "").strip()
            except Exception:
                pass
        except Exception:
            markdown = text = ""

    if not text:
        fb_title, fb_text = _regex_fallback(html)
        title = title or fb_title
        text = fb_text
        markdown = markdown or fb_text
    elif not markdown:
        markdown = text

    if not title:
        fb_title, _ = _regex_fallback(html)
        title = fb_title

    return {
        "title": title,
        "markdown": markdown,
        "text": text,
        "word_count": len(text.split()),
    }
