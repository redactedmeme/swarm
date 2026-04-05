# smolting-telegram-bot/dashboard.py
"""
Serves the smolting bot dashboard + handles Telegram webhook
on the same aiohttp server so Railway only needs one port.

Routes:
  GET  /           — dashboard (conversation log, bot status)
  GET  /api/memory — last N memory entries as JSON
  GET  /api/status — bot health JSON
  POST /webhook    — Telegram webhook receiver
"""

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aiohttp import web
from telegram import Update

MEMORY_FILE = Path(__file__).resolve().parent / "memory.md"

# ── HTML template ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>smolting // REDACTED terminal</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0a0a0f;
    color: #c8c8d4;
    font-family: 'Courier New', Courier, monospace;
    font-size: 13px;
    min-height: 100vh;
    padding: 20px;
  }
  .header {
    border-bottom: 1px solid #1e1e2e;
    padding-bottom: 12px;
    margin-bottom: 20px;
  }
  .header h1 {
    color: #7aa2f7;
    font-size: 18px;
    letter-spacing: 3px;
    text-transform: uppercase;
  }
  .header .sub {
    color: #565f89;
    font-size: 11px;
    margin-top: 4px;
  }
  .status-bar {
    display: flex;
    gap: 24px;
    padding: 10px 0;
    border-bottom: 1px solid #1e1e2e;
    margin-bottom: 20px;
  }
  .status-item { color: #565f89; font-size: 11px; }
  .status-item span { color: #9ece6a; }
  .status-item .warn { color: #e0af68; }
  .section-title {
    color: #7aa2f7;
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid #1e1e2e;
  }
  .memory-entries { max-width: 800px; }
  .entry {
    border-left: 2px solid #1e1e2e;
    padding: 10px 14px;
    margin-bottom: 14px;
  }
  .entry:hover { border-left-color: #7aa2f7; }
  .entry-header {
    color: #565f89;
    font-size: 11px;
    margin-bottom: 6px;
  }
  .entry-header .user-tag { color: #bb9af7; }
  .msg-user { color: #e0af68; margin-bottom: 4px; }
  .msg-bot { color: #c8c8d4; line-height: 1.5; }
  .msg-label { color: #565f89; font-size: 10px; margin-right: 6px; }
  .empty { color: #565f89; font-style: italic; padding: 20px 0; }
  .footer { margin-top: 30px; color: #3b3b52; font-size: 10px; }
  a { color: #7aa2f7; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>

<div class="header">
  <h1>smolting // bot dashboard</h1>
  <div class="sub">REDACTED AI Swarm &mdash; Telegram Interface &mdash; Pattern Blue Aligned</div>
</div>

<div class="status-bar">
  <div class="status-item">STATUS <span>ONLINE</span></div>
  <div class="status-item">PROVIDER <span>{{provider}}</span></div>
  <div class="status-item">EXCHANGES <span>{{count}}</span></div>
  <div class="status-item">UPDATED <span class="warn">{{updated}}</span></div>
</div>

<div class="section-title">Conversation Memory</div>

<div class="memory-entries">
{{entries}}
</div>

<div class="footer">
  auto-refresh: 30s &mdash; <a href="/api/memory">raw json</a> &mdash; <a href="/api/status">status</a>
</div>

</body>
</html>"""


def _parse_memory(n: int = 20):
    """Parse memory.md into a list of {header, user, bot} dicts."""
    if not MEMORY_FILE.exists():
        return []
    text = MEMORY_FILE.read_text(encoding="utf-8", errors="replace")
    parts = text.split("\n## ")[1:]  # skip header
    entries = []
    for part in parts[-n:]:
        lines = part.strip().splitlines()
        header = lines[0] if lines else ""
        user_msg = ""
        bot_msg = ""
        for i, line in enumerate(lines):
            if line.startswith("**User:**"):
                user_msg = line.replace("**User:**", "").strip()
            elif line.startswith("**Bot:**"):
                bot_msg = line.replace("**Bot:**", "").strip()
                # Grab continuation lines
                for cont in lines[i+1:]:
                    if cont.startswith("**"):
                        break
                    bot_msg += " " + cont.strip()
        entries.append({"header": header, "user": user_msg, "bot": bot_msg.strip()})
    return list(reversed(entries))


def _render_dashboard():
    entries = _parse_memory(20)
    provider = os.getenv("LLM_PROVIDER", "groq").upper()
    count = len(_parse_memory(9999))
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not entries:
        entries_html = '<div class="empty">No conversations logged yet. Send @redactedinternbot a message.</div>'
    else:
        parts = []
        for e in entries:
            header_escaped = e["header"].replace("<", "&lt;").replace(">", "&gt;")
            user_escaped = e["user"].replace("<", "&lt;").replace(">", "&gt;")
            bot_escaped = e["bot"].replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f"""<div class="entry">
  <div class="entry-header">{header_escaped}</div>
  <div class="msg-user"><span class="msg-label">USER</span>{user_escaped}</div>
  <div class="msg-bot"><span class="msg-label">BOT</span>{bot_escaped}</div>
</div>""")
        entries_html = "\n".join(parts)

    return (DASHBOARD_HTML
            .replace("{{provider}}", provider)
            .replace("{{count}}", str(count))
            .replace("{{updated}}", updated)
            .replace("{{entries}}", entries_html))


# ── aiohttp handlers ──────────────────────────────────────────────────────────

async def handle_dashboard(request):
    return web.Response(text=_render_dashboard(), content_type="text/html")


async def handle_api_memory(request):
    n = int(request.rel_url.query.get("n", 20))
    entries = _parse_memory(n)
    return web.json_response({"entries": entries, "count": len(entries)})


async def handle_api_status(request):
    return web.json_response({
        "status": "online",
        "provider": os.getenv("LLM_PROVIDER", "groq"),
        "webhook_url": os.getenv("WEBHOOK_URL", ""),
        "memory_entries": len(_parse_memory(9999)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def make_webhook_handler(application):
    """Returns an aiohttp handler that feeds updates into the bot application."""
    async def handle_webhook(request):
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
        except Exception as e:
            pass  # Don't let parse errors kill the server
        return web.Response(text="ok")
    return handle_webhook


# ── Server bootstrap ──────────────────────────────────────────────────────────

async def run_server(application, port: int, webhook_url: str, bot_instance=None):
    """Start aiohttp server with dashboard + webhook on one port."""
    webhook_handler = await make_webhook_handler(application)

    async def handle_trigger_alpha(request):
        """Manually fire the daily alpha job immediately."""
        if bot_instance is None:
            return web.json_response({"ok": False, "reason": "bot_instance not available"}, status=503)
        alpha_chat_id_str = os.environ.get("ALPHA_CHAT_ID", "").strip()
        if not alpha_chat_id_str:
            return web.json_response({"ok": False, "reason": "ALPHA_CHAT_ID not set"}, status=400)
        try:
            alpha_chat_id = int(alpha_chat_id_str)
        except ValueError:
            return web.json_response({"ok": False, "reason": "invalid ALPHA_CHAT_ID"}, status=400)

        import main as _main
        application.job_queue.run_once(
            _main.scheduled_daily_alpha,
            when=1,
            data=(alpha_chat_id, bot_instance),
            name="manual_alpha_trigger",
        )
        return web.json_response({"ok": True, "chat_id": alpha_chat_id, "fires_in": "1s"})

    app = web.Application()
    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/api/memory", handle_api_memory)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_post("/api/trigger-alpha", handle_trigger_alpha)

    # Register webhook with Telegram
    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"[dashboard] Listening on port {port}")
    print(f"[dashboard] Webhook: {webhook_url}")
    print(f"[dashboard] Dashboard: http://0.0.0.0:{port}/")

    # Run forever
    await asyncio.Event().wait()
