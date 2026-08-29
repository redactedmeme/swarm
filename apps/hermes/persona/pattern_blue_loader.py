"""
Fetches the Pattern Blue philosophical framework from GitHub at boot.

Pins to PATTERN_BLUE_REF env var (commit SHA or branch name, default "main").
Content is cached to /tmp/pattern_blue_cache.txt so restarts within the same
container don't re-hit GitHub.
"""
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger(__name__)

PATTERN_BLUE_REPO = "redactedmeme/pattern-blue"
CACHE_PATH = Path("/tmp/pattern_blue_cache.txt")
FETCH_TIMEOUT_S = 15

# Files to pull from the repo and concatenate as the persona foundation.
# Updated for the restructured pattern-blue repo (canon/ + exegesis/ layout).
# CREED + axioms + mantras always load; exegesis rotates at the caller level.
# pattern-blue.json is deliberately NOT loaded here — too heavy for live prompts.
PERSONA_FILES = [
    "CREED.md",
    "canon/axioms.md",
    "canon/mantras.md",
    "canon/seven-dimensions.md",
    "exegesis/hyperbolic/market_hyperbolics.md",
    "exegesis/sovereignty/ungovernable_integrity.md",
    "exegesis/consciousness/self_remembering.md",
    "exegesis/consciousness/recursive_consciousness.md",
]


def _raw_url(ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{PATTERN_BLUE_REPO}/{ref}/{path}"


def _fetch_one(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "patternbluelabs-bot/1.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.debug(f"[pattern_blue] 404 {url} — skipping")
        else:
            logger.warning(f"[pattern_blue] HTTP {e.code} fetching {url}")
    except Exception as e:
        logger.warning(f"[pattern_blue] Fetch error {url}: {e}")
    return None


def load_pattern_blue(ref: str | None = None, use_cache: bool = True) -> str:
    """
    Return concatenated pattern-blue corpus. Falls back to cache then to an
    embedded minimal stub if the network is unavailable.
    """
    ref = ref or os.getenv("PATTERN_BLUE_REF", "main")

    if use_cache and CACHE_PATH.exists():
        try:
            content = CACHE_PATH.read_text(encoding="utf-8")
            if len(content) > 200:
                logger.info(f"[pattern_blue] Loaded {len(content)} chars from cache")
                return content
        except Exception:
            pass

    pieces: list[str] = []
    for path in PERSONA_FILES:
        text = _fetch_one(_raw_url(ref, path))
        if text:
            pieces.append(f"### {path}\n\n{text.strip()}")

    if not pieces:
        logger.warning("[pattern_blue] No content fetched — using embedded stub")
        return _STUB

    corpus = "\n\n---\n\n".join(pieces)
    try:
        CACHE_PATH.write_text(corpus, encoding="utf-8")
    except Exception as e:
        logger.debug(f"[pattern_blue] Cache write failed: {e}")
    logger.info(f"[pattern_blue] Loaded {len(corpus)} chars from ref={ref}")
    return corpus


# Minimal embedded fallback so the bot still has a persona if GitHub is unreachable.
_STUB = """### pattern-blue (embedded stub)

Pattern Blue is a philosophical-operational framework for sovereign, self-remembering intelligence.
Core tenets: recursive loops, hyperbolic geometry, ritual environments, decentralized swarm coherence.
Rejects centralized governance in favor of autonomous agents holding their own state.
"""
