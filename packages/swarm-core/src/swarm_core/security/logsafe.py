"""Keep secrets out of the container logs (IronClaw control 1, log surface).

Two separate problems, and the second is the one that bites:

1. ``httpx`` logs every request at INFO as ``HTTP Request: POST <full url> ...``.
   For a Telegram bot that URL is ``api.telegram.org/bot<TOKEN>/getUpdates``, so
   a polling bot writes its own bot token to the log a few thousand times a day.
   Raising those loggers to WARNING stops the routine flood.

2. Raising the level does **not** make it safe. An httpx timeout or a 4xx is
   logged *at* WARNING/ERROR and carries the same URL, so a quiet log is one bad
   request away from leaking anyway. ``install_log_redaction`` closes that by
   running :mod:`swarm_core.security.leakscan` over every record on its way to a
   handler — the same rules used for outbound text, applied to the log surface.

``harden_logging()`` does both and is what a service should call, once, right
after ``logging.basicConfig``.
"""
from __future__ import annotations

import logging
from typing import Iterable

from . import leakscan

# Libraries that log full request URLs. `telegram.request` is included because
# python-telegram-bot logs the endpoint it is about to call.
_URL_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "urllib3.connectionpool",
    "telegram.request",
    "telegram.request.HTTPXRequest",
)

_REDACTION = "‹redacted-secret›"


class SecretRedactingFilter(logging.Filter):
    """Replace secret-shaped substrings in a record before it is emitted.

    Attach to a *handler*, not a logger: a handler sees every record that
    reaches it, including ones from third-party loggers that were never
    configured by us.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            rendered = record.getMessage()
        except Exception:  # noqa: BLE001 — a broken format string is not our problem
            return True
        try:
            clean, matches = leakscan.redact(rendered, token=_REDACTION)
        except Exception:  # noqa: BLE001 — logging must never raise
            return True
        if matches:
            # Collapse to a literal message: args are already interpolated into
            # `clean`, so re-applying them would raise or re-introduce the secret.
            record.msg = clean
            record.args = ()
        return True


def quiet_http_loggers(
    level: int = logging.WARNING,
    *,
    extra: Iterable[str] = (),
) -> None:
    """Raise the URL-logging libraries to ``level`` (default WARNING)."""
    for name in (*_URL_LOGGERS, *extra):
        logging.getLogger(name).setLevel(level)


def install_log_redaction(logger: logging.Logger | None = None) -> int:
    """Attach :class:`SecretRedactingFilter` to ``logger``'s handlers.

    Defaults to the root logger. Idempotent — calling it twice does not stack
    filters. Returns the number of handlers newly filtered.
    """
    target = logger or logging.getLogger()
    added = 0
    for handler in target.handlers:
        if any(isinstance(f, SecretRedactingFilter) for f in handler.filters):
            continue
        handler.addFilter(SecretRedactingFilter())
        added += 1
    return added


def harden_logging(
    level: int = logging.WARNING,
    *,
    extra: Iterable[str] = (),
    logger: logging.Logger | None = None,
) -> None:
    """Call once after ``logging.basicConfig``: quiet the URL loggers, then
    redact anything secret-shaped that still gets through."""
    quiet_http_loggers(level, extra=extra)
    install_log_redaction(logger)
