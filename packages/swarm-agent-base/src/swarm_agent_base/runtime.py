"""``AgentRuntime`` — the asyncio supervisor that every autonomous swarm agent
needs: heartbeat, SwarmInbox poll (with reap-on-read), soul-update timer, mesh
``thought`` exchange, capability publish. Domain and autonomous-post loops are
added with :meth:`add_periodic`.

Minimal use::

    rt = AgentRuntime(name="degen", character=char, capabilities=["pools"])

    @rt.on_task("pools")
    async def _pools(payload, msg):
        return {"result": format_pool_context(await get_pool_context())}

    rt.add_periodic(monitor_cycle, 60, name="pool_monitor")
    asyncio.run(rt.run())
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from swarm_core.security import inbox as _inbox

from .llm import LLM
from .memory import ActivityLog
from .persona import build_system_prompt
from .soul import SoulStore
from .thought import handle_thought, initiate_thought

logger = logging.getLogger(__name__)

_RESULT_TYPES = {"deploy_result", "task_result", "governance_result"}
_REQUEST_TYPES = {"deploy_request", "task_request", "governance_request"}

TaskHandler = Callable[[dict, dict], Awaitable[Optional[dict]]]


class AgentRuntime:
    def __init__(
        self,
        *,
        name: str,
        character: dict | None = None,
        llm: LLM | None = None,
        activity: ActivityLog | None = None,
        soul: SoulStore | None = None,
        capabilities: list[str] | None = None,
        persona_line: str | None = None,
        heartbeat_meta: dict | None = None,
        thought_peers: list[str] | None = None,
        thought_interval_h: float = 7.0,
        inbox_poll_s: int = 60,
        heartbeat_s: int = 180,
        soul_update_s: int = 7200,
        alias_names: list[str] | None = None,
    ) -> None:
        self.name = name
        self.aliases = alias_names or []
        self.character = character or {"name": name}
        self.llm = llm or LLM()
        self.activity = activity or ActivityLog(name)
        self.soul = soul
        self.capabilities = capabilities or ["thought_exchange"]
        self.persona_line = persona_line or f"You are {name}, a node in the REDACTED AI swarm."
        self.heartbeat_meta = heartbeat_meta or {"source": name, "status": "online"}
        self.thought_peers = thought_peers or []
        self.thought_interval_h = thought_interval_h
        self._inbox_poll_s = inbox_poll_s
        self._heartbeat_s = heartbeat_s
        self._soul_update_s = soul_update_s

        self._task_handlers: dict[str, TaskHandler] = {}
        self._result_cb: Optional[Callable[[dict], Awaitable[None]]] = None
        self._broadcast_cb: Optional[Callable[[dict], Awaitable[None]]] = None
        self._start_cb: Optional[Callable[[], Awaitable[None]]] = None
        self._periodics: list[tuple[Callable[[], Awaitable[None]], float, Optional[float], float, str]] = []
        self._stop = asyncio.Event()

    # -- registration ---------------------------------------------------------
    def on_task(self, verb: str):
        def deco(fn: TaskHandler) -> TaskHandler:
            self._task_handlers[verb.lower()] = fn
            return fn
        return deco

    def register_task(self, verb: str, fn: TaskHandler) -> None:
        self._task_handlers[verb.lower()] = fn

    def on_result(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        self._result_cb = fn

    def on_broadcast(self, fn: Callable[[dict], Awaitable[None]]) -> None:
        self._broadcast_cb = fn

    def on_start(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._start_cb = fn

    def add_periodic(
        self,
        fn: Callable[[], Awaitable[None]],
        interval_s: float,
        *,
        first_s: float | None = None,
        jitter: float = 0.0,
        name: str = "",
    ) -> None:
        """Run ``fn`` every ``interval_s`` (+/- ``jitter`` fraction). ``first_s``
        overrides the initial delay."""
        self._periodics.append((fn, float(interval_s), first_s, float(jitter), name or fn.__name__))

    # -- persona helpers -------------------------------------------------------
    def system_prompt(self, extra: str = "") -> str:
        soul_block = self.soul.for_prompt() if self.soul else ""
        base = build_system_prompt(self.character, extra=extra)
        return (base + ("\n" + soul_block if soul_block else "")).strip()

    async def _llm_call(self, messages: list[dict]) -> str:
        return await self.llm.acomplete(messages, max_tokens=500)

    # -- loops -------------------------------------------------------------
    def _names(self) -> list[str]:
        return [self.name, *self.aliases]

    async def _heartbeat_loop(self) -> None:
        beat = 0
        while not self._stop.is_set():
            try:
                for n in self._names():
                    _inbox.heartbeat(n, {**self.heartbeat_meta,
                                         "ts": datetime.now(timezone.utc).isoformat()})
                if beat % max(1, int(21600 / self._heartbeat_s)) == 0:
                    await self._publish_caps()
            except Exception as e:  # noqa: BLE001
                logger.debug("[%s] heartbeat failed: %s", self.name, e)
            beat += 1
            await self._sleep(self._heartbeat_s)

    async def _publish_caps(self) -> None:
        try:
            from swarm_tg.task_client import publish_capabilities

            for n in self._names():
                await publish_capabilities(n, self.capabilities)
        except Exception as e:  # noqa: BLE001
            logger.debug("[%s] cap publish failed: %s", self.name, e)

    async def _inbox_loop(self) -> None:
        await self._sleep(10)
        while not self._stop.is_set():
            try:
                await self._poll_inbox_once()
            except Exception as e:  # noqa: BLE001
                logger.error("[%s] inbox poll error: %s", self.name, e)
            await self._sleep(self._inbox_poll_s)

    async def _poll_inbox_once(self) -> None:
        pending = _inbox.read_pending(self.name)
        if not pending:
            if random.random() < 0.05:
                _inbox.prune_old_messages()
            return

        for msg in pending[:20]:
            mid = msg.get("id")
            mtype = (msg.get("type") or "").lower()
            frm = msg.get("from", "?")
            to = (msg.get("to") or "").lower()
            if not mid:
                continue

            if to == "all":
                if mtype not in ("heartbeat",) and self._broadcast_cb:
                    try:
                        await self._broadcast_cb(msg)
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[%s] broadcast cb error: %s", self.name, e)
                continue
            if to not in (n.lower() for n in self._names()):
                continue

            if not _inbox.claim_message(mid):
                continue
            try:
                await self._dispatch(mid, mtype, frm, msg)
            except Exception as e:  # noqa: BLE001
                logger.error("[%s] dispatch %s (%s): %s", self.name, mid, mtype, e)
                _inbox.complete_message(mid, error=str(e)[:300])

        if random.random() < 0.05:
            _inbox.prune_old_messages()

    async def _dispatch(self, mid: str, mtype: str, frm: str, msg: dict) -> None:
        if mtype == "thought":
            soul_block = self.soul.for_prompt() if self.soul else ""
            reply_id = await handle_thought(
                msg, self._llm_call, my_agent=self.name,
                persona_line=self.persona_line, soul_block=soul_block,
            )
            _inbox.complete_message(mid, result={"replied": reply_id})
            self.activity.record(kind="thought", title=f"thought from {frm}",
                                 body=f"answered thought from {frm} (reply={reply_id})")
            return

        if mtype in _REQUEST_TYPES:
            payload = msg.get("payload") or {}
            verb = str(payload.get("verb") or payload.get("task_type")
                       or payload.get("action") or "").lower()
            handler = (self._task_handlers.get(verb)
                       or self._task_handlers.get(mtype)
                       or self._task_handlers.get("*"))
            if not handler:
                _inbox.complete_message(mid, error=f"no handler for verb {verb!r} / type {mtype!r}")
                return
            result = await handler(payload, msg)
            _inbox.complete_message(mid, result=result or {"ok": True})
            self.activity.record(kind="inbox_event", title=f"{verb or mtype} from {frm}",
                                 body=f"handled {verb or mtype} from {frm}")
            return

        if mtype in _RESULT_TYPES:
            if self._result_cb:
                await self._result_cb(msg)
            _inbox.complete_message(mid, result={"ack": True})
            self.activity.record(kind="inbox_result", title=f"{mtype} from {frm}",
                                 body=str(msg.get("payload"))[:400])
            return

        _inbox.complete_message(mid, result={"ack": True})
        self.activity.record(kind="inbox_event", title=f"{mtype} from {frm}",
                             body=f"{frm} -> {mtype}")

    async def _soul_loop(self) -> None:
        if not self.soul:
            return
        await self._sleep(min(300, self._soul_update_s))
        while not self._stop.is_set():
            try:
                if await self.soul.update(self.llm, self.activity.soul_context(n=60)):
                    logger.info("[%s] soul updated", self.name)
            except Exception as e:  # noqa: BLE001
                logger.debug("[%s] soul update failed: %s", self.name, e)
            await self._sleep(self._soul_update_s)

    async def _thought_initiate_loop(self) -> None:
        if not self.thought_peers or self.thought_interval_h <= 0:
            return
        interval = self.thought_interval_h * 3600
        await self._sleep(max(300, interval * 0.25))
        while not self._stop.is_set():
            peer = random.choice(self.thought_peers)
            try:
                topic = await self._pick_thought_topic()
                if topic:
                    initiate_thought(self.name, peer, topic["topic"], topic["stance"],
                                     topic.get("question", ""))
                    self.activity.record(kind="thought", title=f"initiated with {peer}",
                                         body=topic["topic"])
            except Exception as e:  # noqa: BLE001
                logger.debug("[%s] thought initiate failed: %s", self.name, e)
            await self._sleep(interval)

    async def _pick_thought_topic(self) -> Optional[dict]:
        """Default: ask the LLM for one short thought seed from recent activity.
        Agents can override by setting ``runtime.thought_topic_fn``."""
        fn = getattr(self, "thought_topic_fn", None)
        if fn:
            return await fn()
        ctx = self.activity.soul_context(n=20) or "(no recent activity)"
        try:
            raw = await self.llm.achat(
                self.system_prompt(),
                "In one sentence, share a genuine thought or observation from your "
                "domain worth trading with a peer agent. Recent context:\n" + ctx,
                max_tokens=120, temperature=0.9,
            )
        except Exception:
            return None
        raw = (raw or "").strip()
        return {"topic": raw[:120], "stance": raw[:400]} if raw else None

    # -- misc -------------------------------------------------------------
    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _run_periodic(self, fn, interval, first, jitter, pname) -> None:
        delay = first if first is not None else min(interval, 30)
        await self._sleep(delay)
        while not self._stop.is_set():
            try:
                await fn()
            except Exception as e:  # noqa: BLE001
                logger.error("[%s] periodic %s error: %s", self.name, pname, e)
            span = interval * (1 + random.uniform(-jitter, jitter)) if jitter else interval
            await self._sleep(max(0.01, span))

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info("[%s] starting — caps=%s peers=%s soul=%s",
                    self.name, self.capabilities, self.thought_peers,
                    self.soul.status_line() if self.soul else "none")
        for n in self._names():
            _inbox.heartbeat(n, {**self.heartbeat_meta, "status": "booting"})
        await self._publish_caps()
        if self._start_cb:
            try:
                await self._start_cb()
            except Exception as e:  # noqa: BLE001
                logger.error("[%s] on_start error: %s", self.name, e)

        coros = [
            self._heartbeat_loop(),
            self._inbox_loop(),
            self._soul_loop(),
            self._thought_initiate_loop(),
        ]
        for fn, interval, first, jitter, pname in self._periodics:
            coros.append(self._run_periodic(fn, interval, first, jitter, pname))

        try:
            await asyncio.gather(*coros)
        except asyncio.CancelledError:
            pass
        finally:
            self._stop.set()
