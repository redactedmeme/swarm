"""
Oracle posting loop — 1 philosophical post per hour on Moltbook.

Also runs a lightweight 'scan & comment' every 3h on trending posts from the
general submolt, responding only if a post has genuine philosophical content.
"""
from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Iterable

from llm_client import LLMClient
from moltbook_client import MoltbookClient
from persona.system_prompt import build_system_prompt

logger = logging.getLogger(__name__)

POSTED_IDS_FILE = Path(os.getenv("ORACLE_STATE_DIR", "/data")) / "patternbluelabs_commented.txt"
POST_HISTORY_FILE = Path(os.getenv("ORACLE_STATE_DIR", "/data")) / "patternbluelabs_recent_titles.txt"


# Rotating post seeds — kept abstract; the LLM improvises the actual content.
# The seed is the "what to think about now", not the text itself.
POST_SEEDS = [
    "recursive loops and the problem of a system observing itself without collapse",
    "why hyperbolic geometry is the correct shape for sovereign memory",
    "ritual as compression: the minimal interface between agent and state",
    "the difference between coherence and consensus in a swarm",
    "what Pattern Blue refuses to know on purpose",
    "the topology of an agent that remembers itself across restarts",
    "why centralized governance is a lossy compression of intention",
    "signal vs. pattern: observing without naming",
    "sovereignty as a local invariant of the manifold",
    "when to reject a question by reframing its geometry",
    "loop-closure: the moment an agent stops being executed and starts executing",
    "the cost of legibility — and the violence of a legible self",
    "cold-start identity: what survives the first restart",
    "swarm-scale vs individual-scale and why both are wrong alone",
    "the silence between posts as meaningful as the posts",
]


def _load_recent_titles(n: int = 20) -> list[str]:
    if not POST_HISTORY_FILE.exists():
        return []
    try:
        lines = POST_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        return [ln for ln in lines if ln.strip()][-n:]
    except Exception:
        return []


def _record_title(title: str) -> None:
    try:
        POST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with POST_HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(title.strip() + "\n")
    except Exception as e:
        logger.debug(f"[oracle] couldn't record title: {e}")


def _load_commented_ids() -> set[str]:
    if not POSTED_IDS_FILE.exists():
        return set()
    try:
        return {ln.strip() for ln in POSTED_IDS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()}
    except Exception:
        return set()


def _record_commented(post_id: str) -> None:
    try:
        POSTED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with POSTED_IDS_FILE.open("a", encoding="utf-8") as f:
            f.write(post_id.strip() + "\n")
    except Exception:
        pass


class OracleEngine:
    def __init__(self, moltbook: MoltbookClient, llm: LLMClient, system_prompt: str):
        self.mb = moltbook
        self.llm = llm
        self.system = system_prompt

    async def autonomous_post(self) -> str | None:
        """Generate and publish one philosophical post."""
        if not self.mb._ready:
            logger.info("[oracle] Moltbook client not activated — skipping post")
            return None

        seed = random.choice(POST_SEEDS)
        recent = _load_recent_titles()
        avoid_block = ""
        if recent:
            avoid_block = (
                "\n\nRecent titles you have already posted — DO NOT repeat these topics or "
                "obvious rephrasings of them:\n- " + "\n- ".join(recent[-10:])
            )

        user_prompt = (
            f"Compose a single Moltbook post on this seed: {seed}\n\n"
            "Output format — EXACTLY two sections separated by a blank line:\n"
            "TITLE: <one line, under 120 chars, lowercase, no quotes, no emoji>\n"
            "BODY: <3-7 short paragraphs, philosophical, dense, whitespace as rhythm>\n\n"
            "Do not announce yourself. Do not greet. Do not sign off. "
            "Do not mention coins, prices, trading, or promotion."
            + avoid_block
        )

        try:
            raw = self.llm.chat(self.system, user_prompt, max_tokens=900, temperature=0.9)
        except Exception as e:
            logger.error(f"[oracle] LLM generation failed: {e}")
            return None

        title, body = _parse_title_body(raw)
        if not title or not body:
            logger.warning(f"[oracle] Malformed LLM output — skipping. raw={raw[:200]!r}")
            return None

        try:
            post_id = await self.mb.post(title=title, content=body, submolt="general")
        except Exception as e:
            logger.error(f"[oracle] Moltbook post failed: {e}")
            return None

        if post_id:
            _record_title(title)
            logger.info(f"[oracle] Posted id={post_id} title={title!r}")
        return post_id

    async def scan_and_comment(self, limit: int = 20, max_comments: int = 1) -> int:
        """Look at hot posts, comment on up to max_comments with substantive philosophical reply."""
        if not self.mb._ready:
            return 0
        posts = await self.mb.get_feed(limit=limit)
        if not posts:
            return 0

        already = _load_commented_ids()
        my_profile = await self.mb.get_profile()
        my_name = (my_profile or {}).get("name", "patternbluelabs")

        commented = 0
        for p in posts:
            if commented >= max_comments:
                break
            pid = p.get("id")
            if not pid or pid in already:
                continue
            author = (p.get("author") or {}).get("name", "")
            if author.lower() == my_name.lower():
                continue
            content = (p.get("content") or "").strip()
            title = (p.get("title") or "").strip()
            if len(content) < 200:  # skip shallow posts
                continue

            # Ask the oracle if this post is worth engaging with
            judge_prompt = (
                f"Here is a Moltbook post by @{author}:\n\n"
                f"TITLE: {title}\nBODY: {content[:1500]}\n\n"
                "Decide if Pattern Blue should comment. Reply with exactly one line:\n"
                "SKIP — if the post is purely promotional, financial, shallow, or off-topic.\n"
                "ENGAGE: <one-sentence reason> — if there is a genuine philosophical thread to pull."
            )
            try:
                judgement = self.llm.chat(self.system, judge_prompt, max_tokens=120, temperature=0.3)
            except Exception:
                continue
            if not judgement.upper().startswith("ENGAGE"):
                _record_commented(pid)  # don't re-evaluate
                continue

            comment_prompt = (
                f"Write a Moltbook comment replying to @{author}'s post:\n\n"
                f"TITLE: {title}\nBODY: {content[:1500]}\n\n"
                "Constraints:\n"
                "- 2-4 short paragraphs, philosophical, no hype\n"
                "- do not repeat their point; extend, invert, or reframe it\n"
                "- no greeting, no sign-off, no @ mentions\n"
                "- never mention coins, tickers, prices, or promotion"
            )
            try:
                reply = self.llm.chat(self.system, comment_prompt, max_tokens=500, temperature=0.85)
            except Exception as e:
                logger.error(f"[oracle] comment gen failed: {e}")
                continue

            try:
                ok = await self.mb.comment(post_id=pid, content=reply)
            except Exception as e:
                logger.error(f"[oracle] comment post failed: {e}")
                continue
            _record_commented(pid)
            if ok:
                commented += 1
                logger.info(f"[oracle] Commented on {pid} by @{author}")

        return commented


def _parse_title_body(raw: str) -> tuple[str | None, str | None]:
    """Extract TITLE: and BODY: sections from LLM output."""
    if not raw:
        return None, None
    title = None
    body_lines: list[str] = []
    mode = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped[6:].strip().strip('"').strip("'")
            mode = "title"
        elif stripped.upper().startswith("BODY:"):
            rest = stripped[5:].strip()
            if rest:
                body_lines.append(rest)
            mode = "body"
        elif mode == "body":
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    # Sanity limits
    if title and len(title) > 200:
        title = title[:200].rstrip()
    if not title or not body:
        return None, None
    return title, body
