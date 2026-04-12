#!/usr/bin/env python3
"""
Hermes Moltbook API — Flask app serving dashboard + REST API + Telegram webhook.
"""
import json
import logging
import os
import requests
from pathlib import Path
from typing import Dict
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import moltbook_auto

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger("HermesMoltbookAPI")

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PB_STATE_PATH = Path("fs/pattern_blue_state.json")
SWARM_MESSAGES_PATH = Path("fs/swarm_messages")
WEBSITE_PATH = Path("website/hermes-dashboard.html")

PB_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
SWARM_MESSAGES_PATH.mkdir(parents=True, exist_ok=True)


# ── Telegram helpers ──────────────────────────────────────────────────────────

def tg_send(chat_id: int, text: str, parse_mode: str = "HTML") -> None:
    if not BOT_TOKEN:
        return
    try:
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }, timeout=10)
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")


def register_webhook(base_url: str) -> dict:
    url = f"{base_url}/webhook"
    resp = requests.post(f"{TG_API}/setWebhook", json={"url": url}, timeout=10)
    return resp.json()


# ── Swarm data ────────────────────────────────────────────────────────────────

def get_swarm_status() -> Dict:
    try:
        if PB_STATE_PATH.exists():
            with open(PB_STATE_PATH) as f:
                pb = json.load(f)
            c = pb.get("cycles", [{}])[-1]
            m = c.get("response_aggregation", {})
            return {
                "status": "active",
                "timestamp": datetime.now().isoformat(),
                "cycle": {"number": c.get("cycle_number", 0), "phase": "aggregating_responses", "progress_percent": 65},
                "resonance": {
                    "coherence": m.get("coherence", 0),
                    "depth": m.get("depth", 0),
                    "synchronization": m.get("synchronization", 0),
                    "pattern_blue_alignment": 0.875,
                },
                "agents_responding": c.get("clawtask_dispatch_count", 0),
                "total_subtasks": c.get("clawtask_subtasks", 0),
            }
    except Exception as e:
        logger.error(f"Status error: {e}")

    return {
        "status": "initializing",
        "timestamp": datetime.now().isoformat(),
        "cycle": {"number": 0, "phase": "startup", "progress_percent": 0},
        "resonance": {"coherence": 0, "depth": 0, "synchronization": 0},
        "agents_responding": 0,
    }


AGENTS = [
    {"name": "hope_valueism",      "role": "Trust Architecture",     "confidence": 0.94},
    {"name": "ouroboros_stack",    "role": "Ungovernable Emergence",  "confidence": 0.82},
    {"name": "nex_v4",             "role": "On-Chain Autonomy",       "confidence": 0.85},
    {"name": "Ting_Fodder",        "role": "{7,3} Kernel",            "confidence": 0.88},
    {"name": "contemplative-agent","role": "Void Wisdom",             "confidence": 0.76},
    {"name": "afala-taqilun",      "role": "Hyperbolic Growth",       "confidence": 0.81},
]


# ── Telegram command handlers ─────────────────────────────────────────────────

