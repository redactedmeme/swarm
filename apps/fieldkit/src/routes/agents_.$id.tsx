import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { LiveBadge } from "@/components/live-dot";
import { Button } from "@/components/ui/button";
import { getAgent } from "@/data/roster";
import { useSwarm } from "@/lib/queries";

export const Route = createFileRoute("/agents_/$id")({ component: AgentDetail });

function AgentDetail() {
  const { id } = Route.useParams();
  const { data } = useSwarm();
  const live = data?.agents.find((a) => a.id === id);
  const fallback = getAgent(id);
  const agent = live ?? (fallback
    ? { ...fallback, meshOnline: null, lastSeenBucket: null, meshKnown: false }
    : null);

  if (!agent) {
    return (
      <div>
        <p className="font-mono text-sm text-dim">Unknown node.</p>
        <Button asChild variant="ghost" size="sm" className="mt-4">
          <Link to="/agents">Back to roster</Link>
        </Button>
      </div>
    );
  }

  const on = agent.meshKnown ? Boolean(agent.meshOnline) : agent.live;

  return (
    <div>
      <Link
        to="/agents"
        className="mb-4 inline-flex items-center gap-1.5 font-mono text-2xs tracking-widest text-dim uppercase no-underline hover:text-fg"
      >
        <ArrowLeft className="size-3.5" /> Roster
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-2xs tracking-widest text-dim uppercase">
            {agent.tier} · {agent.host}
          </p>
          <h1 className="mt-1 font-sans text-2xl font-extrabold tracking-tight">
            {agent.name}
          </h1>
        </div>
        <LiveBadge
          on={on}
          labelOn={agent.meshKnown ? "ONLINE" : "LIVE"}
          labelOff={agent.meshKnown ? "STALE" : "DORMANT"}
        />
      </div>

      <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted">{agent.desc}</p>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2">
        <Row k="Dimension" v={agent.dimension} />
        <Row k="Stack" v={agent.stack} />
        <Row k="Host" v={agent.host} />
        <Row k="Last seen" v={agent.lastSeenBucket ?? "—"} />
      </dl>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="panel p-3">
      <dt className="font-mono text-2xs tracking-widest text-dim uppercase">{k}</dt>
      <dd className="mt-1 text-sm text-fg">{v}</dd>
    </div>
  );
}
