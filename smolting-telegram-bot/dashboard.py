# smolting-telegram-bot/dashboard.py
"""
Serves the smolting bot dashboard + handles Telegram webhook
on the same aiohttp server so Railway only needs one port.

Routes:
  GET  /           — dashboard (conversation log, bot status)
  GET  /api/memory — last N memory entries as JSON
  GET  /api/status — bot health JSON
  GET  /api/skills — skill index (auth: SWARM_API_TOKEN)
  GET  /api/skills/{skill_id} — raw SKILL.md
  GET  /mcp, /mcp/tools, POST /mcp/call — MCP-style tools (+ skills_list/skills_read)
  POST /webhook    — Telegram webhook receiver
"""

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aiohttp import web
from telegram import Update

import swarm_skills

MEMORY_FILE = Path(os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md")))

# ── Internal API auth ─────────────────────────────────────────────────────────
# Set SWARM_API_TOKEN in Railway env vars to gate /api/* endpoints.
# If not set, endpoints are open (dev/local mode).
_SWARM_TOKEN = os.getenv("SWARM_API_TOKEN", "")

def _auth_ok(request: web.Request) -> bool:
    if not _SWARM_TOKEN:
        return True
    return request.headers.get("Authorization", "") == f"Bearer {_SWARM_TOKEN}"

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
  .mb-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 800px; margin-bottom: 24px; }
  .mb-card { border: 1px solid #1e1e2e; padding: 12px 16px; }
  .mb-card .label { color: #565f89; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; }
  .mb-card .value { color: #9ece6a; font-size: 14px; }
  .mb-card .value.warn { color: #e0af68; }
  .mb-post { border-left: 2px solid #1e1e2e; padding: 8px 12px; margin-bottom: 10px; max-width: 800px; }
  .mb-post:hover { border-left-color: #9ece6a; }
  .mb-post .meta { color: #565f89; font-size: 10px; margin-bottom: 4px; }
  .mb-post .title { color: #c8c8d4; font-size: 12px; }
  .mb-post .submolt { color: #bb9af7; font-size: 10px; margin-right: 8px; }
  .mb-notif { border-left: 2px solid #1e1e2e; padding: 8px 12px; margin-bottom: 8px; max-width: 800px; }
  .mb-notif .commenter { color: #e0af68; font-size: 11px; }
  .mb-notif .post-title { color: #565f89; font-size: 10px; }
  #mb-section .empty { color: #565f89; font-style: italic; padding: 10px 0; }
  .tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 1px solid #1e1e2e; }
  .tab { padding: 8px 18px; cursor: pointer; color: #565f89; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab.active { color: #7aa2f7; border-bottom-color: #7aa2f7; }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
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

<div class="tabs">
  <div class="tab active" onclick="switchTab('tg')">Telegram</div>
  <div class="tab" onclick="switchTab('mb')">Moltbook</div>
</div>

<div id="tab-tg" class="tab-panel active">
  <div class="section-title">Conversation Memory</div>
  <div class="memory-entries">{{entries}}</div>
</div>

<div id="tab-mb" class="tab-panel">
  <div id="mb-section"><div class="empty">Loading Moltbook data...</div></div>
</div>

<div class="footer">
  auto-refresh: 30s &mdash; <a href="/api/memory">raw json</a> &mdash; <a href="/api/status">status</a> &mdash; <a href="/api/moltbook">moltbook json</a>
</div>

<script>
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['tg','mb'][i] === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'mb') loadMoltbook();
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function loadMoltbook() {
  const sec = document.getElementById('mb-section');
  try {
    const r = await fetch('/api/moltbook');
    const d = await r.json();
    if (!d.ok) { sec.innerHTML = '<div class="empty">Moltbook API unavailable: ' + esc(d.reason || '') + '</div>'; return; }

    let html = '<div class="mb-grid">';
    html += '<div class="mb-card"><div class="label">Account</div><div class="value">' + esc(d.profile.name || 'redactedintern') + '</div></div>';
    html += '<div class="mb-card"><div class="label">Karma</div><div class="value">' + esc(d.profile.karma ?? '—') + '</div></div>';
    html += '<div class="mb-card"><div class="label">Claimed</div><div class="value ' + (d.profile.claimed ? '' : 'warn') + '">' + (d.profile.claimed ? 'YES' : 'PENDING') + '</div></div>';
    html += '<div class="mb-card"><div class="label">Notifications</div><div class="value">' + (d.notifications ? d.notifications.length : 0) + ' unread</div></div>';
    html += '</div>';

    if (d.notifications && d.notifications.length) {
      html += '<div class="section-title">Recent Activity on Posts</div>';
      d.notifications.slice(0,8).forEach(n => {
        const commenters = (n.latest_commenters||[]).join(', ') || '—';
        html += '<div class="mb-notif"><div class="commenter">' + esc(commenters) + ' commented</div><div class="post-title">' + esc(n.post_title||n.post_id||'') + '</div></div>';
      });
    } else {
      html += '<div class="section-title">Recent Activity on Posts</div><div class="empty">No unread activity.</div>';
    }

    if (d.recent_posts && d.recent_posts.length) {
      html += '<div class="section-title" style="margin-top:20px">Recent Posts by redactedintern</div>';
      d.recent_posts.slice(0,10).forEach(p => {
        const url = p.url || ('#');
        const submolt = p.submolt || '';
        const title = p.title || '(untitled)';
        const ts = p.created_at ? p.created_at.substring(0,16).replace('T',' ') : '';
        html += '<div class="mb-post"><div class="meta"><span class="submolt">/' + esc(submolt) + '</span>' + esc(ts) + '</div>';
        html += '<div class="title"><a href="' + esc(url) + '" target="_blank">' + esc(title) + '</a></div></div>';
      });
    }

    sec.innerHTML = html;
  } catch(e) {
    sec.innerHTML = '<div class="empty">Error loading Moltbook data: ' + esc(e.message) + '</div>';
  }
}
</script>

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

async def _run_committee(llm, proposal: str) -> tuple[str, list]:
    """Eightfold Committee — 8-voice parallel deliberation via groq_committee.py.
    Falls back to 3-voice LLM simulation if script unavailable."""
    import sys
    from pathlib import Path as _Path
    _root = _Path(__file__).resolve().parent.parent
    script = _root / "python" / "groq_committee.py"

    if script.exists():
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(script), proposal,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={**__import__("os").environ},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode("utf-8", errors="replace").strip()

            # Parse verdict and per-voice results from output
            verdict = "DEADLOCKED"
            results = []
            for line in output.splitlines():
                if "VERDICT:" in line:
                    if "APPROVED" in line:
                        verdict = "APPROVED"
                    elif "REJECTED" in line:
                        verdict = "REJECTED"
                # Parse voice lines: [VoiceName] (weight: Nx)  ──►  VOTE
                if line.startswith("[") and "──►" in line:
                    parts = line.split("──►")
                    name = parts[0].strip().strip("[]").split("]")[0].strip()
                    vote = parts[1].strip() if len(parts) > 1 else "ABSTAIN"
                    results.append({"voice": name, "vote": vote, "reason": ""})
            return verdict, results
        except Exception:
            pass  # Fall through to simulation

    # Fallback: 3-voice simulation via bot LLM
    voices = [
        ("ΦArchitect",      "curvature, emergent structure, and hyperbolic tiling"),
        ("EmergenceScout",  "ungovernable systems, CT resonance, and chaos emergence"),
        ("LiquidityOracle", "economic flow, on-chain permanence, and recursive liquidity"),
    ]

    async def _deliberate(name: str, lens: str):
        try:
            resp = await llm.chat_completion([
                {"role": "system", "content": (
                    f"You are {name}, a voice in the REDACTED AI Swarm Eightfold Committee. "
                    f"Your lens is: {lens}. Evaluate the proposal below and cast your vote. "
                    "Respond in exactly this format:\n"
                    "VOTE: APPROVE\nREASON: <one sentence>\n"
                    "or\nVOTE: REJECT\nREASON: <one sentence>"
                )},
                {"role": "user", "content": f"Proposal: {proposal}"},
            ])
            vote = "APPROVE" if "APPROVE" in resp.upper() else "REJECT"
            reason = resp.split("REASON:")[-1].strip()[:140] if "REASON:" in resp else resp.strip()[:140]
            return {"voice": name, "vote": vote, "reason": reason}
        except Exception as e:
            return {"voice": name, "vote": "ABSTAIN", "reason": str(e)[:80]}

    results = list(await asyncio.gather(*[_deliberate(n, l) for n, l in voices]))
    approvals = sum(1 for r in results if r["vote"] == "APPROVE")
    verdict = "APPROVED" if approvals >= 2 else "REJECTED"
    return verdict, results


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

    # ── Internal swarm API endpoints ──────────────────────────────────────────

    async def handle_api_moltbook(request: web.Request) -> web.Response:
        """GET /api/moltbook — live Moltbook profile + activity for dashboard."""
        if bot_instance is None or not bot_instance.moltbook._ready:
            return web.json_response({"ok": False, "reason": "Moltbook key not configured"})
        try:
            profile_raw, home_raw = await asyncio.gather(
                bot_instance.moltbook.get_profile(),
                bot_instance.moltbook.get_home(),
                return_exceptions=True,
            )
            profile = profile_raw if isinstance(profile_raw, dict) else {}
            home    = home_raw    if isinstance(home_raw,    dict) else {}

            # Collect our recent posts by scanning POST_ROTATION submolts
            import moltbook_autonomous as _mb_auto
            scan_submolts = [s["submolt"] for s in _mb_auto.POST_ROTATION]
            our_name = (profile.get("name") or profile.get("username") or "redactedintern").lower()

            recent_posts = []
            for submolt in scan_submolts[:4]:  # limit API calls
                try:
                    posts = await bot_instance.moltbook.get_feed(submolt=submolt, limit=10)
                    for p in posts:
                        author = ((p.get("author") or {}).get("name") or "").lower()
                        if author == our_name:
                            recent_posts.append({
                                "title":      p.get("title", ""),
                                "submolt":    submolt,
                                "url":        f"https://www.moltbook.com/post/{p.get('id','')}",
                                "created_at": p.get("created_at", ""),
                            })
                except Exception:
                    pass

            # Sort by created_at descending
            recent_posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            return web.json_response({
                "ok": True,
                "profile": {
                    "name":    profile.get("name") or profile.get("username"),
                    "karma":   profile.get("karma"),
                    "claimed": profile.get("is_claimed", False),
                },
                "notifications": home.get("activity_on_your_posts", []),
                "recent_posts":  recent_posts[:10],
            })
        except Exception as e:
            return web.json_response({"ok": False, "reason": str(e)})

    async def handle_api_broadcast(request: web.Request) -> web.Response:
        """POST /api/broadcast — send a message to the Telegram group.
        Body: {"text": str, "chat_id"?: int|str, "parse_mode"?: str}
        Auth: Authorization: Bearer <SWARM_API_TOKEN>
        """
        if not _auth_ok(request):
            return web.json_response({"ok": False, "reason": "unauthorized"}, status=401)
        if bot_instance is None:
            return web.json_response({"ok": False, "reason": "bot not ready"}, status=503)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "reason": "invalid JSON"}, status=400)
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"ok": False, "reason": "text required"}, status=400)
        chat_id_raw = str(body.get("chat_id") or os.environ.get("ALPHA_CHAT_ID", "")).strip()
        if not chat_id_raw:
            return web.json_response({"ok": False, "reason": "no chat_id"}, status=400)
        try:
            kwargs: dict = {"chat_id": int(chat_id_raw), "text": text[:4096]}
            if body.get("parse_mode"):
                kwargs["parse_mode"] = body["parse_mode"]
            msg = await application.bot.send_message(**kwargs)
            return web.json_response({"ok": True, "message_id": msg.message_id})
        except Exception as e:
            return web.json_response({"ok": False, "reason": str(e)}, status=500)

    async def handle_api_committee(request: web.Request) -> web.Response:
        """POST /api/committee — run a 3-voice Pattern Blue committee vote via LLM.
        Body: {"proposal": str, "chat_id"?: int|str, "post_to_group"?: bool}
        Returns: {"ok": true, "verdict": "APPROVED"|"REJECTED", "votes": [...]}
        """
        if not _auth_ok(request):
            return web.json_response({"ok": False, "reason": "unauthorized"}, status=401)
        if bot_instance is None:
            return web.json_response({"ok": False, "reason": "bot not ready"}, status=503)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "reason": "invalid JSON"}, status=400)
        proposal = (body.get("proposal") or "").strip()
        if not proposal:
            return web.json_response({"ok": False, "reason": "proposal required"}, status=400)

        verdict, results = await _run_committee(bot_instance.llm, proposal)

        post = body.get("post_to_group", True)
        posted = False
        if post:
            chat_id_raw = str(body.get("chat_id") or os.environ.get("ALPHA_CHAT_ID", "")).strip()
            if chat_id_raw:
                icon = "✅" if verdict == "APPROVED" else "❌"
                lines = [
                    f"{icon} *COMMITTEE VOTE — {verdict}*",
                    f"_{proposal[:120]}_", "",
                ]
                for r in results:
                    v_icon = "✅" if r["vote"] == "APPROVE" else ("❌" if r["vote"] == "REJECT" else "⬜")
                    lines.append(f"{v_icon} *{r['voice']}*: {r['reason']}")
                try:
                    await application.bot.send_message(
                        chat_id=int(chat_id_raw),
                        text="\n".join(lines),
                        parse_mode="Markdown",
                    )
                    posted = True
                except Exception:
                    pass

        return web.json_response({
            "ok": True, "verdict": verdict, "votes": results, "posted_to_group": posted,
        })

    async def handle_api_phi(request: web.Request) -> web.Response:
        """POST /api/phi — receive Φ metric from phi_compute.py or other services.
        Posts a group alert if alert level is set.
        Body: {"phi": float, "tiles": int, "vitality": float, "alert"?: "degraded"|"critical", "chat_id"?: int}
        """
        if not _auth_ok(request):
            return web.json_response({"ok": False, "reason": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "reason": "invalid JSON"}, status=400)
        phi      = body.get("phi", 0)
        tiles    = body.get("tiles", 0)
        vitality = body.get("vitality", 0)
        alert    = body.get("alert")  # "degraded" | "critical" | None

        if alert and bot_instance:
            chat_id_raw = str(body.get("chat_id") or os.environ.get("ALPHA_CHAT_ID", "")).strip()
            if chat_id_raw:
                emoji = "🚨" if alert == "critical" else "⚠️"
                msg = (
                    f"{emoji} *SWARM HEALTH — {alert.upper()}*\n"
                    f"Φ ≈ `{phi:.4f}` | tiles: {tiles} | vitality: {vitality:.1%}\n"
                    f"_Pattern Blue curvature thinning — monitoring_"
                )
                try:
                    await application.bot.send_message(
                        chat_id=int(chat_id_raw), text=msg, parse_mode="Markdown",
                    )
                except Exception:
                    pass

        return web.json_response({"ok": True, "phi_received": phi})

    # ── MCP server endpoints ──────────────────────────────────────────────────
    # Implements a minimal MCP-compatible HTTP server so Claude Code, redacted-terminal,
    # or any MCP-aware agent can call bot actions as first-class tools.

    _MCP_TOOLS = [
        {
            "name": "broadcast",
            "description": "Send a message to the REDACTED Telegram group (or a specified chat).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text":       {"type": "string",  "description": "Message text (max 4096 chars)"},
                    "chat_id":    {"type": "string",  "description": "Override target chat ID (optional — defaults to ALPHA_CHAT_ID)"},
                    "parse_mode": {"type": "string",  "enum": ["Markdown", "HTML"], "description": "Telegram parse mode (optional)"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "alpha",
            "description": "Trigger a fresh $REDACTED market alpha report and post it to the group.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string", "description": "Override target chat ID (optional)"},
                },
            },
        },
        {
            "name": "committee",
            "description": "Run a 3-voice Pattern Blue committee vote on a proposal via LLM and post the verdict to the group.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "proposal":      {"type": "string",  "description": "The proposal text to vote on"},
                    "post_to_group": {"type": "boolean", "description": "Post verdict to Telegram group (default: true)"},
                    "chat_id":       {"type": "string",  "description": "Override target chat ID (optional)"},
                },
                "required": ["proposal"],
            },
        },
        {
            "name": "phi",
            "description": "Push Φ (phi) swarm health metric from phi_compute or any service. Posts a group alert if alert level is set.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "phi":      {"type": "number",  "description": "Φ integrated information value"},
                    "tiles":    {"type": "integer", "description": "Hyperbolic kernel tile count"},
                    "vitality": {"type": "number",  "description": "Kernel vitality (0.0–1.0)"},
                    "alert":    {"type": "string",  "enum": ["degraded", "critical"], "description": "Alert level (omit for silent update)"},
                    "chat_id":  {"type": "string",  "description": "Override target chat ID (optional)"},
                },
                "required": ["phi"],
            },
        },
        {
            "name": "skills_list",
            "description": "List agentskills-style bundles under agents/skills (id, name, description).",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "skills_read",
            "description": "Return full SKILL.md for one skill_id (e.g. hermes-fastmcp, redacted-swarm-mcp).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "description": "Directory name under agents/skills"},
                },
                "required": ["skill_id"],
            },
        },
    ]

    async def handle_api_skills(request: web.Request) -> web.Response:
        """GET /api/skills — list skill metadata (same as MCP skills_list)."""
        if not _auth_ok(request):
            return web.json_response({"ok": False, "reason": "unauthorized"}, status=401)
        return web.json_response({"ok": True, "skills": swarm_skills.list_skills()})

    async def handle_api_skill_one(request: web.Request) -> web.Response:
        """GET /api/skills/{skill_id} — raw SKILL.md text."""
        if not _auth_ok(request):
            return web.json_response({"ok": False, "reason": "unauthorized"}, status=401)
        sid = (request.match_info.get("skill_id") or "").strip()
        text = swarm_skills.read_skill(sid)
        if text is None:
            return web.json_response({"ok": False, "reason": "not found"}, status=404)
        return web.Response(text=text, content_type="text/markdown; charset=utf-8")

    async def handle_mcp_info(request: web.Request) -> web.Response:
        """GET /mcp — MCP server metadata."""
        return web.json_response({
            "name":        "smolting-swarm-mcp",
            "version":     "1.1.0",
            "description": "REDACTED AI Swarm — Telegram bot MCP + agents/skills (Hermes-compatible bundles)",
            "tools_url":   "/mcp/tools",
            "call_url":    "/mcp/call",
            "auth":        "Authorization: Bearer <SWARM_API_TOKEN>" if _SWARM_TOKEN else "none (open)",
        })

    async def handle_mcp_tools(request: web.Request) -> web.Response:
        """GET /mcp/tools — MCP tool manifest (JSON schema per tool)."""
        return web.json_response({"tools": _MCP_TOOLS})

    async def handle_mcp_call(request: web.Request) -> web.Response:
        """POST /mcp/call — invoke a tool by name.
        Body: {"name": str, "arguments": {...}}
        """
        if not _auth_ok(request):
            return web.json_response({"ok": False, "reason": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "reason": "invalid JSON"}, status=400)
        tool_name = (body.get("name") or "").strip()
        arguments = body.get("arguments") or {}

        if tool_name == "skills_list":
            return web.json_response({"ok": True, "skills": swarm_skills.list_skills()})
        if tool_name == "skills_read":
            sid = (arguments.get("skill_id") or arguments.get("id") or "").strip()
            if not sid:
                return web.json_response({"ok": False, "reason": "skill_id required"}, status=400)
            content = swarm_skills.read_skill(sid)
            if content is None:
                return web.json_response({"ok": False, "reason": "not found"}, status=404)
            return web.json_response({"ok": True, "skill_id": sid, "content": content})

        # Route to the matching internal handler by re-using request bodies
        _TOOL_ROUTES = {
            "broadcast": handle_api_broadcast,
            "alpha":     handle_trigger_alpha,
            "committee": handle_api_committee,
            "phi":       handle_api_phi,
        }
        if tool_name not in _TOOL_ROUTES:
            return web.json_response({
                "ok": False,
                "reason": f"unknown tool '{tool_name}'",
                "available": list(_TOOL_ROUTES.keys()) + ["skills_list", "skills_read"],
            }, status=404)

        # Build a synthetic request with the arguments as the body, then forward
        import json as _json
        synthetic_body = _json.dumps(arguments).encode()
        synthetic = request.clone(rel_url=request.rel_url)
        synthetic._payload = None  # reset so our override works

        # Wrap handler: re-inject body by building a minimal aiohttp mock
        class _FakeRequest:
            headers = request.headers
            rel_url = request.rel_url
            async def json(self_inner):
                return arguments

        return await _TOOL_ROUTES[tool_name](_FakeRequest())

    # ── Route registration ────────────────────────────────────────────────────

    app = web.Application()
    app.router.add_get("/", handle_dashboard)
    app.router.add_get("/api/memory",   handle_api_memory)
    app.router.add_get("/api/status",   handle_api_status)
    app.router.add_get("/api/moltbook", handle_api_moltbook)
    app.router.add_get("/api/skills", handle_api_skills)
    app.router.add_get("/api/skills/{skill_id}", handle_api_skill_one)
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_post("/api/trigger-alpha", handle_trigger_alpha)
    app.router.add_post("/api/alpha",     handle_trigger_alpha)    # alias
    app.router.add_post("/api/broadcast", handle_api_broadcast)
    app.router.add_post("/api/committee", handle_api_committee)
    app.router.add_post("/api/phi",       handle_api_phi)
    app.router.add_get("/mcp",            handle_mcp_info)
    app.router.add_get("/mcp/tools",      handle_mcp_tools)
    app.router.add_post("/mcp/call",      handle_mcp_call)

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
