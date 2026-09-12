import { createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { CopyCa } from "@/components/copy-ca";
import { PageHeader } from "@/components/shell";
import { Stat, PctTone } from "@/components/stat";
import { LINKS } from "@/lib/constants";
import { useToken } from "@/lib/queries";
import { formatPct, formatPrice, formatUsd } from "@/lib/utils";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/ticker")({ component: TickerPage });

function TickerPage() {
  const { data, isLoading, isError } = useToken();
  const change = data?.priceChange.h24 ?? null;
  const h24 = data?.txns.h24 ?? { buys: 0, sells: 0 };
  const total = h24.buys + h24.sells;
  const buyPct = total ? (h24.buys / total) * 100 : 50;

  const vols = [
    { k: "5m", v: data?.volume.m5 ?? 0 },
    { k: "1h", v: data?.volume.h1 ?? 0 },
    { k: "6h", v: data?.volume.h6 ?? 0 },
    { k: "24h", v: data?.volume.h24 ?? 0 },
  ];
  const maxV = Math.max(...vols.map((x) => x.v), 1);

  return (
    <div>
      <PageHeader kicker="Solana · PumpSwap" title="Ticker" />

      {isError || (data && !data.ok) ? (
        <p className="mb-4 border border-border bg-bg-3 px-3 py-2 font-mono text-xs text-dim">
          Tape unavailable. Pair still lives on-chain — use the links below.
        </p>
      ) : null}

      <p
        className={cn(
          "font-mono text-4xl tracking-tight tabular-nums sm:text-5xl",
          PctTone(change) === "up" && "text-up",
          PctTone(change) === "down" && "text-down",
        )}
      >
        {isLoading ? "—" : formatPrice(data?.priceUsd)}
      </p>
      <p className="mt-1 font-mono text-sm tracking-wide text-muted">
        {formatPct(change)} 24h
        {data?.dexId ? ` · ${data.dexId}` : ""}
      </p>

      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Market cap" value={formatUsd(data?.marketCap)} />
        <Stat label="FDV" value={formatUsd(data?.fdv)} />
        <Stat label="Liquidity" value={formatUsd(data?.liquidityUsd)} />
        <Stat label="Vol 24h" value={formatUsd(data?.volume.h24)} />
      </div>

      <div className="mt-4 panel p-4">
        <p className="font-mono text-2xs tracking-widest text-dim uppercase">
          24h flow · {h24.buys} buys / {h24.sells} sells
        </p>
        <div className="mt-3 flex h-2 overflow-hidden rounded-xs bg-bg-3">
          <div className="bg-up" style={{ width: `${buyPct}%` }} />
          <div className="bg-down" style={{ width: `${100 - buyPct}%` }} />
        </div>
        <div className="mt-2 flex justify-between font-mono text-2xs tracking-wide text-dim">
          <span className="text-up">Buys {buyPct.toFixed(0)}%</span>
          <span className="text-down">Sells {(100 - buyPct).toFixed(0)}%</span>
        </div>
      </div>

      <div className="mt-4 panel p-4">
        <p className="mb-3 font-mono text-2xs tracking-widest text-dim uppercase">
          Volume windows
        </p>
        <div className="grid grid-cols-4 gap-3">
          {vols.map((w) => (
            <div key={w.k} className="flex flex-col items-stretch gap-2">
              <div className="flex h-24 items-end rounded-xs bg-bg-3 p-1">
                <div
                  className="w-full rounded-xs bg-border-2"
                  style={{ height: `${Math.max(6, (w.v / maxV) * 100)}%` }}
                />
              </div>
              <p className="text-center font-mono text-2xs tracking-widest text-dim uppercase">
                {w.k}
              </p>
              <p className="text-center font-mono text-xs tabular-nums text-muted">
                {formatUsd(w.v)}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <CopyCa />
      </div>
      <p className="mt-2 font-mono text-2xs tracking-wide text-dim">
        WARNING — verify contract before interaction
      </p>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Ext href={LINKS.dexscreener} label="DexScreener" />
        <Ext href={LINKS.birdeye} label="Birdeye" />
        <Ext href={LINKS.solscan} label="Solscan" />
        <Ext href={LINKS.jupiter} label="Jupiter" />
      </div>
    </div>
  );
}

function Ext({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="panel flex h-12 items-center justify-between px-3 no-underline hover:border-border-2"
    >
      <span className="font-sans text-xs font-semibold tracking-widest uppercase">
        {label}
      </span>
      <ArrowUpRight className="size-3.5 text-dim" />
    </a>
  );
}
