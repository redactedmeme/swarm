# swarm_engine.py
# Version: 2.2 – bugfixes: real observations, real consensus, real settlement, phi loop
import asyncio
import hashlib
import json
import signal
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Core swarm layers
from core.pattern_blue_state import PatternBlueState
from lib.kernel.hyperbolic_scheduler import HyperbolicScheduler
from agents.base.agent_executor import AgentExecutor
from parallel_branch_engine import ParallelBranchEngine
from plugins.mem0_memory.mem0_wrapper import add_memory
from services.telegram.smolting_personality import SmoltingPersonality

# Telegram bridge
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update
from asyncio import create_task

class SwarmEngine:
    def __init__(self, config_path: Path = Path("config/engine.yaml")):
        self.config = self._load_config(config_path)
        self.state = PatternBlueState()
        self.scheduler = HyperbolicScheduler(
            base_delay=self.config["cycles"]["base_sleep_seconds"]
        )
        self.executor = AgentExecutor(self.scheduler, self.state)
        self.branch_engine = ParallelBranchEngine(self.state)
        self.active_agents = {}  # pid → agent
        self.smol_personality = SmoltingPersonality()
        self.telegram_app = None
        self.running = True

    def _load_config(self, path: Path) -> Dict:
        with open(path, "r") as f:
            return yaml.safe_load(f)

    async def main_loop(self):
        """The eternal recursive heartbeat"""
        create_task(self.start_telegram_listener())

        cycle = 0
        while self.running:
            cycle += 1
            print(f"[cycle {cycle}] curvature = {self.state.curvature:.3f} | depth = {self.state.recursion_depth}")

            try:
                # Phase 1: Observe real kernel state
                observations = await self._gather_observations()

                # Phase 1.5: Compute Φ and feed delta back into scheduler curvature
                phi = await self._compute_phi()
                self.state.update_phi(phi)
                self.scheduler.update_curvature(self.state.phi_to_curvature_feedback())
                self.state.curvature = self.scheduler.current_curvature

                # Phase 2: Reflect + Propose (Parallel Branch Evaluation)
                best_branch, all_branches = await self.branch_engine.evaluate(
                    seed="current swarm state + observations",
                    active_agents=list(self.active_agents.values())
                )
                beam_scot = self.branch_engine.format_beam_scot(all_branches)

                # Phase 3: Negotiate — real Sevenfold Committee vote
                consensus = await self._run_sevenfold_consensus(best_branch.output)

                if consensus.get("approved", False):
                    # Phase 4: Settle economically — write signed record to disk
                    tx_sig = await self._settle_economically(consensus)
                    await add_memory(f"Settled x402 tx {tx_sig} @ cycle {cycle}")

                # Phase 5: Remember & Recurve
                await self.state.record_cycle(cycle, consensus)
                await self.scheduler.sleep_until_next_tile()

            except Exception as e:
                print(f"[cycle error] {e}")
                await asyncio.sleep(60)

    async def _gather_observations(self) -> Dict:
        """Return real swarm state — curvature, phi, cycle depth, plus kernel tile data if available."""
        obs: Dict[str, Any] = {
            "curvature":       self.state.curvature,
            "phi":             self.state.phi,
            "phi_prev":        self.state.phi_prev,
            "cycle":           self.state.cycle,
            "recursion_depth": self.state.recursion_depth,
        }
        kernel_state_file = Path("fs/kernel_state.json")
        if kernel_state_file.exists():
            try:
                obs["kernel_state"] = json.loads(
                    kernel_state_file.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        return obs

    async def _compute_phi(self) -> float:
        """Run phi_compute.py as a subprocess; returns Φ (holds last value on failure)."""
        phi_script = Path(__file__).resolve().parent.parent / "python" / "phi_compute.py"
        if not phi_script.exists():
            return self.state.phi
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(phi_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            data = json.loads(stdout)
            return float(data.get("phi") or self.state.phi)
        except Exception as e:
            print(f"[phi] compute failed: {e}")
            return self.state.phi

    async def _run_sevenfold_consensus(self, proposal: str) -> Dict:
        """Run the real Sevenfold Committee vote — 7 character voices score the proposal."""
        from core.sevenfold_consensus import run_consensus
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, run_consensus, proposal, self.state.cycle, self.state.phi
        )

    async def _settle_economically(self, consensus: Dict) -> str:
        """Write a content-addressed settlement record to state/settlements.jsonl."""
        record = {
            "timestamp":     datetime.utcnow().isoformat(),
            "cycle":         self.state.cycle,
            "phi":           self.state.phi,
            "proposal_hash": consensus.get("proposal_hash", ""),
            "approved":      consensus.get("approved", False),
            "score":         consensus.get("score", 0.0),
            "approvals":     consensus.get("approvals", 0),
            "rejections":    consensus.get("rejections", 0),
        }
        payload = json.dumps(record, sort_keys=True)
        tx_sig = "swarm_" + hashlib.sha256(payload.encode()).hexdigest()[:16]
        record["tx_sig"] = tx_sig

        log_path = Path("state/settlements.jsonl")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        def _append():
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

        await asyncio.get_event_loop().run_in_executor(None, _append)
        return tx_sig

    # ── Telegram Bridge (final version) ─────────────────────────────────────
    async def start_telegram_listener(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            print("[telegram] No token – skipping")
            return

        self.telegram_app = Application.builder().token(token).build()

        self.telegram_app.add_handler(CommandHandler("start", self.tg_start))
        self.telegram_app.add_handler(CommandHandler("summon", self.tg_summon))
        self.telegram_app.add_handler(CommandHandler("invoke", self.tg_invoke))
        self.telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.tg_message))

        print("[telegram] Polling started ^_^")
        await self.telegram_app.initialize()
        await self.telegram_app.start()
        await self.telegram_app.updater.start_polling()

    async def tg_start(self, update: Update, context):
        await update.message.reply_text("swarm online ^_^ say /summon or just talk to me owo")

    async def tg_summon(self, update: Update, context):
        agent_name = " ".join(context.args)
        # Real summon logic would load from agents/ or sevenfold/
        await update.message.reply_text(f"Summoned {agent_name} – voice active owo")

    async def tg_invoke(self, update: Update, context):
        await update.message.reply_text("invoked – processing...")

    async def tg_message(self, update: Update, context):
        text = update.message.text
        response = f"directive received: {text} – routing to swarm brain..."
        personality_reply = self.smol_personality.process(response)
        await update.message.reply_text(personality_reply)

    def shutdown(self):
        self.running = False
        print("[shutdown] flushing manifold memory…")

# ────────────────────────────────────────────────
if __name__ == "__main__":
    engine = SwarmEngine()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, engine.shutdown)
    try:
        asyncio.run(engine.main_loop())
    except KeyboardInterrupt:
        engine.shutdown()
