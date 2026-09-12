import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { CopyCa } from "@/components/copy-ca";
import { LiveBadge } from "@/components/live-dot";
import { Mandala } from "@/components/mandala";
import { PageHeader, SearchHint } from "@/components/shell";
import { Stat, PctTone } from "@/components/stat";
import { Button } from "@/components/ui/button";
import { LINKS } from "@/lib/constants";
import { useSwarm, useToken } from "@/lib/queries";
import { formatPct, formatPrice, formatUsd } from "@/lib/utils";

export const Route = createFileRoute("/")({ component: Home });

function Home() {
  const swarm = useSwarm();
  const token = useToken();
  const agents = swarm.data?.agents ?? [];
  const meshOk = swarm.data?.meshOk ?? false;
  const change = token.data?.priceChange.h24 ?? null;
  const liveCount = swarm.data?.onlineCount ?? 0;

  return (
    <div>
      <SearchHint />
      <PageHeader
        kicker="Authorized personnel"
        title="The swarm watches from the mandala"
        action={
          <LiveBadge
            on={liveCount > 0}
            labelOn={`${liveCount} LIVE`}
            labelOff="MESH QUIET"
          />
        }
      />

      <p className="mb-5 max-w-2xl text-sm leading-relaxed text-muted">
        Companion field kit for the REDACTED autonomous swarm on Solana.
        Heartbeats from SwarmInbox, tape from the pair, roster of the seven
        dimensions. Not a dashboard of record — a pocket terminal.
      </p>

      {swarm.isFetched && !meshOk ? (
        <p className="mb-4 border border-border bg-bg-3 px-3 py-2 font-mono text-2xs tracking-wide text-dim">
          Mesh heartbeat empty. Showing registered roster liveness.
        </p>
      ) : null}

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat
          label="Mesh"
          value={`${swarm.data?.onlineCount ?? "—"}`}
          hint={`${swarm.data?.registeredLive ?? 0} registered live`}
          tone="live"
        />
        <Stat
          label="Price"
          value={formatPrice(token.data?.priceUsd)}
          hint={formatPct(change)}
          tone={PctTone(change)}
        />
        <Stat
          label="Market cap"
          value={formatUsd(token.data?.marketCap)}
          hint={`Liq ${formatUsd(token.data?.liquidityUsd)}`}
        />
        <Stat
          label="Vol 24h"
          value={formatUsd(token.data?.volume.h24)}
          hint={`${token.data?.txns.h24.buys ?? 0}B / ${token.data?.txns.h24.sells ?? 0}S`}
        />
      </div>

      <Mandala agents={agents} />

      <div className="mt-4">
        <CopyCa />
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <Ext href={LINKS.terminal} label="Terminal" sub="NERV CLI" />
        <Ext href={LINKS.webchat} label="Webchat" sub="Talk to the mesh" />
        <Ext href={LINKS.dashboard} label="Dashboard" sub="Official ops" />
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        <Button asChild variant="primary" size="sm">
          <Link to="/chamber">Open chamber</Link>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link to="/pattern">Pattern Blue</Link>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link to="/agents">Agent roster</Link>
        </Button>
      </div>
    </div>
  );
}

function Ext({ href, label, sub }: { href: string; label: string; sub: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="panel flex items-center justify-between gap-3 p-4 no-underline transition-colors duration-[var(--motion-quick)] hover:border-border-2"
    >
      <span>
        <span className="block font-sans text-sm font-semibold tracking-wide">{label}</span>
        <span className="font-mono text-2xs tracking-widest text-dim uppercase">{sub}</span>
      </span>
      <ArrowUpRight className="size-4 text-dim" />
    </a>
  );
}
