"""Shared Telegram + swarm-task helpers.

Previously the repo-root `shared/` directory, reached by every bot through a
`sys.path` insert with a local-copy fallback. Now a real package.
"""
from .tg_fmt import TgFmt, from_llm  # noqa: F401