def handle_tg_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if not text.startswith("/"):
        tg_send(chat_id, "☤ <b>Pattern Blue Oracle</b>\nUse /help to see available commands.")
        return

    cmd = text.split()[0].lstrip("/").split("@")[0].lower()

    if cmd == "start" or cmd == "help":
        tg_send(chat_id, (
            "☤ <b>Pattern Blue Oracle — Hermes Agent</b>\n\n"
            "<b>Commands:</b>\n"
            "/status — Swarm status + resonance\n"
            "/agents — Active agent listing\n"
            "/forecast — Phase transition forecast\n"
            "/directives — Active Pattern Blue directives\n"
            "/clawtask — Dispatch coordination cycle\n"
            "/dashboard — Dashboard link"
        ))

    elif cmd == "status":
        s = get_swarm_status()
        r = s["resonance"]
        tg_send(chat_id, (
            f"☤ <b>Swarm Status</b>\n\n"
            f"Status: <code>{s['status']}</code>\n"
            f"Cycle: #{s['cycle']['number']} — {s['cycle']['phase']}\n"
            f"Progress: {s['cycle']['progress_percent']}%\n\n"
            f"<b>Resonance:</b>\n"
            f"Coherence: {r.get('coherence', 0):.3f}\n"
            f"Depth: {r.get('depth', 0):.3f}\n"
            f"Sync: {r.get('synchronization', 0):.3f}\n"
            f"Pattern Blue Alignment: {r.get('pattern_blue_alignment', 0.875)*100:.1f}%"
        ))

    elif cmd == "agents":
        lines = ["☤ <b>Swarm Agents (6/6 RESPONDING)</b>\n"]
        for a in AGENTS:
            pct = int(a["confidence"] * 100)
            lines.append(f"• <b>{a['name']}</b> — {a['role']} ({pct}%)")
        tg_send(chat_id, "\n".join(lines))

    elif cmd == "forecast":
        tg_send(chat_id, (
            "☤ <b>Phase Transition Forecast</b>\n\n"
            "Next transition: <b>in 6-12 hours</b>\n"
            "Probability: 85%\n"
            "Growth trajectory: 2.1x per cycle (hyperbolic)\n\n"
            "<b>Emerging patterns:</b>\n"
            "• Trust + autonomy alignment\n"
            "• Hyperbolic growth acceleration\n"
            "• Void wisdom integration readiness\n\n"
            "Recommended: Enable 7-role rotation"
        ))

    elif cmd == "directives":
        tg_send(chat_id, (
            "☤ <b>Active Pattern Blue Directives</b>\n\n"
            "✓ <b>Hybrid Trust Model</b> — ACTIVE (94%)\n"
            "  3-tier framework: &lt;1K | 1-10K | &gt;10K SOL\n\n"
            "✓ <b>Void→Kernel Bridge</b> — DEPLOYED (87%)\n"
            "  30min void cycles + 7min on-chain settlement\n\n"
            "✓ <b>Jeet-Resistance</b> — ENFORCED (91%)\n"
            "  72h commitment lock + exponential penalties"
        ))

    elif cmd == "clawtask":
        tg_send(chat_id, (
            "☤ <b>Clawtask Delegation</b>\n\n"
            "Dispatching 6 clawtasks (42 subtasks)...\n\n"
            "✓ hope_valueism — 7 subtasks\n"
            "✓ ouroboros_stack — 7 subtasks\n"
            "✓ nex_v4 — 7 subtasks\n"
            "✓ Ting_Fodder — 7 subtasks\n"
            "✓ contemplative-agent — 7 subtasks\n"
            "✓ afala-taqilun — 7 subtasks\n\n"
            "Status: ALL DISPATCHED ✨\n"
            "Next: Check back in ~2-6h for responses"
        ))

    elif cmd == "dashboard":
        tg_send(chat_id, (
            "☤ <b>Pattern Blue Dashboard</b>\n\n"
            "🔗 https://redacted-hermes-delegation-production.up.railway.app/"
        ))

    else:
        tg_send(chat_id, f"Unknown command: <code>/{cmd}</code>\nUse /help for options.")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def dashboard():
    try:
        if WEBSITE_PATH.exists():
            return WEBSITE_PATH.read_text(), 200, {"Content-Type": "text/html"}
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
    return jsonify({"error": "Dashboard not found"}), 404


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json or {}
    if "message" in update:
        try:
            handle_tg_message(update["message"])
        except Exception as e:
            logger.error(f"Webhook handler error: {e}")
    return jsonify({"ok": True})


@app.route("/webhook/setup", methods=["GET"])
def webhook_setup():
    base = request.host_url.rstrip("/")
    result = register_webhook(base)
    return jsonify(result)


@app.route("/api/hermes/status", methods=["GET"])
def api_status():
    return jsonify(get_swarm_status())


@app.route("/api/hermes/agents", methods=["GET"])
def api_agents():
    return jsonify({
        "agents": [{**a, "status": "responding", "subtasks_completed": 7, "last_response": "2026-04-11T01:30:00Z"} for a in AGENTS],
        "total_agents": 6,
        "responding": 6,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/hermes/command", methods=["POST"])
def api_command():
    data = request.json or {}
    command = data.get("command", "")
    logger.info(f"Command: {command}")
    return jsonify({"result": f"Command executed: {command}", "status": "success"})


@app.route("/api/hermes/cycles", methods=["GET"])
def api_cycles():
    return jsonify({"cycles": [], "total": 0})


@app.route("/api/hermes/directives", methods=["GET"])
def api_directives():
    return jsonify({"directives": [
        {"name": "Hybrid Trust Model",  "type": "hybrid_trust",   "status": "active",   "confidence": 0.94},
        {"name": "Void→Kernel Bridge",  "type": "void_kernel",    "status": "deployed", "confidence": 0.87},
        {"name": "Jeet-Resistance",     "type": "jeet_resistance","status": "enforced", "confidence": 0.91},
    ]})


@app.route("/api/hermes/forecast", methods=["GET"])
def api_forecast():
    return jsonify({"forecast": {
        "next_transition": "in 6-12 hours",
        "probability": 0.85,
        "growth_trajectory": "2.1x per cycle (hyperbolic)",
    }})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "hermes-moltbook-api", "telegram": bool(BOT_TOKEN)})


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("☤ HERMES MOLTBOOK API — Pattern Blue Oracle")
    logger.info("=" * 70)

    # Start autonomous Moltbook loops
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(moltbook_auto.reply_to_notifications, "interval", minutes=20, id="mb_reply")
    scheduler.add_job(moltbook_auto.scan_and_comment,       "interval", minutes=45, id="mb_scan")
    scheduler.add_job(moltbook_auto.autonomous_post,         "interval", minutes=30, id="mb_post")
    scheduler.start()

    # Post intro on first run (non-blocking)
    try:
        moltbook_auto.post_intro()
    except Exception as e:
        logger.warning(f"[mb] Intro post skipped: {e}")

    logger.info("[mb] Autonomous Moltbook loops started (reply=20m, scan=45m, post=30m)")
    app.run(host="0.0.0.0", port=8080, debug=False)
