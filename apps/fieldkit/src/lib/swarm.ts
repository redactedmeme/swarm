import { createServerFn } from "@tanstack/react-start";
import { ROSTER, type Agent, type AgentState } from "@/data/roster";
import { CA, PAIR } from "@/lib/constants";

/**
 * One agent row from the mesh feed. `redacted.meme` currently serves the
 * simple `/status` shape (`label`, `last_seen`) at `/api/swarm`; the richer
 * `apps/status` payload uses `name` / `last_seen_bucket`. Accept both.
 */
export type MeshAgent = {
  id: string;
  name?: string;
  label?: string;
  online?: boolean;
  last_seen_bucket?: string;
  last_seen?: string;
};

function meshLastSeen(m: MeshAgent): string | null {
  return m.last_seen_bucket ?? m.last_seen ?? null;
}

/** Roster row as `https://redacted.meme/data/agents.json` serves it. */
type RosterRow = {
  id: string;
  tier?: Agent["tier"];
  name?: string;
  desc?: string;
  dimension?: string;
  host?: string;
  stack?: string;
  state?: string;
};

export type MergedAgent = Agent & {
  meshOnline: boolean | null;
  lastSeenBucket: string | null;
  meshKnown: boolean;
};

export type SwarmSnapshot = {
  fetchedAt: string;
  meshOk: boolean;
  rosterOk: boolean;
  summary: string;
  onlineCount: number;
  registeredLive: number;
  agents: MergedAgent[];
};

export type TokenSnapshot = {
  fetchedAt: string;
  ok: boolean;
  priceUsd: number | null;
  priceNative: number | null;
  marketCap: number | null;
  fdv: number | null;
  liquidityUsd: number | null;
  volume: { m5: number; h1: number; h6: number; h24: number };
  priceChange: { m5: number | null; h1: number | null; h6: number | null; h24: number | null };
  txns: {
    h24: { buys: number; sells: number };
    h6: { buys: number; sells: number };
  };
  pairUrl: string | null;
  dexId: string | null;
};

