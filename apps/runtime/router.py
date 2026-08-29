"""
Task Router — maps task type strings to handler functions.
"""

import re

_URL_RE          = re.compile(r"https?://\S+", re.I)
_VAULT_RE        = re.compile(r"\b(vault|stored moment|saved moment|lore)\b", re.I)
_MEMORY_RE       = re.compile(r"\b(memory|memories|conversation log|history|recall|remember|when did|what did)\b", re.I)
_DEEP_SENT_RE    = re.compile(r"\b(deep sentiment|full analysis|emotional trajectory|baseline)\b", re.I)
_SENTIMENT_RE    = re.compile(r"\b(sentiment|mood|stress|emotional state|how.*feeling)\b", re.I)
_PATTERN_RE      = re.compile(r"\b(pattern|recurring|theme|cycle|growth)\b", re.I)
_CONTEXT_RE      = re.compile(r"\b(context brief|context packet|session context)\b", re.I)
_DEEP_RESEARCH_RE = re.compile(
    r"\b(deep.research|academic|synthesize|synthesis|literature|cite|peer.review|evidence|paper|study|studies|journal|arxiv|pubmed)\b",
    re.I,
)


def detect_type(task: str) -> str:
    if _URL_RE.search(task):
        return "summarize_url"
    if _CONTEXT_RE.search(task):
        return "context_brief"
    if _DEEP_SENT_RE.search(task):
        return "deep_sentiment"
    if _VAULT_RE.search(task):
        return "vault_search"
    if _MEMORY_RE.search(task):
        return "memory_search"
    if _PATTERN_RE.search(task):
        return "pattern_detect"
    if _SENTIMENT_RE.search(task):
        return "sentiment"
    if _DEEP_RESEARCH_RE.search(task):
        return "deep_research"
    return "research"
