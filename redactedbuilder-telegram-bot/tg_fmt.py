"""Telegram rich message formatting — dual-mode (HTML / MarkdownV2).

Usage:
    from shared.tg_fmt import TgFmt, from_llm

    fmt = TgFmt("HTML")  # or "MarkdownV2"
    await update.message.reply_text(
        fmt.bold("hello") + " " + fmt.code("world"),
        parse_mode=fmt.parse_mode,
    )

    # Convert LLM markdown to Telegram-safe HTML:
    safe = from_llm(llm_response)
    await update.message.reply_text(safe, parse_mode="HTML")
"""

from __future__ import annotations

import html
import re
from typing import List

_MD2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _esc_html(text: str) -> str:
    return html.escape(text, quote=False)


def _esc_md2(text: str) -> str:
    return _MD2_SPECIAL.sub(r"\\\1", text)


class TgFmt:
    def __init__(self, mode: str = "HTML"):
        if mode not in ("HTML", "MarkdownV2"):
            raise ValueError(f"mode must be 'HTML' or 'MarkdownV2', got {mode!r}")
        self.mode = mode

    @property
    def parse_mode(self) -> str:
        return self.mode

    def esc(self, text: str) -> str:
        return _esc_html(text) if self.mode == "HTML" else _esc_md2(text)

    def bold(self, text: str) -> str:
        t = self.esc(text)
        return f"<b>{t}</b>" if self.mode == "HTML" else f"*{t}*"

    def italic(self, text: str) -> str:
        t = self.esc(text)
        return f"<i>{t}</i>" if self.mode == "HTML" else f"_{t}_"

    def underline(self, text: str) -> str:
        t = self.esc(text)
        return f"<u>{t}</u>" if self.mode == "HTML" else f"__{t}__"

    def strike(self, text: str) -> str:
        t = self.esc(text)
        return f"<s>{t}</s>" if self.mode == "HTML" else f"~{t}~"

    def spoiler(self, text: str) -> str:
        t = self.esc(text)
        return f"<tg-spoiler>{t}</tg-spoiler>" if self.mode == "HTML" else f"||{t}||"

    def code(self, text: str) -> str:
        if self.mode == "HTML":
            return f"<code>{_esc_html(text)}</code>"
        escaped = text.replace("\\", "\\\\").replace("`", "\\`")
        return f"`{escaped}`"

    def pre(self, text: str, lang: str = "") -> str:
        if self.mode == "HTML":
            t = _esc_html(text)
            if lang:
                return f'<pre><code class="language-{_esc_html(lang)}">{t}</code></pre>'
            return f"<pre>{t}</pre>"
        escaped = text.replace("\\", "\\\\").replace("`", "\\`")
        return f"```{lang}\n{escaped}\n```"

    def link(self, text: str, url: str) -> str:
        t = self.esc(text)
        if self.mode == "HTML":
            return f'<a href="{html.escape(url)}">{t}</a>'
        u = url.replace("\\", "\\\\").replace(")", "\\)")
        return f"[{t}]({u})"

    def mention(self, user_id: int, name: str) -> str:
        t = self.esc(name)
        if self.mode == "HTML":
            return f'<a href="tg://user?id={user_id}">{t}</a>'
        return f"[{t}](tg://user?id={user_id})"

    def custom_emoji(self, emoji: str, emoji_id: str) -> str:
        if self.mode == "HTML":
            return f'<tg-emoji emoji-id="{_esc_html(emoji_id)}">{_esc_html(emoji)}</tg-emoji>'
        return f"![{self.esc(emoji)}](tg://emoji?id={emoji_id})"

    def blockquote(self, text: str) -> str:
        t = self.esc(text)
        if self.mode == "HTML":
            return f"<blockquote>{t}</blockquote>"
        return "\n".join(f">{line}" for line in t.split("\n"))

    def expandable_blockquote(self, text: str) -> str:
        t = self.esc(text)
        if self.mode == "HTML":
            return f"<blockquote expandable>{t}</blockquote>"
        lines = t.split("\n")
        result = "\n".join(f">{line}" for line in lines[:-1])
        if lines:
            result += f"\n>||{lines[-1]}||"
        return result


# ── Standalone HTML convenience ──────────────────────────────────────

_html = TgFmt("HTML")
esc = _html.esc
bold = _html.bold
italic = _html.italic
underline = _html.underline
strike = _html.strike
spoiler = _html.spoiler
code = _html.code
pre = _html.pre
link = _html.link
mention = _html.mention
blockquote = _html.blockquote


# ── LLM markdown → Telegram conversion ──────────────────────────────