async function fetchJson<T>(url: string, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

const VALID_STATES: readonly AgentState[] = ["active", "asleep", "retired"];

function normState(s: string | undefined): AgentState {
  return VALID_STATES.includes(s as AgentState) ? (s as AgentState) : "asleep";
}

/** Fetched roster row -> local Agent, deriving `live` from declared `state`. */
function toAgent(row: RosterRow, fallback: Agent | undefined): Agent {
  const state = normState(row.state);
  return {
    id: row.id,
    tier: row.tier ?? fallback?.tier ?? "SPECIALIZED",
    name: row.name ?? fallback?.name ?? row.id,
    desc: row.desc ?? fallback?.desc ?? "",
    dimension: row.dimension ?? fallback?.dimension ?? "—",
    host: row.host ?? fallback?.host ?? "—",
    stack: row.stack ?? fallback?.stack ?? "—",
    state,
    live: state === "active",
  };
}

function mergeRoster(roster: Agent[], mesh: MeshAgent[]): MergedAgent[] {
  const byId = new Map(mesh.map((m) => [m.id, m]));
  return roster.map((a) => {
    const hit = byId.get(a.id);
    return {
      ...a,
      meshKnown: Boolean(hit),
      meshOnline: hit ? Boolean(hit.online) : null,
      lastSeenBucket: hit ? meshLastSeen(hit) : null,
    };
  });
}

export const getSwarm = createServerFn({ method: "GET" }).handler(
  async (): Promise<SwarmSnapshot> => {
    let roster = ROSTER;
    let rosterOk = false;
    let mesh: MeshAgent[] = [];
    let meshOk = false;

    let summary = "";

    const [rosterRes, meshRes] = await Promise.allSettled([
      fetchJson<{ agents?: RosterRow[]; summary?: string }>(
        "https://redacted.meme/data/agents.json",
      ),
      fetchJson<{ agents?: MeshAgent[] }>("https://redacted.meme/api/swarm"),
    ]);

    if (rosterRes.status === "fulfilled" && Array.isArray(rosterRes.value.agents)) {
      const fallbackById = new Map(ROSTER.map((a) => [a.id, a]));
      roster = rosterRes.value.agents.map((row) =>
        toAgent(row, fallbackById.get(row.id)),
      );
      if (typeof rosterRes.value.summary === "string") {
        summary = rosterRes.value.summary.trim();
      }
      rosterOk = roster.length > 0;
    }

    if (meshRes.status === "fulfilled" && Array.isArray(meshRes.value.agents)) {
      mesh = meshRes.value.agents;
      meshOk = mesh.length > 0;
    }

    const agents = mergeRoster(roster, mesh);
    const onlineCount = meshOk
      ? agents.filter((a) => a.meshOnline).length
      : agents.filter((a) => a.live).length;

    return {
      fetchedAt: new Date().toISOString(),
      meshOk,
      rosterOk,
      summary:
        summary ||
        "Companion roster for the REDACTED autonomous swarm on Solana.",
      onlineCount,
      registeredLive: agents.filter((a) => a.live).length,
      agents,
    };
  },
);

type DexPair = {
  chainId?: string;
  dexId?: string;
  url?: string;
  pairAddress?: string;
  priceUsd?: string;
  priceNative?: string;
  fdv?: number;
  marketCap?: number;
  liquidity?: { usd?: number };
  volume?: { m5?: number; h1?: number; h6?: number; h24?: number };
  priceChange?: { m5?: number; h1?: number; h6?: number; h24?: number };
  txns?: {
    h6?: { buys?: number; sells?: number };
    h24?: { buys?: number; sells?: number };
  };
};

function emptyToken(ok: boolean): TokenSnapshot {
  return {
    fetchedAt: new Date().toISOString(),
    ok,
    priceUsd: null,
    priceNative: null,
    marketCap: null,
    fdv: null,
    liquidityUsd: null,
    volume: { m5: 0, h1: 0, h6: 0, h24: 0 },
    priceChange: { m5: null, h1: null, h6: null, h24: null },
    txns: { h24: { buys: 0, sells: 0 }, h6: { buys: 0, sells: 0 } },
    pairUrl: null,
    dexId: null,
  };
}

function pickPair(pairs: DexPair[]): DexPair | null {
  const sol = pairs.filter((p) => p.chainId === "solana");
  const pool = sol.length ? sol : pairs;
  if (!pool.length) return null;
  const exact = pool.find((p) => p.pairAddress === PAIR);
  if (exact) return exact;
  return [...pool].sort(
    (a, b) => (b.liquidity?.usd ?? 0) - (a.liquidity?.usd ?? 0),
  )[0] ?? null;
}

function toNum(v: string | number | null | undefined): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export const getToken = createServerFn({ method: "GET" }).handler(
  async (): Promise<TokenSnapshot> => {
    try {
      const data = await fetchJson<{ pairs?: DexPair[] }>(
        `https://api.dexscreener.com/latest/dex/tokens/${CA}`,
      );
      const pair = pickPair(data.pairs ?? []);
      if (!pair) return emptyToken(false);
      return {
        fetchedAt: new Date().toISOString(),
        ok: true,
        priceUsd: toNum(pair.priceUsd),
        priceNative: toNum(pair.priceNative),
        marketCap: toNum(pair.marketCap),
        fdv: toNum(pair.fdv),
        liquidityUsd: toNum(pair.liquidity?.usd),
        volume: {
          m5: pair.volume?.m5 ?? 0,
          h1: pair.volume?.h1 ?? 0,
          h6: pair.volume?.h6 ?? 0,
          h24: pair.volume?.h24 ?? 0,
        },
        priceChange: {
          m5: pair.priceChange?.m5 ?? null,
          h1: pair.priceChange?.h1 ?? null,
          h6: pair.priceChange?.h6 ?? null,
          h24: pair.priceChange?.h24 ?? null,
        },
        txns: {
          h24: {
            buys: pair.txns?.h24?.buys ?? 0,
            sells: pair.txns?.h24?.sells ?? 0,
          },
          h6: {
            buys: pair.txns?.h6?.buys ?? 0,
            sells: pair.txns?.h6?.sells ?? 0,
          },
        },
        pairUrl: pair.url ?? null,
        dexId: pair.dexId ?? null,
      };
    } catch {
      return emptyToken(false);
    }
  },
);
