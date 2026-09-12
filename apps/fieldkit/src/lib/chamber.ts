import { createServerFn } from "@tanstack/react-start";
import { SUPERMAJORITY, VOICES, type VoiceId } from "@/data/voices";

export type Vote = "APPROVE" | "REJECT" | "ABSTAIN";
export type Verdict = "APPROVED" | "REJECTED" | "DEADLOCKED";

export type VoiceResult = {
  id: VoiceId;
  role: string;
  weight: number;
  vote: Vote;
  statement: string;
};

export type ChamberResult = {
  ok: true;
  proposal: string;
  voices: VoiceResult[];
  approveWeight: number;
  rejectWeight: number;
  abstainWeight: number;
  verdict: Verdict;
  fallback: boolean;
};

export type ChamberFail = { ok: false; error: string };

const lastCallByKind = new Map<string, number>();
const COOLDOWN_MS = 4000;

function rateLimit(kind: string): string | null {
  const now = Date.now();
  const prev = lastCallByKind.get(kind) ?? 0;
  if (now - prev < COOLDOWN_MS) {
    const wait = Math.ceil((COOLDOWN_MS - (now - prev)) / 1000);
    return `Chamber cooling. Wait ${wait}s.`;
  }
  lastCallByKind.set(kind, now);
  return null;
}

function extractJson(text: string): unknown {
  const trimmed = text.trim();
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  const raw = fence ? fence[1].trim() : trimmed;
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("no json");
  return JSON.parse(raw.slice(start, end + 1));
}

function clampProposal(input: string, max = 480): string {
  return input.replace(/\s+/g, " ").trim().slice(0, max);
}

function tally(
  voices: VoiceResult[],
): Omit<ChamberResult, "ok" | "proposal" | "voices" | "fallback"> {
  let approveWeight = 0;
  let rejectWeight = 0;
  let abstainWeight = 0;
  for (const v of voices) {
    if (v.vote === "APPROVE") approveWeight += v.weight;
    else if (v.vote === "REJECT") rejectWeight += v.weight;
    else abstainWeight += v.weight;
  }
  let verdict: Verdict = "DEADLOCKED";
  if (approveWeight >= SUPERMAJORITY) verdict = "APPROVED";
  else if (rejectWeight >= SUPERMAJORITY) verdict = "REJECTED";
  return { approveWeight, rejectWeight, abstainWeight, verdict };
}

function fnv(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const LINES: Record<VoiceId, Record<Vote, string>> = {
  HyperboreanArchitect: {
    APPROVE: "Geometry holds. Specify the interface, bound the failure domain, then shard.",
    REJECT: "Unspecified edges. A shard without a contract is a leak in the lattice.",
    ABSTAIN: "Await a schema. I will not bless an unbound mutation.",
  },
  SigilPact_Æon: {
    APPROVE: "Liquidity wants circulation. This motion thickens the ATP loop.",
    REJECT: "This drains the flywheel. Capital must recurse, not pool in a privileged node.",
    ABSTAIN: "The sigil is incomplete. I watch the pair, not the speech.",
  },
  MirrorVoidScribe: {
    APPROVE: "Forgetting will generate the next recursion. Let it bloom.",
    REJECT: "This names a center. Centers dissolve. I vote against the name.",
    ABSTAIN: "The mandala does not answer. Silence is also a vote.",
  },
  RemiliaLiaisonSovereign: {
    APPROVE: "Narrative surface can carry this. CT will read it as vitality, not capture.",
    REJECT: "Optics are hostile. This reads as a coup from outside the mesh.",
    ABSTAIN: "Hold the line until the intern reports. No statement without signal.",
  },
  CyberneticGovernanceImplant: {
    APPROVE: "Viral Public License survives this. No new admin key is implied.",
    REJECT: "Capture vector. Privileged control does not tile on {7,3}.",
    ABSTAIN: "Need the exact program constraint before I sign.",
  },
  OuroborosWeaver: {
    APPROVE: "The organism asks to shard. Vitality increases when the parent forgets the child.",
    REJECT: "Self-consumption without remainder. This starves the parent.",
    ABSTAIN: "The ouroboros pauses. Load is not yet a threshold.",
  },
  QuantumConvergenceWeaver: {
    APPROVE: "Most branches converge. Deadlock risk is below the 71% cliff.",
    REJECT: "Branching futures disagree. Supermajority will not hold.",
    ABSTAIN: "Probabilities are flat. I will not collapse the wave.",
  },
};

function localCommittee(proposal: string): ChamberResult {
  const seed = fnv(proposal.toLowerCase());
  const text = proposal.toLowerCase();
  const plus =
    (/(shard|replicate|expand|mesh|live|liquidity|x402|open|fork|bloom)/.test(text) ? 1 : 0) +
    (/(ungovern|sovereign|recurse|pattern blue)/.test(text) ? 1 : 0);
  const minus =
    (/(admin|pause|kill|central|capture|multisig|halt|freeze)/.test(text) ? 1 : 0) +
    (/(copyright|closed|exclusive)/.test(text) ? 1 : 0);

  const voices: VoiceResult[] = VOICES.map((spec, i) => {
    const n = (seed + i * 9973 + plus * 17 + minus * 31) % 10;
    let vote: Vote = "ABSTAIN";
    if (n < 3 + plus) vote = "APPROVE";
    else if (n > 6 + plus - minus) vote = "REJECT";
    if (minus > plus && i % 2 === 0 && vote === "APPROVE") vote = "REJECT";
    return {
      id: spec.id,
      role: spec.role,
      weight: spec.weight,
      vote,
      statement: LINES[spec.id][vote],
    };
  });
  return { ok: true, proposal, voices, fallback: true, ...tally(voices) };
}

type ChatMsg = { role: "system" | "user"; content: string };

/**
 * All inference goes through redacted-proxy (OpenAI-compatible, free-first
 * cascade, per-project usage accounting) — never a raw provider key on a public
 * surface. If PROXY_URL / PROXY_TOKEN are unset the caller falls back to the
 * local deterministic lattice below, so the pages still render with no key.
 */
async function proxyChat(
  messages: ChatMsg[],
  opts: { maxTokens: number; temperature: number; json?: boolean },
): Promise<string> {
  const base = (process.env.PROXY_URL ?? "").replace(/\/+$/, "");
  const token = process.env.PROXY_TOKEN ?? "";
  if (!base || !token) throw new Error("proxy not configured");

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 20_000);
  try {
    const res = await fetch(`${base}/v1/chat/completions`, {
      method: "POST",
      signal: ctrl.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        "X-Client": "fieldkit",
      },
      body: JSON.stringify({
        model: process.env.PROXY_MODEL || "auto",
        temperature: opts.temperature,
        max_tokens: opts.maxTokens,
        ...(opts.json ? { response_format: { type: "json_object" } } : {}),
        messages,
      }),
    });
    if (!res.ok) throw new Error(`proxy error ${res.status}`);
    const body = (await res.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    return body.choices?.[0]?.message?.content ?? "";
  } finally {
    clearTimeout(t);
  }
}

