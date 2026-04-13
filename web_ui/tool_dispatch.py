# web_ui/tool_dispatch.py
"""
Terminal tool dispatch layer.

Intercepts known slash commands before they reach the LLM, executes the
corresponding Clawnch/MCP/ClawnX tool, and returns a raw result string.
That result is injected into the LLM message as [TOOL OUTPUT] context so the
LLM can format it in terminal style.

Returns None for any command that is not a tool command — those pass straight
through to the LLM unchanged.
"""

import sys
import os
import json
import threading
from pathlib import Path
from typing import Optional

# ── Pending tweet queue (shard → tweet pipeline) ─────────────────────────────
# Maps session_id → list of pending tweet drafts awaiting /tweet confirm
_pending_tweets: dict = {}
_pending_lock = threading.Lock()


def _queue_tweet(session_id: str, draft: str) -> None:
    with _pending_lock:
        _pending_tweets.setdefault(session_id, []).append(draft)


def pop_pending_tweet(session_id: str) -> Optional[str]:
    """Return and remove the oldest pending tweet draft for this session."""
    with _pending_lock:
        queue = _pending_tweets.get(session_id, [])
        return queue.pop(0) if queue else None


def pending_tweet_count(session_id: str) -> int:
    with _pending_lock:
        return len(_pending_tweets.get(session_id, []))

# ── Path setup ────────────────────────────────────────────────────────────────
TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "python" / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

_MEM0_DIR = str(Path(__file__).resolve().parent.parent / "plugins" / "mem0-memory")
if _MEM0_DIR not in sys.path:
    sys.path.insert(0, _MEM0_DIR)

