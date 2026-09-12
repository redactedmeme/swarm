import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { AgentCard } from "@/components/agent-card";
import { PageHeader } from "@/components/shell";
import type { AgentTier } from "@/data/roster";
import { useSwarm } from "@/lib/queries";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/agents")({ component: AgentsPage });

const FILTERS: Array<"ALL" | AgentTier> = ["ALL", "CORE", "APEX", "SPECIALIZED"];

function AgentsPage() {
  const { data, isLoading } = useSwarm();
  const [q, setQ] = useState("");
  const [tier, setTier] = useState<(typeof FILTERS)[number]>("ALL");

  const list = useMemo(() => {
    const agents = data?.agents ?? [];
    const needle = q.trim().toLowerCase();
    return agents.filter((a) => {
      if (tier !== "ALL" && a.tier !== tier) return false;
      if (!needle) return true;
      return (
        a.name.toLowerCase().includes(needle) ||
        a.id.toLowerCase().includes(needle) ||
        a.dimension.toLowerCase().includes(needle) ||
        a.desc.toLowerCase().includes(needle)
      );
    });
  }, [data, q, tier]);

  return (
    <div>
      <PageHeader
        kicker={data?.summary ?? "Roster"}
        title="Agents"
      />

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Filter by name, dimension, stack…"
        className="mb-3 h-11 w-full rounded-sm border border-border bg-bg-2 px-3 font-mono text-sm text-fg outline-none placeholder:text-dim focus:border-border-2"
      />

      <div className="mb-4 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setTier(f)}
            className={cn(
              "h-9 rounded-sm border px-3 font-mono text-2xs tracking-widest uppercase",
              tier === f
                ? "border-fg bg-fg text-bg"
                : "border-border text-dim hover:text-fg",
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="font-mono text-xs text-dim">Reading roster…</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {list.map((a) => (
            <AgentCard key={a.id} agent={a} />
          ))}
        </div>
      )}

      {!isLoading && list.length === 0 ? (
        <p className="mt-6 font-mono text-sm text-dim">No agents in this slice.</p>
      ) : null}
    </div>
  );
}