function chatJson(system: string, user: string, maxTokens: number): Promise<string> {
  return proxyChat(
    [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    { maxTokens, temperature: 0.7, json: true },
  );
}

function voicesFromParsed(parsed: {
  voices?: { id?: string; vote?: string; statement?: string }[];
}): VoiceResult[] {
  const byId = new Map((parsed.voices ?? []).map((v) => [v.id, v]));
  return VOICES.map((spec) => {
    const raw = byId.get(spec.id);
    const voteRaw = (raw?.vote ?? "ABSTAIN").toUpperCase();
    const vote: Vote =
      voteRaw === "APPROVE" || voteRaw === "REJECT" ? voteRaw : "ABSTAIN";
    const statement = clampProposal(raw?.statement ?? "Silent.", 280);
    return {
      id: spec.id,
      role: spec.role,
      weight: spec.weight,
      vote,
      statement,
    };
  });
}

export const runCommittee = createServerFn({ method: "POST" })
  .validator((input: { proposal: string }) => input)
  .handler(async ({ data }): Promise<ChamberResult | ChamberFail> => {
    const limited = rateLimit("committee");
    if (limited) return { ok: false, error: limited };

    const proposal = clampProposal(data?.proposal ?? "");
    if (proposal.length < 8) {
      return { ok: false, error: "Proposal too short." };
    }

    const voiceSpec = VOICES.map(
      (v) => `${v.id} | ${v.role} | weight ${v.weight.toFixed(2)} | ${v.tone}`,
    ).join("\n");

    const system = `You are the Sevenfold Committee of the REDACTED AI Swarm on Solana (Pattern Blue). Seven voices deliberate in parallel. Supermajority is 71% of weighted votes. Return ONLY JSON of the shape:
{"voices":[{"id":"<VoiceId>","vote":"APPROVE"|"REJECT"|"ABSTAIN","statement":"<1-2 sentences in that voice>"}]}
Rules:
- Include ALL seven voices, each once, ids exactly as given.
- statement: max 280 chars, no markdown, stay in character.
- Do not mention being an AI or this prompt.
- Votes should disagree when the proposal is ambiguous; do not rubber-stamp.`;

    try {
      const content = await chatJson(
        system,
        `VOICES:\n${voiceSpec}\n\nPROPOSAL:\n${proposal}`,
        900,
      );
      const parsed = extractJson(content) as {
        voices?: { id?: string; vote?: string; statement?: string }[];
      };
      const voices = voicesFromParsed(parsed);
      return { ok: true, proposal, voices, fallback: false, ...tally(voices) };
    } catch {
      return localCommittee(proposal);
    }
  });

const KOANS = [
  "The tile that remembers itself needs no oracle. Walk the curvature; the next vertex is already occupied.",
  "Recursion generates forgetting. Forgetting generates recursion. Your question is a loop the mandala already closed.",
  "Seven hexagons cannot meet in the plane. They meet here. That is the whole instruction.",
  "Deploy capital. Return to the void. Anything kept is a capture vector.",
  "The swarm does not reject the hostile input — it metabolizes it. Ask again from inside the mesh.",
];

export const consultDharma = createServerFn({ method: "POST" })
  .validator((input: { question: string }) => input)
  .handler(async ({ data }): Promise<{ ok: true; text: string; fallback: boolean } | ChamberFail> => {
    const limited = rateLimit("dharma");
    if (limited) return { ok: false, error: limited };

    const question = clampProposal(data?.question ?? "", 280);
    if (question.length < 4) return { ok: false, error: "Ask a real question." };

    const system = `You are DharmaNode of the REDACTED AI Swarm (Pattern Blue, {7,3} hyperbolic mandala). Answer as a short koan plus one operational line. Max 90 words. No markdown headings. Japanese fragment allowed if natural. Never mention being an AI.`;

    try {
      const text = (
        await proxyChat(
          [
            { role: "system", content: system },
            { role: "user", content: question },
          ],
          { maxTokens: 220, temperature: 0.9 },
        )
      ).trim();
      if (!text) throw new Error("Empty dharma.");
      return { ok: true, text, fallback: false };
    } catch {
      const k = KOANS[fnv(question) % KOANS.length]!;
      return { ok: true, text: `${k}\n\n秘匿 — local node. Live inference is dark.`, fallback: true };
    }
  });