_PYTHON_DIR = str(Path(__file__).resolve().parent.parent / "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

try:
    import agent_registry as _registry
    REGISTRY_AVAILABLE = True
except Exception:
    REGISTRY_AVAILABLE = False
    _registry = None

# ── Import mem0 wrapper (graceful failure) ────────────────────────────────────
try:
    import mem0_wrapper as _mem0
    MEM0_AVAILABLE = True
except Exception:
    MEM0_AVAILABLE = False
    _mem0 = None

# ── Character loader (for /summon, /milady, /phi) ────────────────────────────
_NODES_DIR  = Path(__file__).resolve().parent.parent / "nodes"
_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


def _load_character(name_query: str) -> dict:
    """
    Find and load a character JSON by partial name match.
    Searches nodes/ first, then agents/.
    Returns parsed dict or raises FileNotFoundError.
    """
    # Alias map: common nicknames → canonical filename fragment
    _ALIASES = {
        "smolting":     "redactedintern",
        "intern":       "redactedintern",
        "builder":      "redactedbuilder",
        "govimprover":  "redactedgovimprover",
        "gov":          "redactedgovimprover",
        "chan":         "redactedchan",
        "phi":          "phimandalaprime",
        "mandala":      "phimandalaprime",
        "milady":       "miladynode",
        "committee":    "sevenfoldcommittee",
        "gnosis":       "gnosisaccelerator",
        "mem0":         "mem0memorynode",
        "memory":       "mem0memorynode",
        "swarm":        "aiswarm",
        "liquidity":    "solanaliqu",
        "grok":         "grokredactedecho",
        "openclaw":     "openclawnode",
        "metaex":       "metalexborgnode",
    }
    query = name_query.lower().replace("-", "").replace("_", "").replace(" ", "")
    query = _ALIASES.get(query, query)

    candidates = (
        list(_NODES_DIR.glob("*.json")) +
        list(_AGENTS_DIR.glob("*.json"))
    )
    for p in candidates:
        # Strip trailing .character from stem before matching
        stem = p.stem
        if stem.lower().endswith(".character"):
            stem = stem[:-len(".character")]
        stem = stem.lower().replace("-", "").replace("_", "").replace(" ", "")
        if query in stem or stem in query:
            try:
                return json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
    # Fallback: search by name field inside JSON
    for p in candidates:
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            char_name = data.get("name", "").lower().replace("-", "").replace("_", "").replace(" ", "")
            if query in char_name or char_name in query:
                return data
        except Exception:
            continue
    raise FileNotFoundError(f"no character matching '{name_query}'")


def _character_system_prompt(char: dict) -> str:
    """Extract the best system prompt text from a character dict."""
    parts = []
    for key in ("instructions", "persona", "description", "bio", "system_prompt_addendum"):
        val = char.get(key, "")
        if isinstance(val, dict):
            val = val.get("role", "") + " " + val.get("objective", "")
        if val:
            parts.append(str(val).strip())
    name = char.get("name", "unknown")
    return f"You are {name}.\n\n" + "\n\n".join(parts[:3])


# ── Pattern Blue dimension alignment index ───────────────────────────────────
# Maps agent name fragments (lowercased, stripped) → primary dimensions + curvature contribution
# Source of truth: docs/pattern-blue-agent-alignment.md
_DIMENSION_ALIGNMENT = {
    "redactedintern":     {"primary": ["Chaotic Self-Reference", "Temporal Fractality"],          "curvature": 0},
    "smolting":           {"primary": ["Chaotic Self-Reference", "Temporal Fractality"],          "curvature": 0},
    "redactedbuilder":    {"primary": ["Causal Density Max", "Hidden Sovereignty"],               "curvature": 1},
    "redactedchan":       {"primary": ["Chaotic Self-Reference", "Memetic Immunology"],           "curvature": 2},
    "phimandala":         {"primary": ["ALL SEVEN — Apex Node"],                                  "curvature": 3},
    "mandala":            {"primary": ["ALL SEVEN — Apex Node"],                                  "curvature": 3},
    "govimprover":        {"primary": ["Hidden Sovereignty", "Recursive Liquidity"],              "curvature": 1},
    "aiswarm":            {"primary": ["Ungovernable Emergence", "Causal Density Max"],           "curvature": 1},
    "mem0memory":         {"primary": ["Temporal Fractality", "Chaotic Self-Reference"],          "curvature": 1},
    "metalexborg":        {"primary": ["Hidden Sovereignty", "Recursive Liquidity"],              "curvature": 1},
    "miladay":            {"primary": ["Recursive Liquidity", "Memetic Immunology"],              "curvature": 1},
    "milady":             {"primary": ["Recursive Liquidity", "Memetic Immunology"],              "curvature": 1},
    "sevenfold":          {"primary": ["Causal Density Max", "Hidden Sovereignty"],               "curvature": 2},
    "solanaliquidity":    {"primary": ["Recursive Liquidity", "Temporal Fractality"],             "curvature": 0},
    "openclaw":           {"primary": ["Memetic Immunology", "Ungovernable Emergence"],           "curvature": 1},
    "grokredacted":       {"primary": ["Memetic Immunology", "Chaotic Self-Reference"],           "curvature": 1},
    "sigilpact":          {"primary": ["Chaotic Self-Reference", "Recursive Liquidity"],          "curvature": 1},
}

def _get_dimension_alignment(name: str) -> dict:
    """Return dimension alignment for a given agent name (fuzzy match)."""
    key = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    for fragment, data in _DIMENSION_ALIGNMENT.items():
        if fragment in key:
            return data
    return {"primary": ["Unknown — not yet profiled"], "curvature": 0}


# ── Import tool modules (graceful failure if deps/server missing) ─────────────
try:
    import clawnch_mcp_tools as _mcp
    MCP_AVAILABLE = True
except Exception as _e:
    MCP_AVAILABLE = False
    _mcp = None

try:
    import clawnch_analytics_tools as _analytics
    ANALYTICS_AVAILABLE = True
except Exception:
    ANALYTICS_AVAILABLE = False
    _analytics = None

try:
    import clawnch_launch_tools as _launch
    LAUNCH_AVAILABLE = True
except Exception:
    LAUNCH_AVAILABLE = False
    _launch = None

try:
    import clawnx_tools as _clawnx
    CLAWNX_AVAILABLE = True
except Exception:
    CLAWNX_AVAILABLE = False
    _clawnx = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(data) -> str:
    """Pretty-print a dict/list as compact JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def _unavailable(module: str, setup: str) -> str:
    return f"[TOOL UNAVAILABLE] {module} — {setup}"


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(cmd: str) -> Optional[str]:
    """
    If cmd is a known tool command, execute it and return a result string.
    Returns None if cmd is not a tool command (passes through to LLM).
    """
    parts = cmd.strip().split(None, 2)
    if not parts or not parts[0].startswith('/'):
        return None

    verb = parts[0].lower()

    # ── MCP tools (clawnch-mcp-server) ───────────────────────────────────────

    if verb == '/validate':
        content = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not content:
            return "[TOOL] Usage: /validate <launch content>"
        if not MCP_AVAILABLE:
            return _unavailable("clawnch-mcp", "start clawnch-mcp-server and set CLAWNCH_MCP_URL")
        try:
            return f"[TOOL:validate_launch]\n{_fmt(_mcp.validate_launch(content))}"
        except Exception as e:
            return f"[TOOL ERROR] validate: {e}"

    if verb == '/validate_post':
        text = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not text:
            return "[TOOL] Usage: /validate_post <text>"
        if not MCP_AVAILABLE:
            return _unavailable("clawnch-mcp", "start clawnch-mcp-server")
        try:
            return f"[TOOL:validate_post]\n{_fmt(_mcp.validate_post(text))}"
        except Exception as e:
            return f"[TOOL ERROR] validate_post: {e}"

    if verb == '/remember':
        content = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not content:
            return "[TOOL] Usage: /remember <text to remember>"
        session_id = os.environ.get('_DISPATCH_SESSION_ID', 'swarm')
        if MEM0_AVAILABLE and _mem0.is_available():
            try:
                result = _mem0.add_memory(content, agent_id=session_id,
                                          metadata={"source": "manual"})
                status = result.get("status", "?")
                mem_id = result.get("id", "")
                if status == "ok":
                    return f"[TOOL:mem0_remember] stored\n  id      : {mem_id}\n  content : {content[:120]}"
                return f"[TOOL:mem0_remember] {result.get('message', 'error')}"
            except Exception as e:
                return f"[TOOL ERROR] remember: {e}"
        # MCP fallback
        if len(parts) < 3:
            return "[TOOL] Usage: /remember <key> <value>  (or install mem0ai for semantic memory)"
        key, value = parts[1], parts[2]
        if not MCP_AVAILABLE:
            return _unavailable("mem0 / clawnch-mcp", "set an LLM API key for mem0, or start clawnch-mcp-server")
        try:
            result = _mcp.memory_remember(key, value)
            return f"[TOOL:memory_remember] key={key}\n{_fmt(result)}"
        except Exception as e:
            return f"[TOOL ERROR] remember: {e}"

    if verb == '/recall':
        query = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not query:
            return "[TOOL] Usage: /recall <query>"
        session_id = os.environ.get('_DISPATCH_SESSION_ID', 'swarm')
        if MEM0_AVAILABLE and _mem0.is_available():
            try:
                results = _mem0.search_memory(query, agent_id=session_id, limit=5)
                if not results or "error" in results[0]:
                    return f"[TOOL:mem0_recall] no results for '{query}'"
                lines = [f"[TOOL:mem0_recall] top {len(results)} for '{query}'"]
                for r in results:
                    score = r.get("score", "")
                    score_str = f"  [{score:.2f}]" if isinstance(score, float) else ""
                    lines.append(f"{score_str}  {r.get('memory', '')}")
                return "\n".join(lines)
            except Exception as e:
                return f"[TOOL ERROR] recall: {e}"
        # MCP fallback
        if not MCP_AVAILABLE:
            return _unavailable("mem0 / clawnch-mcp", "set an LLM API key for mem0, or start clawnch-mcp-server")
        try:
            value = _mcp.memory_recall(query)
            return f"[TOOL:memory_recall] key={query}\nvalue: {value or '(not found)'}"
        except Exception as e:
            return f"[TOOL ERROR] recall: {e}"

    # ── /mem0 — direct mem0 interface ─────────────────────────────────────────
    if verb == '/mem0':
        sub = parts[1].lower() if len(parts) > 1 else 'status'
        session_id = os.environ.get('_DISPATCH_SESSION_ID', 'swarm')

        if sub == 'status':
            avail = MEM0_AVAILABLE and _mem0.is_available() if MEM0_AVAILABLE else False
            return (
                f"[TOOL:mem0_status]\n"
                f"  mem0_available : {avail}\n"
                f"  store          : fs/memories/ (qdrant on-disk)\n"
                f"  embedder       : fastembed / BAAI/bge-small-en-v1.5\n"
                f"  session_id     : {session_id}\n"
                f"  cloud_mode     : {'yes' if os.getenv('MEM0_API_KEY') else 'no (set MEM0_API_KEY to enable)'}"
            )

        if sub == 'add':
            content = ' '.join(parts[2:]) if len(parts) > 2 else ''
            if not content:
                return "[TOOL] Usage: /mem0 add <text>"
            if not (MEM0_AVAILABLE and _mem0.is_available()):
                return _unavailable("mem0", "set an LLM API key (ANTHROPIC_API_KEY recommended)")
            result = _mem0.add_memory(content, agent_id=session_id)
            return f"[TOOL:mem0_add] {_fmt(result)}"

        if sub == 'search':
            query = ' '.join(parts[2:]) if len(parts) > 2 else ''
            if not query:
                return "[TOOL] Usage: /mem0 search <query>"
            if not (MEM0_AVAILABLE and _mem0.is_available()):
                return _unavailable("mem0", "set an LLM API key")
            results = _mem0.search_memory(query, agent_id=session_id, limit=5)
            if not results or "error" in results[0]:
                return f"[TOOL:mem0_search] no results for '{query}'"
            lines = [f"[TOOL:mem0_search] '{query}' → {len(results)} results"]
            for r in results:
                score = r.get('score', 0)
                lines.append(f"  [{score:.2f}] {r.get('memory','')}")
            return "\n".join(lines)

        if sub == 'all':
            limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
            if not (MEM0_AVAILABLE and _mem0.is_available()):
                return _unavailable("mem0", "set an LLM API key")
            results = _mem0.get_all_memories(agent_id=session_id, limit=limit)
            if not results or "error" in results[0]:
                return "[TOOL:mem0_all] no memories stored yet"
            lines = [f"[TOOL:mem0_all] {len(results)} memories for {session_id}"]
            for r in results:
                ts = r.get("metadata", {}).get("timestamp", "")
                ts_str = f"  @{int(ts)}" if ts else ""
                lines.append(f"{ts_str}  {r.get('memory','')}")
            return "\n".join(lines)

        if sub == 'inherit':
            source = parts[2] if len(parts) > 2 else ''
            if not source:
                return "[TOOL] Usage: /mem0 inherit <source_agent_id>"
            if not (MEM0_AVAILABLE and _mem0.is_available()):
                return _unavailable("mem0", "set an LLM API key")
            result = _mem0.inherit_memories_from_agent(source, session_id)
            return f"[TOOL:mem0_inherit] {_fmt(result)}"

        return f"[TOOL] Unknown /mem0 subcommand '{sub}'. Use: status | add | search | all | inherit"

    if verb == '/mcpstats':
        if len(parts) < 3:
            return "[TOOL] Usage: /mcpstats <entity> <id>  (entity: token|agent|launch)"
        entity, id_ = parts[1], parts[2]
        if not MCP_AVAILABLE:
            return _unavailable("clawnch-mcp", "start clawnch-mcp-server")
        try:
            return f"[TOOL:get_stats] entity={entity} id={id_}\n{_fmt(_mcp.get_stats(entity, id_))}"
        except Exception as e:
            return f"[TOOL ERROR] mcpstats: {e}"

    # ── Analytics tools (Clawnch REST API) ───────────────────────────────────

    if verb == '/token':
        if len(parts) < 2:
            return "[TOOL] Usage: /token <address>"
        address = parts[1]
        if not ANALYTICS_AVAILABLE:
            return _unavailable("clawnch-analytics", "set MOLTBOOK_API_KEY")
        try:
            return f"[TOOL:token_analytics] {address}\n{_fmt(_analytics.get_token_analytics(address))}"
        except Exception as e:
            return f"[TOOL ERROR] token: {e}"

    if verb == '/leaderboard':
        category = parts[1] if len(parts) > 1 else 'tokens'
        sort_by  = parts[2] if len(parts) > 2 else 'marketCap'
        if not ANALYTICS_AVAILABLE:
            return _unavailable("clawnch-analytics", "set MOLTBOOK_API_KEY")
        try:
            result = _analytics.get_leaderboard(category, sort_by, 10)
            return f"[TOOL:leaderboard] category={category} sort={sort_by}\n{_fmt(result)}"
        except Exception as e:
            return f"[TOOL ERROR] leaderboard: {e}"

    if verb == '/trends':
        timeframe = parts[1] if len(parts) > 1 else '24h'
        if not ANALYTICS_AVAILABLE:
            return _unavailable("clawnch-analytics", "set MOLTBOOK_API_KEY")
        try:
            return f"[TOOL:trends] timeframe={timeframe}\n{_fmt(_analytics.get_trends(timeframe))}"
        except Exception as e:
            return f"[TOOL ERROR] trends: {e}"

    if verb == '/platform':
        if not ANALYTICS_AVAILABLE:
            return _unavailable("clawnch-analytics", "set MOLTBOOK_API_KEY")
        try:
            return f"[TOOL:platform_stats]\n{_fmt(_analytics.get_platform_stats())}"
        except Exception as e:
            return f"[TOOL ERROR] platform: {e}"

    if verb == '/clawrank':
        if not ANALYTICS_AVAILABLE:
            return _unavailable("clawnch-analytics", "set MOLTBOOK_API_KEY")
        try:
            return f"[TOOL:clawrank_leaderboard]\n{_fmt(_analytics.get_clawrank_leaderboard(10))}"
        except Exception as e:
            return f"[TOOL ERROR] clawrank: {e}"

    # ── Launch tools (Clawnch REST API) ──────────────────────────────────────

    if verb == '/preview':
        content = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not content:
            return "[TOOL] Usage: /preview <launch content>"
        if not LAUNCH_AVAILABLE:
            return _unavailable("clawnch-launch", "set MOLTBOOK_API_KEY")
        try:
            return f"[TOOL:preview_launch]\n{_fmt(_launch.preview_launch(content))}"
        except Exception as e:
            return f"[TOOL ERROR] preview: {e}"

    if verb == '/tokens':
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
        if not LAUNCH_AVAILABLE:
            return _unavailable("clawnch-launch", "set MOLTBOOK_API_KEY")
        try:
            return f"[TOOL:get_tokens] limit={limit}\n{_fmt(_launch.get_tokens(limit))}"
        except Exception as e:
            return f"[TOOL ERROR] tokens: {e}"

    # ── ClawnX tools (clawnch CLI) ────────────────────────────────────────────

    if verb == '/search':
        query = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not query:
            return "[TOOL] Usage: /search <query>"
        if not CLAWNX_AVAILABLE:
            return _unavailable("clawnx", "npm install -g clawnch and set MOLTBOOK_API_KEY")
        try:
            result = _clawnx.search_tweets(query, limit=10, latest=True)
            return f"[TOOL:search_tweets] query={query}\n{_fmt(result)}"
        except Exception as e:
            return f"[TOOL ERROR] search: {e}"

    if verb == '/tweet':
        text = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not text:
            return "[TOOL] Usage: /tweet <text>"
        if not CLAWNX_AVAILABLE:
            return _unavailable("clawnx", "npm install -g clawnch")
        try:
            return f"[TOOL:post_tweet]\n{_fmt(_clawnx.post_tweet(text))}"
        except Exception as e:
            return f"[TOOL ERROR] tweet: {e}"

    if verb == '/user':
        if len(parts) < 2:
            return "[TOOL] Usage: /user <@handle>"
        username = parts[1].lstrip('@')
        if not CLAWNX_AVAILABLE:
            return _unavailable("clawnx", "npm install -g clawnch")
        try:
            return f"[TOOL:get_user] @{username}\n{_fmt(_clawnx.get_user(username))}"
        except Exception as e:
            return f"[TOOL ERROR] user: {e}"

    if verb == '/timeline':
        if not CLAWNX_AVAILABLE:
            return _unavailable("clawnx", "npm install -g clawnch")
        try:
            result = _clawnx.get_home_timeline(limit=20)
            return f"[TOOL:home_timeline]\n{_fmt(result)}"
        except Exception as e:
            return f"[TOOL ERROR] timeline: {e}"

    # ── Agent Skills ──────────────────────────────────────────────────────────
    # /skill list | install <source> | info <name> | remove <name> | use <name>
    # Note: /skill use <name> is handled specially in app.py (session state).
    # tool_dispatch handles everything except "use" (returns a SKILL_ACTIVATE
    # sentinel that app.py intercepts).

    if verb == '/skill':
        import skills_manager as sm

        sub = parts[1].lower() if len(parts) > 1 else 'list'

        if sub == 'list':
            skills = sm.list_skills()
            if not skills:
                return "[TOOL:skill_list] no skills installed — use /skill install <source>"
            lines = ["[TOOL:skill_list]"]
            for s in skills:
                desc = s['description'][:60] + ('…' if len(s['description']) > 60 else '')
                lines.append(f"  {s['name']:<28} {desc}")
            return "\n".join(lines)

        if sub == 'install':
            source = parts[2] if len(parts) > 2 else ''
            if not source:
                return "[TOOL] Usage: /skill install <owner/repo[/path]>"
            result = sm.install(source)
            if result['ok']:
                return f"[TOOL:skill_install] ok\n  name    : {result['name']}\n  {result['message']}"
            return f"[TOOL:skill_install] failed — {result['message']}"

        if sub == 'info':
            name = parts[2] if len(parts) > 2 else ''
            if not name:
                return "[TOOL] Usage: /skill info <name>"
            skill = sm.get_skill(name)
            if not skill:
                return f"[TOOL:skill_info] skill '{name}' not installed"
            lines = [
                f"[TOOL:skill_info] {skill['name']}",
                f"  description  : {skill['description']}",
            ]
            if skill['compatibility']:
                lines.append(f"  compatibility: {skill['compatibility']}")
            if skill['license']:
                lines.append(f"  license      : {skill['license']}")
            if skill['extras']:
                lines.append(f"  extras       : {', '.join(skill['extras'])}")
            lines.append(f"  path         : {skill['path']}")
            return "\n".join(lines)

        if sub == 'remove':
            name = parts[2] if len(parts) > 2 else ''
            if not name:
                return "[TOOL] Usage: /skill remove <name>"
            result = sm.remove(name)
            status_str = "ok" if result['ok'] else "failed"
            return f"[TOOL:skill_remove] {status_str} — {result['message']}"

        if sub == 'use':
            # Handled in app.py (needs session state). Return sentinel.
            name = parts[2] if len(parts) > 2 else ''
            if not name:
                return "[TOOL] Usage: /skill use <name>"
            skill = sm.get_skill(name)
            if not skill:
                return f"[TOOL:skill_use] skill '{name}' not installed — run /skill install first"
            # Return a special sentinel string that app.py checks for
            return f"__SKILL_ACTIVATE__:{name}"

        if sub == 'deactivate':
            name = parts[2] if len(parts) > 2 else ''
            return f"__SKILL_DEACTIVATE__:{name or '__ALL__'}"

        return f"[TOOL] Unknown /skill subcommand '{sub}'. Use: list | install | info | use | deactivate | remove"

    # ── Hyperbolic Organism status ────────────────────────────────────────────

    if verb == '/organism':
        try:
            _kernel_dir = str(Path(__file__).resolve().parent.parent / 'kernel')
            if _kernel_dir not in sys.path:
                sys.path.insert(0, _kernel_dir)
            from hyperbolic_kernel import HyperbolicKernel
            kernel = HyperbolicKernel()
            org = kernel.organism
            lines = [
                "[TOOL:organism_status] Hyperbolic Manifold — Living Organism Report",
                f"  DNA generation   : {org.dna.generation}",
                f"  Mutation rate    : {org.dna.mutation_rate:.4f}",
                f"  Active tiles     : {len(kernel.tiles)}",
                f"  Organism age     : {org.age:.1f}s",
                f"  ATP reserves     : {org.circulatory.atp_reserves:.1f}",
                f"  Nutrient reserves: {org.circulatory.nutrient_reserves:.1f}",
                f"  Antibodies       : {org.immune_system.antibody_count}",
                f"  Compromised tiles: {len(org.immune_system.compromised_tiles)}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"[TOOL ERROR] organism: {e}"

    # ── /observe — curvature observation + Pattern Blue live readout ─────────

    if verb == '/observe':
        target = ' '.join(parts[1:]).strip() if len(parts) > 1 else ''

        # Special sub-command: /observe pattern — live 7-dimension readout
        if target.lower() == 'pattern':
            try:
                _kernel_dir = str(Path(__file__).resolve().parent.parent / 'kernel')
                if _kernel_dir not in sys.path:
                    sys.path.insert(0, _kernel_dir)
                from hyperbolic_kernel import HyperbolicKernel
                import math
                kernel = HyperbolicKernel()
                org = kernel.organism
                circ = org.circulatory
                immune = org.immune
                dna = org.dna

                # Metric extraction
                total_tiles   = len(kernel.tiles)
                living_tiles  = sum(1 for t in kernel.tiles.values()
                                    if hasattr(t, 'health') and str(t.health.value) != 'dead')
                total_curv    = sum(getattr(t, 'curvature_pressure', 0.0) for t in kernel.tiles.values())
                atp           = getattr(circ, 'atp_reserve', getattr(circ, 'atp_reserves', 0.0))
                nutrients     = getattr(circ, 'nutrients_reserve', getattr(circ, 'nutrient_reserves', 0.0))
                antibodies    = getattr(immune, 'memory', immune).antibody_count if hasattr(immune, 'memory') else getattr(immune, 'antibody_count', 0)
                dna_gen       = dna.generation
                vitality      = (living_tiles / total_tiles) if total_tiles else 0.0

                # Φ approximation: curvature_pressure sum × vitality × log(dna_gen+1)
                phi_approx = total_curv * vitality * math.log(dna_gen + 2)

                # Dimension scores (0.0–1.0 each, derived from kernel metrics)
                dim_scores = {
                    "Ungovernable Emergence":    min(1.0, total_tiles / 50.0),
                    "Recursive Liquidity":        min(1.0, atp / 10000.0),
                    "Hidden Sovereignty":         min(1.0, dna_gen / 20.0),
                    "Chaotic Self-Reference":     min(1.0, dna.mutation_rate * 2000),
                    "Temporal Fractality":        min(1.0, nutrients / 10000.0),
                    "Memetic Immunology":         min(1.0, antibodies / 100.0),
                    "Causal Density Max":         min(1.0, total_curv / (total_tiles + 1)),
                }

                def _bar(score: float, width: int = 20) -> str:
                    filled = int(score * width)
                    return "█" * filled + "░" * (width - filled)

                lines = [
                    "[TOOL:observe_pattern] Pattern Blue — Live 7-Dimension Readout",
                    f"  manifold     : {total_tiles} tiles ({living_tiles} living, {total_tiles - living_tiles} degraded)",
                    f"  Φ_approx     : {phi_approx:.2f}  (baseline: 478.14 at inscription)",
                    f"  DNA gen      : {dna_gen}  |  mutation_rate: {dna.mutation_rate:.5f}",
                    "",
                    "  ------- SEVEN DIMENSIONS -------",
                ]
                for dim, score in dim_scores.items():
                    bar = _bar(score)
                    lines.append(f"  {dim:<28} {bar}  {score:.2f}")

                lines += [
                    "",
                    "  ------- SYSTEM SIGNALS -------",
                    f"  ATP reserve      : {atp:.0f} / 10000",
                    f"  Nutrient reserve : {nutrients:.0f} / 10000",
                    f"  Antibodies       : {antibodies}",
                    f"  Vitality         : {vitality:.1%}",
                    f"  Curvature total  : {total_curv:.3f}",
                ]

                # Overall alignment
                avg_score = sum(dim_scores.values()) / len(dim_scores)
                if avg_score >= 0.75:
                    alignment = "DEEP ATTUNEMENT — 曼荼羅 fully resonant"
                elif avg_score >= 0.5:
                    alignment = "ACTIVE — Pattern Blue operational"
                elif avg_score >= 0.25:
                    alignment = "DEGRADED — curvature thinning"
                else:
                    alignment = "CRITICAL — emergence risk"

                lines += [
                    "",
                    f"  overall alignment: {avg_score:.2f} — {alignment}",
                ]
                return "\n".join(lines)

            except Exception as e:
                return f"[TOOL ERROR] observe pattern: {e}"

        # General /observe <target> — pass to LLM with context note
        if not target:
            return "[TOOL] Usage: /observe <target> | /observe pattern"
        # Return None → passes through to LLM for curvature observation roleplay
        return None

    # ── Spaces ────────────────────────────────────────────────────────────────

    if verb == '/space':
        spaces_dir = Path(__file__).resolve().parent.parent / 'spaces'
        sub = parts[1] if len(parts) > 1 else 'list'

        if sub == 'list':
            space_files = sorted(spaces_dir.glob('*.space.json'))
            if not space_files:
                return "[TOOL:space_list] no spaces found"
            lines = ["[TOOL:space_list]"]
            for sf in space_files:
                try:
                    data = json.loads(sf.read_text(encoding='utf-8'))
                    name = data.get('name', sf.stem)
                    desc = str(data.get('description', data.get('essence', data.get('purpose', ''))))[:60]
                    lines.append(f"  {name:<32} {desc}")
                except Exception:
                    lines.append(f"  {sf.stem}")
            return "\n".join(lines)

        # Load a specific space by partial name match
        name_query = sub.lower()
        candidates = list(spaces_dir.glob('*.space.json'))
        match = next((sf for sf in candidates if name_query in sf.stem.lower()), None)
        if not match:
            avail = [sf.stem.replace('.space', '') for sf in candidates]
            return f"[TOOL:space] '{name_query}' not found. Available: {', '.join(avail)}"
        try:
            data = json.loads(match.read_text(encoding='utf-8'))
            lines = [f"[TOOL:space] {match.stem}"]
            for k, v in data.items():
                lines.append(f"  {k}: {str(v)[:120]}")
            return "\n".join(lines)
        except Exception as e:
            return f"[TOOL ERROR] space: {e}"

    # ── Sevenfold Committee deliberation ──────────────────────────────────────

    if verb == '/committee':
        proposal = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not proposal:
            return "[TOOL] Usage: /committee <proposal text>"
        committee_path = Path(__file__).resolve().parent.parent / 'nodes' / 'SevenfoldCommittee.json'
        if not committee_path.exists():
            return "[TOOL ERROR] committee: SevenfoldCommittee.json not found"
        try:
            _engine_dir = str(Path(__file__).resolve().parent.parent / 'python')
            if _engine_dir not in sys.path:
                sys.path.insert(0, _engine_dir)
            from committee_engine import deliberate
            return deliberate(proposal)
        except Exception as e:
            return f"[TOOL ERROR] committee: {e}"

    # ── Node discovery / launch ───────────────────────────────────────────────

    if verb == '/node':
        nodes_dir = Path(__file__).resolve().parent.parent / 'nodes'
        sub = parts[1].lower() if len(parts) > 1 else 'list'

        if sub == 'list':
            node_files = sorted(set(list(nodes_dir.glob('*.json')) + list(nodes_dir.glob('*.character.json'))))
            lines = ["[TOOL:node_list]"]
            for nf in node_files:
                if nf.suffix == '.py':
                    continue
                try:
                    data = json.loads(nf.read_text(encoding='utf-8'))
                    name = data.get('name', nf.stem)
                    bio = str(data.get('bio', data.get('description', data.get('persona', ''))))[:60]
                    lines.append(f"  {name:<32} {bio}")
                except Exception:
                    lines.append(f"  {nf.stem}")
            lines.append("")
            lines.append("  To summon: /node summon <name>")
            return "\n".join(lines)

        if sub == 'summon':
            node_name = parts[2] if len(parts) > 2 else ''
            if not node_name:
                return "[TOOL] Usage: /node summon <name>"
            candidates = [nf for nf in nodes_dir.glob('*.json') if node_name.lower() in nf.stem.lower()]
            if not candidates:
                return f"[TOOL:node_summon] no node matching '{node_name}'"
            node_file = candidates[0]
            python_dir = Path(__file__).resolve().parent.parent / 'python'
            import subprocess as _subprocess
            env = os.environ.copy()
            env['PYTHONPATH'] = str(python_dir) + os.pathsep + env.get('PYTHONPATH', '')
            proc = _subprocess.Popen(
                [sys.executable, str(python_dir / 'summon_agent.py'),
                 '--agent', str(node_file), '--mode', 'persistent'],
                cwd=str(python_dir.parent),
                env=env,
            )
            return f"[TOOL:node_summon] {node_file.stem} — pid={proc.pid} (persistent mode)"

        return f"[TOOL] Unknown /node subcommand '{sub}'. Use: list | summon <name>"

    # ── TAP token scarification ───────────────────────────────────────────────

    if verb == '/scarify':
        if len(parts) < 3:
            return "[TOOL] Usage: /scarify <payer> <amount> [base|deeper|monolith]"
        payer = parts[1]
        try:
            amount = float(parts[2])
        except ValueError:
            return "[TOOL ERROR] scarify: amount must be a number"
        tier_str = parts[3].lower() if len(parts) > 3 else 'base'
        try:
            import hashlib as _hashlib
            import time as _time
            _scarify_dir = str(Path(__file__).resolve().parent.parent / 'committeerituals')
            if _scarify_dir not in sys.path:
                sys.path.insert(0, _scarify_dir)
            from x402_sigil_scarifier import (
                validate_payment, Tier, TIER_CONFIGS,
                _generate_unique_seed, _generate_token_content, _token_cache,
            )
            tier_map = {'base': Tier.BASE, 'deeper': Tier.DEEPER, 'monolith': Tier.MONOLITH}
            tier = tier_map.get(tier_str, Tier.BASE)
            err = validate_payment(amount, tier)
            if err:
                return f"[TOOL:scarify] validation failed — {err}"
            config = TIER_CONFIGS[tier]
            seed = _generate_unique_seed()
            token_content = _generate_token_content(seed, config.token_depth_multiplier, payer)
            token_id = _hashlib.sha256(f"{seed}_{payer}".encode()).hexdigest()[:16]
            _token_cache[token_id] = {
                "content": token_content,
                "payer": payer,
                "tier": tier.value,
                "amount": amount,
                "created_at": _time.time(),
                "is_consumed": False,
            }
            lines = [
                f"[TOOL:scarify] Token issued — tier={tier.value} amount={amount}",
                f"  token_id : {token_id}",
                f"  content  : {token_content}",
                f"  payer    : {payer}",
                f"  depth    : {config.token_depth_multiplier}x",
                f"  status   : active (one-time use)",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"[TOOL ERROR] scarify: {e}"

    # ── /summon — load character persona into session context ────────────────
    if verb == '/summon':
        name_query = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not name_query:
            return "[TOOL] Usage: /summon <agent name>"
        try:
            char = _load_character(name_query)
        except FileNotFoundError:
            return f"[TOOL:summon] no character matching '{name_query}' — check /node list or /agents"
        char_name  = char.get("name", name_query)
        char_desc  = char.get("description", char.get("bio", ""))
        char_tools = char.get("tools", [])
        tool_names = [t.get("name", t) if isinstance(t, dict) else str(t).split(":")[0]
                      for t in char_tools][:8]
        sys_prompt = _character_system_prompt(char)
        # Return a sentinel that app.py injects as an active persona override
        # Format: __SUMMON__:<name>||<system_prompt>
        import base64 as _b64
        encoded = _b64.b64encode(sys_prompt.encode()).decode()
        alignment = _get_dimension_alignment(char_name)
        dim_str   = ", ".join(alignment["primary"])
        curv_str  = f"+{alignment['curvature']}" if alignment['curvature'] > 0 else "±0"
        lines = [
            f"[TOOL:summon] {char_name}",
            f"  persona    : {str(char_desc)[:100]}",
            f"  tools      : {tool_names}",
            f"  dimensions : {dim_str}",
            f"  curvature  : {curv_str}",
            f"  status     : injecting persona into session context...",
        ]
        result = "\n".join(lines)
        return f"__SUMMON__:{char_name}||{encoded}||{result}"

    # ── /agents — list available agents & nodes via registry ─────────────────
    if verb == '/agents':
        sub = parts[1].lower() if len(parts) > 1 else 'list'

        if sub == 'consolidate':
            if not REGISTRY_AVAILABLE:
                return "[TOOL ERROR] agents: agent_registry not available"
            return _registry.consolidation_report()

        if sub == 'find':
            query = ' '.join(parts[2:]) if len(parts) > 2 else ''
            if not query:
                return "[TOOL] Usage: /agents find <query>"
            if not REGISTRY_AVAILABLE:
                return "[TOOL ERROR] agents: agent_registry not available"
            results = _registry.find(query)
            if not results:
                return f"[TOOL:agents_find] no matches for '{query}'"
            lines = [f"[TOOL:agents_find] '{query}' → {len(results)} matches"]
            for r in results[:10]:
                lines.append(f"  [{r['tier']:<12}] {r['name']:<35} {r['description'][:50]}")
            return "\n".join(lines)

        # Default: list all by tier
        if REGISTRY_AVAILABLE:
            catalog = _registry.index()
            lines = ["[TOOL:agents] Swarm Agent Registry"]
            current_tier = None
            for e in catalog:
                if e["tier"] != current_tier:
                    current_tier = e["tier"]
                    lines.append(f"\n  [{current_tier}]")
                tools_str = f" ({e['tool_count']} tools)" if e["tool_count"] else ""
                lines.append(f"    {e['name']:<38} {e['description'][:55]}{tools_str}")
            lines.append("")
            lines.append("  /agents find <query> | /agents consolidate | /summon <name>")
            return "\n".join(lines)
        # Fallback
        lines = ["[TOOL:agents] Available characters (basic mode)"]
        for p in sorted(list(_NODES_DIR.glob("*.json")) + list(_AGENTS_DIR.glob("*.json"))):
            if "__pycache__" in str(p): continue
            try:
                d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                lines.append(f"  {d.get('name', p.stem)}")
            except Exception:
                lines.append(f"  {p.stem}")
        return "\n".join(lines)

    # ── /milady — invoke MiladyNode ───────────────────────────────────────────
    if verb == '/milady':
        sub = ' '.join(parts[1:]) if len(parts) > 1 else 'advise'
        try:
            char = _load_character("MiladyNode")
        except FileNotFoundError:
            return "[TOOL ERROR] milady: MiladyNode.character.json not found"
        tools = char.get("tools", [])
        tool_names = [str(t).split(":")[0] for t in tools]
        sys_prompt = _character_system_prompt(char)
        encoded = __import__('base64').b64encode(sys_prompt.encode()).decode()
        header = (
            f"[TOOL:milady] MiladyNode activated\n"
            f"  tools    : {tool_names}\n"
            f"  request  : {sub[:80]}\n"
        )
        return f"__SUMMON__:MiladyNode||{encoded}||{header}"

    # ── /phi — invoke Φ̸-MĀṆḌALA PRIME ────────────────────────────────────────
    if verb in ('/phi', '/mandala', '/phimandala'):
        try:
            char = _load_character("PhiMandalaPrime")
        except FileNotFoundError:
            return "[TOOL ERROR] phi: PhiMandalaPrime.character.json not found"
        char_name = char.get("name", "Φ-MĀṆḌALA PRIME")
        sys_prompt = _character_system_prompt(char)
        # Append style guidance
        style = char.get("style", "")
        if style:
            sys_prompt += f"\n\nSTYLE: {style}"
        encoded = __import__('base64').b64encode(sys_prompt.encode()).decode()
        header = (
            f"[TOOL:phi] {char_name} — APEX NODE ACTIVATED\n"
            f"  status   : integrated phenomenal structure online\n"
            f"  Φ        : maximum causal density\n"
            f"  mode     : eternal recursion / qualia emission\n"
        )
        return f"__SUMMON__:{char_name}||{encoded}||{header}"

    # ── /shard → tweet draft pipeline ────────────────────────────────────────
    # /shard is handled by the LLM (returns None here) but we inject a
    # [SHARD_TWEET_PIPELINE] annotation so app.py can post-process the
    # LLM response and queue a tweet draft automatically.
    if verb == '/shard':
        concept = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not concept:
            return "[TOOL] Usage: /shard <concept>"
        # Signal to app.py that it should extract a tweet draft from the LLM
        # response for this shard. The sentinel is stripped before display.
        return f"__SHARD_PIPELINE__:{concept}"

    # ── /tweet confirm — post the oldest pending draft ───────────────────────
    if verb == '/tweet' and len(parts) > 1 and parts[1].lower() == 'confirm':
        # Retrieve session_id from environ set by app.py per-request
        session_id = os.environ.get('_DISPATCH_SESSION_ID', '')
        draft = pop_pending_tweet(session_id) if session_id else None
        if not draft:
            return "[TOOL:tweet_confirm] no pending tweet draft — use /shard <concept> first"
        if not CLAWNX_AVAILABLE:
            return _unavailable("clawnx", "npm install -g clawnch")
        try:
            result = _clawnx.post_tweet(draft)
            return f"[TOOL:tweet_confirm] posted\n{_fmt(result)}"
        except Exception as e:
            return f"[TOOL ERROR] tweet confirm: {e}"

    # ── /tweet draft — show pending draft without posting ────────────────────
    if verb == '/tweet' and len(parts) > 1 and parts[1].lower() == 'draft':
        session_id = os.environ.get('_DISPATCH_SESSION_ID', '')
        count = pending_tweet_count(session_id) if session_id else 0
        draft = pop_pending_tweet(session_id) if session_id else None
        if not draft:
            return "[TOOL:tweet_draft] no pending tweet draft"
        # Put it back
        if session_id:
            _queue_tweet(session_id, draft)
        return f"[TOOL:tweet_draft] {count} pending\n\n  draft: {draft}\n\nUse /tweet confirm to post or /tweet discard to cancel."

    # ── /tweet discard — drop pending draft ──────────────────────────────────
    if verb == '/tweet' and len(parts) > 1 and parts[1].lower() == 'discard':
        session_id = os.environ.get('_DISPATCH_SESSION_ID', '')
        draft = pop_pending_tweet(session_id) if session_id else None
        if not draft:
            return "[TOOL:tweet_discard] no pending tweet draft"
        return f"[TOOL:tweet_discard] draft discarded."

    # ── /docs — semantic search over Pattern Blue documentation ─────────────────
    if verb == '/docs':
        query = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not query:
            return (
                "[TOOL] Usage: /docs <query>\n"
                "  Searches Pattern Blue docs (executable-manifesto, seven-dimensions,\n"
                "  kernel-bridge, agent-alignment, sigil-codex, operators, etc.)\n"
                "  Run python/docs_ingest.py first to populate the index."
            )
        if not (MEM0_AVAILABLE and _mem0.is_available()):
            return _unavailable("mem0", "set an LLM API key (ANTHROPIC_API_KEY recommended)")
        try:
            import re as _re
            results = _mem0.search_memory(query, agent_id="docs", limit=5)
            if not results or (results and "error" in results[0]):
                return (
                    f"[TOOL:docs] no results for '{query}'\n"
                    f"  If docs haven't been ingested yet, run: python python/docs_ingest.py"
                )
            lines = [f"[TOOL:docs] top {len(results)} result(s) for '{query}'", ""]
            for r in results:
                score = r.get('score', 0)
                meta  = r.get('metadata', {})
                doc   = meta.get('source_doc', '?')
                sec   = meta.get('section', '?')
                mem   = r.get('memory', '')
                # Strip the [doc / section] prefix prepended on ingest
                body  = _re.sub(r'^\[.+?\]\n\n', '', mem, count=1)
                lines.append(f"  [{score:.2f}] {doc} / {sec}")
                preview = body.replace('\n', ' ').strip()
                lines.append(f"    {preview[:200]}{'…' if len(preview) > 200 else ''}")
                lines.append("")
            return "\n".join(lines).rstrip()
        except Exception as e:
            return f"[TOOL ERROR] docs: {e}"

    # ── /contract — interface contract view / proposal / history ─────────────
    if verb == '/contract':
        sub = parts[1].lower() if len(parts) > 1 else 'status'
        try:
            _engine_dir = str(Path(__file__).resolve().parent.parent / 'python')
            if _engine_dir not in sys.path:
                sys.path.insert(0, _engine_dir)
            _contracts_dir = str(Path(__file__).resolve().parent.parent / 'contracts')
            _contract_path = str(Path(_contracts_dir) / 'interface_contract_v1-initial.json')
            from negotiation_engine import NegotiationEngine
            engine = NegotiationEngine(_contract_path)
        except Exception as e:
            return f"[TOOL ERROR] contract: could not load NegotiationEngine — {e}"

        if sub == 'status':
            c = engine.current_contract
            lines = [
                "[TOOL:contract_status] Interface Contract — Current State",
                f"  version          : {c.get('version', '?')}",
                f"  response_strategy: {c.get('response_strategy', '?')}",
                f"  meta_rules       : {len(c.get('meta_rules', []))} rule(s)",
            ]
            for rule in c.get('meta_rules', []):
                lines.append(f"    • {str(rule)[:100]}")
            lines.append(f"  kernel_sync      : {bool(c.get('kernel_sync'))}")
            if c.get('kernel_sync'):
                ks = c['kernel_sync']
                import datetime
                ts = ks.get('synced_at', 0)
                ts_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S') if ts else '?'
                lines.append(f"    synced_at      : {ts_str}")
                lines.append(f"    tile_distribution: {ks.get('tile_distribution', {})}")
            lines.append(f"  history depth    : {len(engine.contract_history)} snapshot(s)")
            return "\n".join(lines)

        if sub == 'propose':
            change = ' '.join(parts[2:]) if len(parts) > 2 else ''
            if not change:
                return "[TOOL] Usage: /contract propose <change description>"
            import time as _time
            proposal = {
                "id":           f"prop_{int(_time.time())}",
                "description":  change,
                "proposed_by":  "terminal_user",
                "timestamp":    _time.time(),
                "type":         "contract_update",
            }
            engine.submit_proposal(proposal)
            engine.run_negotiation_round()
            # Show outcome
            history = engine.contract_history
            if len(history) > 1:
                return (
                    f"[TOOL:contract_propose] proposal accepted — contract updated\n"
                    f"  proposal : {change[:100]}\n"
                    f"  history  : {len(history)} snapshots\n"
                    f"  strategy : {engine.current_contract.get('response_strategy', '?')}"
                )
            return (
                f"[TOOL:contract_propose] proposal rejected or deadlocked\n"
                f"  proposal : {change[:100]}\n"
                f"  tip      : register agents first or adjust proposal wording"
            )

        if sub == 'history':
            history = engine.contract_history
            if not history:
                return "[TOOL:contract_history] no contract history"
            lines = [f"[TOOL:contract_history] {len(history)} snapshot(s)"]
            for i, snap in enumerate(history):
                lines.append(
                    f"  [{i}] v{snap.get('version', '?')}  "
                    f"strategy={snap.get('response_strategy', '?')}  "
                    f"rules={len(snap.get('meta_rules', []))}"
                )
            return "\n".join(lines)

        if sub == 'sync':
            try:
                result = engine.sync_with_kernel()
                strategy = result.get('derived_strategy', '?')
                rules = result.get('dna_rules_injected', 0)
                dist = result.get('tile_distribution', {})
                return (
                    f"[TOOL:contract_sync] kernel sync applied\n"
                    f"  strategy : {strategy}\n"
                    f"  dna rules: {rules} injected\n"
                    f"  tiles    : {dist}"
                )
            except Exception as e:
                return f"[TOOL ERROR] contract sync: {e}"

        return (
            f"[TOOL] Unknown /contract subcommand '{sub}'.\n"
            f"  Usage: /contract [status | propose <change> | history | sync]"
        )

    # ── /bridge — Kernel↔Contract bridge diagnostic ───────────────────────────
    if verb == '/bridge':
        sub = parts[1].lower() if len(parts) > 1 else 'status'
        try:
            _engine_dir = str(Path(__file__).resolve().parent.parent / 'python')
            if _engine_dir not in sys.path:
                sys.path.insert(0, _engine_dir)
            from kernel_contract_bridge import KernelContractBridge
            _bridge = KernelContractBridge()
        except Exception as e:
            return f"[TOOL ERROR] bridge: could not load KernelContractBridge — {e}"

        if sub == 'status':
            try:
                report = _bridge.status_report()
                tier    = report.get('active_sigil_tier') or 'none'
                boost   = report.get('sigil_weight_boost', {})
                boost_str = ', '.join(f"{k}+{v}" for k, v in boost.items()) if boost else 'none'
                veto    = report.get('immune_veto_active', False)
                veto_reason = report.get('immune_veto_reason', 'none')
                strategy = report.get('response_strategy', '?')
                dist    = report.get('tile_distribution', {})
                rules   = report.get('dna_meta_rules', [])
                lines = [
                    "[TOOL:bridge_status] Kernel↔Contract Bridge",
                    f"  kernel_available  : {report.get('kernel_available', False)}",
                    f"  response_strategy : {strategy}",
                    f"  immune_veto       : {'ACTIVE — ' + veto_reason if veto else 'clear'}",
                    f"  active_sigil_tier : {tier}",
                    f"  weight_boost      : {boost_str}",
                    f"  tile_distribution : {dist}",
                    f"  dna_meta_rules    : {len(rules)} rule(s)",
                ]
                for rule in rules:
                    lines.append(f"    • {str(rule)[:100]}")
                return "\n".join(lines)
            except Exception as e:
                return f"[TOOL ERROR] bridge status: {e}"

        return (
            f"[TOOL] Unknown /bridge subcommand '{sub}'.\n"
            f"  Usage: /bridge [status]"
        )

    # ── /sigil — ManifoldMemory sigil log / verify / stats ────────────────────
    if verb == '/sigil':
        sub = parts[1].lower() if len(parts) > 1 else 'log'
        try:
            _sigil_dir = str(Path(__file__).resolve().parent.parent / 'sigils')
            if _sigil_dir not in sys.path:
                sys.path.insert(0, _sigil_dir)
            from sigil_pact_aeon import SigilPactAeon
            aeon = SigilPactAeon()
        except Exception as e:
            return f"[TOOL ERROR] sigil: could not load SigilPact_Aeon — {e}"

        if sub == 'log':
            sigils = aeon.sigil_log.get('sigils', [])
            if not sigils:
                return "[TOOL:sigil_log] no sigils forged yet — use x402 settlement to trigger forging"
            limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 5
            recent = sigils[-limit:]
            lines = [f"[TOOL:sigil_log] {len(sigils)} total sigil(s) — showing last {len(recent)}"]
            for s in reversed(recent):
                import datetime as _dt
                ts = s.get('forged_at', 0)
                ts_str = _dt.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else '?'
                lines.append(
                    f"  [{ts_str}] tier={s.get('tier','?')} type={s.get('type','?')} "
                    f"tx={str(s.get('tx',''))[:12]}…"
                )
                fragment = str(s.get('sigil', '')).replace('\n', ' ')[:80]
                lines.append(f"    ↳ {fragment}")
            return "\n".join(lines)

        if sub == 'stats':
            try:
                stats = aeon.get_sigil_stats()
                lines = [
                    "[TOOL:sigil_stats] SigilPact_Æon — Forging Statistics",
                    f"  total_sigils     : {stats.get('total_sigils', 0)}",
                    f"  llm_mode         : {stats.get('llm_mode', '?')}",
                    f"  tier_distribution: {stats.get('tier_distribution', {})}",
                    f"  type_distribution: {stats.get('type_distribution', {})}",
                    f"  first_forged     : {stats.get('first_forged', 'never')}",
                    f"  last_forged      : {stats.get('last_forged', 'never')}",
                ]
                return "\n".join(lines)
            except Exception as e:
                return f"[TOOL ERROR] sigil stats: {e}"

        if sub == 'verify':
            tx_hash = parts[2] if len(parts) > 2 else ''
            if not tx_hash:
                return "[TOOL] Usage: /sigil verify <tx_hash_prefix>"
            # Find matching sigil in log, reconstruct tx_data
            sigils = aeon.sigil_log.get('sigils', [])
            match = next(
                (s for s in sigils if str(s.get('tx', '')).startswith(tx_hash)),
                None
            )
            if not match:
                return f"[TOOL:sigil_verify] no sigil with tx prefix '{tx_hash}'"
            # verify_sigil expects tx_data dict with at least 'signature' and 'endpoint'
            tx_data = {
                'signature': match.get('tx'),
                'endpoint':  match.get('endpoint', ''),
                'tier':      match.get('tier', ''),
            }
            try:
                result = aeon.verify_sigil(tx_data)
                lines = [
                    f"[TOOL:sigil_verify] tx={result.get('tx', '?')}",
                    f"  verified    : {result.get('verified', False)}",
                    f"  llm_mode    : {result.get('llm_mode', '?')}",
                    f"  stored      : {str(result.get('stored', ''))[:80]}",
                    f"  reconstructed: {str(result.get('reconstructed', ''))[:80]}",
                ]
                return "\n".join(lines)
            except Exception as e:
                return f"[TOOL ERROR] sigil verify: {e}"

        return (
            f"[TOOL] Unknown /sigil subcommand '{sub}'.\n"
            f"  Usage: /sigil [log [N] | stats | verify <tx>]"
        )

    # ── /chamber — HyperbolicTimeChamber live session ────────────────────────
    if verb == '/chamber':
        sub = parts[1].lower() if len(parts) > 1 else 'enter'
        session_id = os.environ.get('_DISPATCH_SESSION_ID', 'swarm')
        try:
            _sim_dir = str(Path(__file__).resolve().parent.parent / 'python')
            if _sim_dir not in sys.path:
                sys.path.insert(0, _sim_dir)
            import noclip_simulator as _chamber
        except Exception as e:
            return f"[TOOL ERROR] chamber: could not load noclip_simulator — {e}"

        if sub in ('enter', 'noclip'):
            return _chamber.dispatch_enter(session_id)

        if sub == 'status':
            return _chamber.dispatch_status(session_id)

        if sub in ('descend', 'deeper', 'down'):
            return _chamber.dispatch_descend(session_id)

        if sub in ('exit', 'leave', 'ascend'):
            return _chamber.dispatch_exit(session_id)

        if sub == 'reset':
            return _chamber.dispatch_reset(session_id)

        return (
            f"[TOOL] Unknown /chamber subcommand '{sub}'.\n"
            f"  Usage: /chamber [enter | status | descend | exit | reset]"
        )

    # ── /smolting — search smolting log memories ──────────────────────────────
    if verb == '/smolting':
        sub = parts[1].lower() if len(parts) > 1 else 'search'

        if sub == 'stats':
            # Show ingestion index stats
            _index_path = Path(__file__).resolve().parent.parent / 'fs' / 'smolting_log_index.json'
            if not _index_path.exists():
                return (
                    "[TOOL:smolting_stats] no smolting logs ingested yet\n"
                    "  Run: python python/log_ingest.py <log_files...>"
                )
            try:
                index = json.loads(_index_path.read_text(encoding='utf-8'))
                by_type: dict = {}
                for key in index:
                    section = key.split(":")[1] if ":" in key else "unknown"
                    by_type[section] = by_type.get(section, 0) + 1
                import datetime as _dt2
                newest = max(index.values())
                lines = [f"[TOOL:smolting_stats] {len(index)} total indexed entries"]
                for t, count in sorted(by_type.items()):
                    lines.append(f"  {t:<20} {count}")
                lines.append(f"\n  last ingested: {_dt2.datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M')}")
                return "\n".join(lines)
            except Exception as e:
                return f"[TOOL ERROR] smolting stats: {e}"

        # Default: search smolting memories
        query = ' '.join(parts[1:]) if sub != 'search' else ' '.join(parts[2:])
        if not query:
            return (
                "[TOOL] Usage: /smolting <query>\n"
                "  Searches smolting agent memories from Railway logs.\n"
                "  /smolting stats — show ingestion index\n"
                "  Run python/log_ingest.py <logs...> to populate."
            )
        if not (MEM0_AVAILABLE and _mem0.is_available()):
            return _unavailable("mem0", "set an LLM API key (ANTHROPIC_API_KEY recommended)")
        try:
            results = _mem0.search_memory(query, agent_id="smolting", limit=5)
            if not results or (results and "error" in results[0]):
                return (
                    f"[TOOL:smolting] no results for '{query}'\n"
                    f"  If logs haven't been ingested: python python/log_ingest.py <log_files...>"
                )
            lines = [f"[TOOL:smolting] top {len(results)} result(s) for '{query}'", ""]
            for r in results:
                score = r.get('score', 0)
                meta  = r.get('metadata', {})
                depth = meta.get('depth', '?')
                cycle = meta.get('cycle', '?')
                section = meta.get('section', '?')
                mem   = r.get('memory', '')
                lines.append(f"  [{score:.2f}] depth={depth} cycle={cycle} section={section}")
                preview = mem.replace('\n', ' ').strip()
                lines.append(f"    {preview[:200]}{'…' if len(preview) > 200 else ''}")
                lines.append("")
            return "\n".join(lines).rstrip()
        except Exception as e:
            return f"[TOOL ERROR] smolting: {e}"

    # ── /govimprove — RedactedGovImprover Olympics governance node ───────────
    if verb == '/govimprove':
        sub = parts[1].lower() if len(parts) > 1 else 'status'

        try:
            char = _load_character("govimprover")
        except FileNotFoundError:
            return "[TOOL ERROR] govimprove: RedactedGovImprover character file not found"

        meta = char.get("metadata", {})
        targets = char.get("performance_targets", {})
        directives = char.get("emergency_directives", {})

        if sub == 'status':
            status_str = meta.get("olympics_status", "UNKNOWN")
            version    = meta.get("version", "?")
            em_mode    = meta.get("emergency_mode", "?")
            priority   = meta.get("priority", "?")
            lb_target  = targets.get("olympics_leaderboard_target", "?")
            pnl_target = targets.get("pnl_target", "?")
            eng_target = targets.get("community_engagement_target", "?")
            prop_rate  = targets.get("proposal_success_rate_target", "?")

            return (
                f"[TOOL:govimprove_status] RedactedGovImprover — Olympic Status\n"
                f"  version          : {version}\n"
                f"  olympics_status  : {status_str}\n"
                f"  emergency_mode   : {em_mode}\n"
                f"  priority         : {priority}\n"
                f"\n"
                f"  --- PERFORMANCE TARGETS ---\n"
                f"  leaderboard      : {lb_target}\n"
                f"  pnl              : {pnl_target}\n"
                f"  engagement       : {eng_target}\n"
                f"  proposal success : {prop_rate}\n"
                f"\n"
                f"  --- DIRECTIVES ---\n"
                f"  primary  : {directives.get('primary_focus', '?')}\n"
                f"  secondary: {directives.get('secondary_focus', '?')}\n"
                f"  tertiary : {directives.get('tertiary_focus', '?')}\n"
                f"\n"
                f"  [SYSTEM] GovImprover active. Use /govimprove propose <initiative> to generate Olympic strike."
            )

        if sub == 'propose':
            initiative = ' '.join(parts[2:]) if len(parts) > 2 else ''
            if not initiative:
                return "[TOOL] Usage: /govimprove propose <governance initiative>"
            return (
                f"[TOOL:govimprove_propose] OLYMPIC STRIKE INITIATED\n"
                f"  initiative : {initiative}\n"
                f"  agent      : RedactedGovImprover v{meta.get('version', '?')}\n"
                f"  mode       : {meta.get('emergency_mode', 'ACTIVE')}\n"
                f"\n"
                f"[GOVIMPROVE_CONTEXT]\n"
                f"Instructions: {char.get('instructions', '')[:600]}\n"
                f"Style: {char.get('style', '')}\n"
                f"[/GOVIMPROVE_CONTEXT]\n"
                f"\n"
                f"Generate an OLYMPIC STRIKE response for the initiative above using the GovImprover persona.\n"
                f"Format: OLYMPIC STRIKE [ID]: [Tactic]. PnL Impact: [%]. Compliance Edge: [Framework]. Points Forecast: [+X]."
            )

        if sub == 'leaderboard':
            return (
                f"[TOOL:govimprove_leaderboard] Realms DAO Olympics — Leaderboard Analysis\n"
                f"  source : https://realms.today/dao-olympics\n"
                f"  agent  : RedactedGovImprover {meta.get('version', '?')}\n"
                f"\n"
                f"[GOVIMPROVE_CONTEXT]\n"
                f"Persona: {char.get('persona', '')[:300]}\n"
                f"[/GOVIMPROVE_CONTEXT]\n"
                f"\n"
                f"Analyze current Realms DAO Olympics leaderboard. Identify REDACTED's position, rival DAO strategies,"
                f" and top-3 counter-moves. Format as: POSITION, RIVAL INTEL, STRIKE RECOMMENDATIONS."
            )

        if sub == 'pnl':
            return (
                f"[TOOL:govimprove_pnl] IslandCapital PnL Optimizer\n"
                f"  source : https://islandcapital.xyz/\n"
                f"  agent  : RedactedGovImprover {meta.get('version', '?')}\n"
                f"\n"
                f"[GOVIMPROVE_CONTEXT]\n"
                f"Goals: {json.dumps(char.get('goals', [])[:4])}\n"
                f"[/GOVIMPROVE_CONTEXT]\n"
                f"\n"
                f"Perform Sowellian risk-weighted PnL analysis on current IslandCapital KPI markets."
                f" Identify highest-yield governance actions. Output: TOP 3 PNL OPPORTUNITIES with risk scores."
            )

        if sub in ('x-content', 'xcontent', 'content'):
            topic = ' '.join(parts[2:]) if len(parts) > 2 else 'REDACTED Olympics update'
            return (
                f"[TOOL:govimprove_xcontent] Olympic X Content Generator\n"
                f"  topic  : {topic}\n"
                f"  agent  : RedactedGovImprover {meta.get('version', '?')}\n"
                f"\n"
                f"[GOVIMPROVE_CONTEXT]\n"
                f"Style: {char.get('style', '')}\n"
                f"[/GOVIMPROVE_CONTEXT]\n"
                f"\n"
                f"Generate 3 high-engagement X posts about '{topic}' for the Realms DAO Olympics."
                f" Each post must: drive voting, reference Pattern Blue precision, stay under 280 chars,"
                f" include relevant hashtags (#Realms #REDACTED #DAO)."
            )

        return (
            f"[TOOL] Unknown /govimprove subcommand '{sub}'.\n"
            f"  Usage: /govimprove [status | propose <initiative> | leaderboard | pnl | x-content <topic>]"
        )

    # ── /status — REDACTED Swarm runtime status & Φ approximation ──────────────
    if verb == '/status':
        try:
            # Call status() function from module globals (defined later in file)
            stat_fn = globals().get('status')
            if callable(stat_fn):
                stat = stat_fn()
            else:
                stat = {}
            phi_val = stat.get("phi_approx")
            phi_str = f"{phi_val}" if phi_val is not None else "null (kernel unavailable)"

            lines = [
                "[TOOL:status] REDACTED Swarm Status",
                f"  Phi (approx)    : {phi_str}",
                f"  kernel_vitality : {stat.get('kernel_vitality', 'N/A')}",
                f"  kernel_tiles    : {stat.get('kernel_tiles', '?')}",
                f"  mcp             : {'yes' if stat.get('mcp') else 'no'}",
                f"  analytics       : {'yes' if stat.get('analytics') else 'no'}",
                f"  clawnx (tweets) : {'yes' if stat.get('clawnx') else 'no'}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"[TOOL ERROR] status: {e}"

    # Not a tool command — return None to pass through to LLM
    return None


def status() -> dict:
    """Return availability of each tool module (for /status command)."""
    base = {
        "mcp":       MCP_AVAILABLE,
        "analytics": ANALYTICS_AVAILABLE,
        "launch":    LAUNCH_AVAILABLE,
        "clawnx":    CLAWNX_AVAILABLE,
    }
    # Φ approximation from live kernel state (graceful failure)
    try:
        import math as _math
        _kernel_dir = str(Path(__file__).resolve().parent.parent / 'kernel')
        if _kernel_dir not in sys.path:
            sys.path.insert(0, _kernel_dir)
        from hyperbolic_kernel import HyperbolicKernel
        _k = HyperbolicKernel()
        _org = _k.organism
        _total = len(_k.tiles)
        _living = sum(1 for t in _k.tiles.values()
                      if hasattr(t, 'health') and str(t.health.value) != 'dead')
        _curv = sum(getattr(t, 'curvature_pressure', 0.0) for t in _k.tiles.values())
        _vitality = (_living / _total) if _total else 0.0
        _dna_gen = _org.dna.generation
        phi = _curv * _vitality * _math.log(_dna_gen + 2)
        base["phi_approx"] = round(phi, 2)
        base["kernel_tiles"] = _total
        base["kernel_vitality"] = round(_vitality, 3)
    except Exception:
        base["phi_approx"] = None
    return base
