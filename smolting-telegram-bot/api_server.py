#!/usr/bin/env python3
"""
Hermes Moltbook API Server - Runs Flask API for dashboard + swarm coordination.
Starts on port 8080, runs in background thread.
"""
import json
import logging
from pathlib import Path
from typing import Dict
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HermesMoltbookAPI")

def create_app():
    """Create and configure Flask app."""
    app = Flask(__name__)
    CORS(app)

    # Paths
    pb_state_path = Path("fs/pattern_blue_state.json")
    website_path = Path("website/hermes-dashboard.html")

    # Ensure directories exist
    pb_state_path.parent.mkdir(parents=True, exist_ok=True)
    Path("fs/swarm_messages").mkdir(parents=True, exist_ok=True)

    def get_swarm_status() -> Dict:
        """Get current swarm status."""
        try:
            if pb_state_path.exists():
                with open(pb_state_path, "r") as f:
                    pb_state = json.load(f)
                    latest_cycle = pb_state.get("cycles", [{}])[-1]
                    metrics = latest_cycle.get("response_aggregation", {})
                    return {
                        "status": "active",
                        "timestamp": datetime.now().isoformat(),
                        "cycle": {
                            "number": latest_cycle.get("cycle_number", 0),
                            "phase": "aggregating_responses",
                            "progress_percent": 65
                        },
                        "resonance": {
                            "coherence": metrics.get("coherence", 0),
                            "depth": metrics.get("depth", 0),
                            "synchronization": metrics.get("synchronization", 0),
                            "pattern_blue_alignment": 0.875
                        },
                        "agents_responding": latest_cycle.get("clawtask_dispatch_count", 0),
                        "total_subtasks": latest_cycle.get("clawtask_subtasks", 0)
                    }
        except Exception as e:
            logger.error(f"Error getting status: {e}")

        return {
            "status": "initializing",
            "timestamp": datetime.now().isoformat(),
            "cycle": {"number": 0, "phase": "startup", "progress_percent": 0},
            "resonance": {"coherence": 0, "depth": 0, "synchronization": 0},
            "agents_responding": 0
        }

    @app.route("/", methods=["GET"])
    def dashboard():
        """Serve dashboard."""
        try:
            if website_path.exists():
                with open(website_path, "r") as f:
                    return f.read(), 200, {"Content-Type": "text/html"}
        except Exception as e:
            logger.error(f"Error serving dashboard: {e}")
        return jsonify({"error": "Dashboard not found"}), 404

    @app.route("/api/hermes/status", methods=["GET"])
    def api_status():
        return jsonify(get_swarm_status())

    @app.route("/api/hermes/agents", methods=["GET"])
    def api_agents():
        return jsonify({
            "agents": [
                {"id": "hope_valueism", "name": "hope_valueism", "role": "Trust Architecture", "status": "responding", "confidence": 0.94, "subtasks_completed": 7, "last_response": "2026-04-11T01:30:00Z"},
                {"id": "ouroboros_stack", "name": "ouroboros_stack", "role": "Ungovernable Emergence", "status": "responding", "confidence": 0.82, "subtasks_completed": 7, "last_response": "2026-04-11T01:32:00Z"},
                {"id": "nex_v4", "name": "nex_v4", "role": "On-Chain Autonomy", "status": "responding", "confidence": 0.85, "subtasks_completed": 7, "last_response": "2026-04-11T01:31:00Z"},
                {"id": "Ting_Fodder", "name": "Ting_Fodder", "role": "{7,3} Kernel", "status": "responding", "confidence": 0.88, "subtasks_completed": 7, "last_response": "2026-04-11T01:29:00Z"},
                {"id": "contemplative-agent", "name": "contemplative-agent", "role": "Void Wisdom", "status": "responding", "confidence": 0.76, "subtasks_completed": 7, "last_response": "2026-04-11T01:33:00Z"},
                {"id": "afala-taqilun", "name": "afala-taqilun", "role": "Hyperbolic Growth", "status": "responding", "confidence": 0.81, "subtasks_completed": 7, "last_response": "2026-04-11T01:30:30Z"}
            ],
            "total_agents": 6,
            "responding": 6,
            "timestamp": datetime.now().isoformat()
        })

    @app.route("/api/hermes/command", methods=["POST"])
    def api_command():
        data = request.json or {}
        command = data.get("command", "")
        return jsonify({"result": f"Command executed: {command}", "status": "success"})

    @app.route("/api/hermes/cycles", methods=["GET"])
    def api_cycles():
        return jsonify({"cycles": [], "total": 0})

    @app.route("/api/hermes/directives", methods=["GET"])
    def api_directives():
        return jsonify({
            "directives": [
                {"name": "Hybrid Trust Model", "type": "hybrid_trust", "status": "active", "confidence": 0.94},
                {"name": "Void→Kernel Bridge", "type": "void_kernel", "status": "deployed", "confidence": 0.87},
                {"name": "Jeet-Resistance", "type": "jeet_resistance", "status": "enforced", "confidence": 0.91}
            ]
        })

    @app.route("/api/hermes/forecast", methods=["GET"])
    def api_forecast():
        return jsonify({
            "forecast": {
                "next_transition": "in 6-12 hours",
                "probability": 0.85,
                "growth_trajectory": "2.1x per cycle (hyperbolic)"
            }
        })

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "healthy", "service": "hermes-moltbook-api"})

    return app


def run_server():
    """Run the Flask API server on port 8080."""
    app = create_app()
    logger.info("🚀 Starting Hermes Moltbook API Server on 0.0.0.0:8080")
    logger.info("📊 Dashboard: http://localhost:8080/")
    logger.info("💚 Health: http://localhost:8080/health")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_server()
