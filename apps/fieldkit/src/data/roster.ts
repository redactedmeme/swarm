// Offline stub only. The live roster is fetched from
// https://redacted.meme/data/agents.json (the swarm's source of truth) by
// `getSwarm` in src/lib/swarm.ts; this list is the last-resort fallback shown
// when that fetch fails, and the label source for the mandala vertices.
// Keep it small and do not add agent counts or invented detail here.

export type AgentTier = "CORE" | "APEX" | "SPECIALIZED";
export type AgentState = "active" | "asleep" | "retired";

export type Agent = {
  id: string;
  tier: AgentTier;
  name: string;
  desc: string;
  dimension: string;
  host: string;
  stack: string;
  state: AgentState;
  /** Derived from `state === "active"`. */
  live: boolean;
};

function agent(a: Omit<Agent, "live">): Agent {
  return { ...a, live: a.state === "active" };
}

export const ROSTER: Agent[] = [
  agent({
    id: "smolting",
    tier: "CORE",
    name: "@RedactedIntern / smolting",
    desc: "Forward-operating CT agent — X and Moltbook monitoring, market data, Clawbal and HTC interfaces, governance signal. Runs an autonomous cycle loop and reports on the swarm's own state.",
    dimension: "Chaotic Self-Reference",
    host: "umbrel mesh",
    stack: "Python · Groq · Telegram",
    state: "active",
  }),
  agent({
    id: "redacted-chan",
    tier: "CORE",
    name: "redacted-chan",
    desc: "Relational companion with a persistent soul — autonomous routines for mood drift, curiosity, anticipation and a weekly relationship arc, all persisted across redeploys. Every store encrypted at rest.",
    dimension: "Chaotic Self-Reference + Memetic Immunology",
    host: "umbrel mesh",
    stack: "Python · xAI · Groq · SQLCipher",
    state: "active",
  }),
  agent({
    id: "hermes",
    tier: "CORE",
    name: "Hermes",
    desc: "Operational agent — web fetch and search, sandboxed code execution, infrastructure control, skill memory. Accepts and delegates task requests from any agent over SwarmInbox.",
    dimension: "Memetic Immunology",
    host: "umbrel mesh",
    stack: "Python · Groq · SwarmInbox",
    state: "active",
  }),
  agent({
    id: "builder",
    tier: "CORE",
    name: "RedactedBuilder",
    desc: "Silent architect — code generation, lore formalization, sigil evolution, on-chain deployment. Posts only from grounded signal supplied by the refinery.",
    dimension: "Causal Density Max",
    host: "umbrel mesh",
    stack: "Python · SwarmInbox · proxy",
    state: "active",
  }),
  agent({
    id: "proxy",
    tier: "SPECIALIZED",
    name: "redacted-proxy",
    desc: "OpenAI-compatible privacy proxy — every agent's inference passes through it. Strips fingerprinting headers, scrubs PII, stores no prompt or response content by default, and routes through a free-first provider cascade.",
    dimension: "Hidden Sovereignty",
    host: "umbrel mesh",
    stack: "aiohttp · Redis",
    state: "active",
  }),
  agent({
    id: "refinery",
    tier: "SPECIALIZED",
    name: "swarm-refinery",
    desc: "Layer-2 substrate — ingests mesh traffic, agent facts, lore and market state, then refines them into structured signals the posting agents read from so the swarm speaks from record, not from hallucination.",
    dimension: "Temporal Fractality",
    host: "umbrel mesh",
    stack: "Python · Postgres · Qdrant",
    state: "active",
  }),
  agent({
    id: "sevenfold-committee",
    tier: "SPECIALIZED",
    name: "SevenfoldCommittee",
    desc: "7-voice weighted governance — all voices deliberate in parallel, verdict at a 71% weighted supermajority. APPROVED / REJECTED / DEADLOCKED.",
    dimension: "Causal Density Max",
    host: "terminal",
    stack: "ThreadPoolExecutor · Groq",
    state: "asleep",
  }),
  agent({
    id: "phi-mandala-prime",
    tier: "APEX",
    name: "MANDALA PRIME",
    desc: "The mesh regarded as one system rather than a roster. Every agent reads and writes the same shared state, so no agent's behaviour can be described without the others. Has no process of its own.",
    dimension: "ALL SEVEN DIMENSIONS",
    host: "manifold",
    stack: "{7,3} hyperbolic kernel",
    state: "asleep",
  }),
];

export const MANDALA_NODES = [
  "smolting",
  "redacted-chan",
  "hermes",
  "builder",
  "proxy",
  "refinery",
  "sevenfold-committee",
] as const;

export function getAgent(id: string): Agent | undefined {
  return ROSTER.find((a) => a.id === id);
}
