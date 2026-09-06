"""swarm_core.web — readable extraction + SSRF guard."""
from __future__ import annotations

import re

import pytest

import importlib

extract_mod = importlib.import_module("swarm_core.web.extract")
extract = extract_mod.extract
from swarm_core.web.ssrf import is_blocked

_FIXTURE = """<!DOCTYPE html>
<html><head><title>The Real Article — Example</title>
<style>.nav{color:red}</style>
<script>window.__TRACK__ = "GARBAGENAVSCRIPTTOKEN"; analytics.push(1);</script>
</head><body>
<nav class="nav">HOME PRODUCTS PRICING BLOG CONTACT LOGIN SIGN UP</nav>
<div id="cookie-banner">We value your privacy. This site uses COOKIECONSENT cookies. Accept all.</div>
<header>MEGAMENU NEWSLETTER SUBSCRIBE</header>
<main><article>
<h1>The Real Article</h1>
<p>Hyperbolic tilings partition the Poincare disk into congruent cells. The {7,3}
tiling places seven heptagons around every vertex, and its dual is the {3,7}.</p>
<p>Each successive ring of cells grows exponentially in count, which is what makes
the manifold useful as an addressing scheme for a large agent population.</p>
</article></main>
<footer>COPYRIGHT 2026 ALLRIGHTSRESERVED PRIVACY TERMS SITEMAP</footer>
</body></html>"""

_NAV_STRINGS = ["COOKIECONSENT", "MEGAMENU", "ALLRIGHTSRESERVED", "GARBAGENAVSCRIPTTOKEN"]


def _regex_strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


@pytest.mark.skipif(extract_mod._trafilatura is None, reason="trafilatura not installed")
def test_extract_drops_chrome_and_keeps_article():
    doc = extract(_FIXTURE, "https://example.com/article")
    assert doc["title"].startswith("The Real Article")
    assert "heptagons around every vertex" in doc["text"]
    for junk in _NAV_STRINGS:
        assert junk not in doc["text"], f"{junk} leaked into extracted text"
    # cleaner text is *shorter* than the naive strip (which keeps nav + script)
    assert doc["word_count"] < len(_regex_strip(_FIXTURE).split())
    assert doc["word_count"] > 30
    assert doc["markdown"]


def test_fallback_when_trafilatura_absent(monkeypatch):
    monkeypatch.setattr(extract_mod, "_trafilatura", None)
    doc = extract(_FIXTURE, "https://example.com/article")
    assert doc["text"], "regex fallback must return non-empty text"
    assert doc["word_count"] > 0
    assert doc["markdown"] == doc["text"]
    # script/style bodies are stripped even on the fallback path
    assert "GARBAGENAVSCRIPTTOKEN" not in doc["text"]
    assert doc["title"] == "The Real Article — Example"


def test_extract_never_raises_on_junk():
    for bad in ["", "   ", "<html", "not html at all", "<title>x</title>"]:
        doc = extract(bad, "")
        assert set(doc) == {"title", "markdown", "text", "word_count"}


def test_ssrf_guard():
    for blocked in [
        "http://localhost/x", "https://127.0.0.1", "http://10.1.2.3/a",
        "http://192.168.0.1", "https://169.254.169.254/latest/meta-data",
        "http://foo.internal/", "https://metadata.google.internal",
        "http://172.16.0.1", "http://172.31.255.255", "ftp://example.com",
        "file:///etc/passwd", "example.com",
    ]:
        assert is_blocked(blocked), blocked
    for ok in [
        "https://example.com", "http://93.184.216.34/", "https://arxiv.org/abs/1",
        "http://172.15.0.1", "http://172.32.0.1",
    ]:
        assert not is_blocked(ok), ok
