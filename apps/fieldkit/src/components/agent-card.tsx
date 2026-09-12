import { Link } from "@tanstack/react-router";
import type { MergedAgent } from "@/lib/swarm";
import { LiveBadge } from "@/components/live-dot";
import { cn } from "@/lib/utils";

export function AgentCard({ agent }: { agent: MergedAgent }) {
  const on = agent.meshKnown ? Boolean(agent.meshOnline) : agent.live;
  return (
    <Link
      to="/agents/$id"
      params={{ id: agent.id }}
      className={cn(
        "panel group block p-4 no-underline transition-[border-color,background-color] duration-[var(--motion-quick)]",
        "hover:border-border-2",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-2xs tracking-widest text-dim uppercase">
            {agent.tier} · {agent.host}
          </p>
          <h3 className="mt-1 font-sans text-sm font-semibold tracking-wide text-fg">
            {agent.name}
          </h3>
        </div>
        <LiveBadge
          on={on}
          labelOn={agent.meshKnown ? "ONLINE" : "LIVE"}
          labelOff={agent.meshKnown ? "STALE" : "DORMANT"}
        />
      </div>
      <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-muted">
        {agent.desc}
      </p>
      <p className="mt-3 font-mono text-2xs tracking-wider text-dim uppercase">
        {agent.dimension}
      </p>
    </Link>
  );
}
