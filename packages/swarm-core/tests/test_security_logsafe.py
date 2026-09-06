"""logsafe: bot tokens must not reach the log surface.

Found live: swarm-builder was writing its Telegram token ~6k times a day, and
smolting and chan the same, because httpx logs the full request URL at INFO and
a Telegram endpoint is api.telegram.org/bot<TOKEN>/getUpdates.
"""
from __future__ import annotations

import logging

from swarm_core.security import logsafe

# Shaped to match leakscan's telegram_bot_token rule (8-10 digits, ':', 35 chars).
# MUST be synthetic. Never paste a live credential here to make the match realistic.
TOKEN = "1234567890:AAFAKEfakeFAKEfakeFAKEfakeFAKEfake0"  # leakscan: allow
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"


def _capture(name: str):
    """A logger with its own handler and a list to collect formatted output."""
    out: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            out.append(self.format(record))

    logger = logging.getLogger(name)
    logger.handlers = []
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    h = _Collect()
    h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(h)
    return logger, out


# -- levels ------------------------------------------------------------------

def test_quiet_http_loggers_raises_the_url_loggers():
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logging.getLogger("httpcore").setLevel(logging.DEBUG)
    logsafe.quiet_http_loggers()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_quiet_http_loggers_accepts_extra():
    logsafe.quiet_http_loggers(extra=["some.chatty.lib"])
    assert logging.getLogger("some.chatty.lib").level == logging.WARNING


# -- redaction ---------------------------------------------------------------

def test_token_is_redacted_from_a_record():
    logger, out = _capture("test.logsafe.a")
    logsafe.install_log_redaction(logger)
    logger.info("HTTP Request: POST %s \"HTTP/1.1 200 OK\"", URL)
    assert TOKEN not in out[0]
    assert "api.telegram.org" in out[0]  # the useful part survives


def test_redaction_survives_the_level_fix_being_insufficient():
    """The reason raising levels is not enough on its own: an httpx timeout is
    logged AT WARNING and carries the same URL."""
    logger, out = _capture("test.logsafe.b")
    logger.setLevel(logging.WARNING)
    logsafe.install_log_redaction(logger)
    logger.warning("request failed: %s", URL)
    assert out and TOKEN not in out[0]


def test_clean_records_are_untouched():
    logger, out = _capture("test.logsafe.c")
    logsafe.install_log_redaction(logger)
    logger.info("pool cycle complete: %d pools", 10)
    assert out == ["pool cycle complete: 10 pools"]


def test_filter_is_idempotent():
    logger, _ = _capture("test.logsafe.d")
    assert logsafe.install_log_redaction(logger) == 1
    assert logsafe.install_log_redaction(logger) == 0


def test_broken_format_string_does_not_raise():
    """A record whose own format string is broken must pass through the filter
    untouched — redaction is not the place to surface someone else's bug."""
    record = logging.LogRecord(
        "test.logsafe.e", logging.INFO, __file__, 1, "value=%d", ("not-an-int",), None
    )
    assert logsafe.SecretRedactingFilter().filter(record) is True
    assert record.msg == "value=%d"  # left alone, not mangled


def test_harden_logging_does_both():
    logger, out = _capture("test.logsafe.f")
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logsafe.harden_logging(logger=logger)
    assert logging.getLogger("httpx").level == logging.WARNING
    logger.info("POST %s", URL)
    assert TOKEN not in out[0]