_CODE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD_ASTERISK = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_UNDER = re.compile(r"__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_ITALIC_UNDER = re.compile(r"(?<!_)_([^_\n]+?)_(?!_)")
_STRIKE = re.compile(r"~~(.+?)~~")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BLOCKQUOTE = re.compile(r"^> ?(.+)$", re.MULTILINE)


def from_llm(text: str, target: str = "HTML") -> str:
    """Convert LLM markdown to Telegram-safe formatted text."""
    if target == "HTML":
        return _llm_to_html(text)
    return _llm_to_md2(text)


def _llm_to_html(text: str) -> str:
    preserved: list[str] = []

    def _save_code_block(m: re.Match) -> str:
        lang, body = m.group(1), m.group(2)
        idx = len(preserved)
        escaped = _esc_html(body.rstrip("\n"))
        if lang:
            preserved.append(f'<pre><code class="language-{_esc_html(lang)}">{escaped}</code></pre>')
        else:
            preserved.append(f"<pre>{escaped}</pre>")
        return f"\x00CODEBLOCK{idx}\x00"

    def _save_inline_code(m: re.Match) -> str:
        idx = len(preserved)
        preserved.append(f"<code>{_esc_html(m.group(1))}</code>")
        return f"\x00CODEBLOCK{idx}\x00"

    text = _CODE_BLOCK.sub(_save_code_block, text)
    text = _INLINE_CODE.sub(_save_inline_code, text)

    def _save_blockquote(m: re.Match) -> str:
        idx = len(preserved)
        preserved.append(f"<blockquote>{_esc_html(m.group(1))}</blockquote>")
        return f"\x00CODEBLOCK{idx}\x00"

    text = _BLOCKQUOTE.sub(_save_blockquote, text)

    def _save_link(m: re.Match) -> str:
        idx = len(preserved)
        preserved.append(f'<a href="{html.escape(m.group(2))}">{_esc_html(m.group(1))}</a>')
        return f"\x00CODEBLOCK{idx}\x00"

    text = _LINK.sub(_save_link, text)

    text = _esc_html(text)

    text = _BOLD_ASTERISK.sub(r"<b>\1</b>", text)
    text = _BOLD_UNDER.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _ITALIC_UNDER.sub(r"<i>\1</i>", text)
    text = _STRIKE.sub(r"<s>\1</s>", text)

    for idx, block in enumerate(preserved):
        text = text.replace(f"\x00CODEBLOCK{idx}\x00", block)

    return text


def _llm_to_md2(text: str) -> str:
    preserved: list[str] = []

    def _save_code_block(m: re.Match) -> str:
        lang, body = m.group(1), m.group(2)
        idx = len(preserved)
        escaped = body.replace("\\", "\\\\").replace("`", "\\`")
        preserved.append(f"```{lang}\n{escaped.rstrip(chr(10))}\n```")
        return f"\x00CODEBLOCK{idx}\x00"

    def _save_inline_code(m: re.Match) -> str:
        idx = len(preserved)
        inner = m.group(1).replace("\\", "\\\\").replace("`", "\\`")
        preserved.append(f"`{inner}`")
        return f"\x00CODEBLOCK{idx}\x00"

    text = _CODE_BLOCK.sub(_save_code_block, text)
    text = _INLINE_CODE.sub(_save_inline_code, text)

    text = _esc_md2(text)

    text = re.sub(r"\\\*\\\*(.+?)\\\*\\\*", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"\\_\\_(.+?)\\_\\_", r"__\1__", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\\\*)\\\*([^*\n]+?)\\\*(?!\\\*)", r"_\1_", text)
    text = re.sub(r"\\~\\~(.+?)\\~\\~", r"~\1~", text)
    text = re.sub(
        r"\\\[([^\]]+)\\\]\\\(([^)]+)\\\)",
        lambda m: f"[{m.group(1)}]({m.group(2).replace(chr(92), '')})",
        text,
    )

    for idx, block in enumerate(preserved):
        text = text.replace(f"\x00CODEBLOCK{idx}\x00", block)

    return text


# ── Message splitting ────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")


def truncate(text: str, limit: int = 4096) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    open_tags: list[str] = []
    for tag in _TAG_RE.finditer(cut):
        t = tag.group()
        if t.startswith("</"):
            if open_tags:
                open_tags.pop()
        elif not t.endswith("/>"):
            name = t.split()[0].strip("<>").split(">")[0]
            open_tags.append(name)
    suffix = "".join(f"</{t}>" for t in reversed(open_tags))
    return cut + "…" + suffix


def chunks(text: str, limit: int = 4096) -> List[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit - 1
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return parts
