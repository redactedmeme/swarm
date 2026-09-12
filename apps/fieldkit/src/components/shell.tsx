import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  Compass,
  Hexagon,
  Radio,
  Scale,
  Search,
} from "lucide-react";
import type { ReactNode } from "react";
import { CommandPalette } from "@/components/command-palette";
import { DoctrineTicker } from "@/components/doctrine-ticker";
import { LiveDot } from "@/components/live-dot";
import { useSwarm, useToken } from "@/lib/queries";
import { cn, formatPct, formatPrice } from "@/lib/utils";

const NAV = [
  { to: "/", label: "MESH", icon: Radio },
  { to: "/ticker", label: "TICKER", icon: Activity },
  { to: "/agents", label: "AGENTS", icon: Hexagon },
  { to: "/chamber", label: "CHAMBER", icon: Scale },
  { to: "/field", label: "FIELD", icon: Compass },
] as const;

export function Shell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const swarm = useSwarm();
  const token = useToken();
  const online = swarm.data?.onlineCount ?? 0;
  const change = token.data?.priceChange.h24 ?? null;

  return (
    <div className="relative min-h-dvh bg-bg text-fg">
      <div className="scanlines" />
      <CommandPalette />
      <header className="sticky top-0 z-40 border-b border-border bg-bg/95 backdrop-blur-sm">
        <div className="mx-auto flex h-[var(--nav-h)] max-w-6xl items-center gap-3 px-4">
          <Link to="/" className="shrink-0 no-underline">
            <span className="font-sans text-sm font-extrabold tracking-wide">
              <span className="text-dim">[</span>REDACTED
              <span className="text-dim">]</span>
            </span>
            <span className="ml-2 hidden font-mono text-2xs tracking-widest text-dim uppercase sm:inline">
              Field Kit
            </span>
          </Link>
          <nav className="ml-6 hidden items-center gap-4 lg:flex">
            {NAV.map((item) => {
              const active =
                item.to === "/"
                  ? pathname === "/"
                  : pathname === item.to || pathname.startsWith(`${item.to}/`);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "font-sans text-xs font-semibold tracking-widest uppercase no-underline transition-colors duration-[var(--motion-quick)]",
                    active ? "text-fg" : "text-dim hover:text-muted",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
            <Link
              to="/pattern"
              className={cn(
                "font-sans text-xs font-semibold tracking-widest uppercase no-underline",
                pathname === "/pattern" ? "text-fg" : "text-dim hover:text-muted",
              )}
            >
              PATTERN
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-1.5 font-mono text-2xs tracking-widest text-dim uppercase sm:flex">
              <LiveDot on={online > 0} />
              {online} MESH
            </span>
            <span
              className={cn(
                "hidden font-mono text-2xs tracking-wide tabular-nums md:inline",
                change != null && change > 0 && "text-up",
                change != null && change < 0 && "text-down",
                (change == null || change === 0) && "text-dim",
              )}
            >
              {formatPrice(token.data?.priceUsd)} {formatPct(change)}
            </span>
            <kbd className="hidden rounded-sm border border-border px-1.5 py-0.5 font-mono text-2xs text-dim lg:inline">
              ⌘K
            </kbd>
          </div>
        </div>
        <DoctrineTicker />
      </header>

      <div className="mx-auto flex max-w-6xl">
        <main className="min-w-0 flex-1 px-4 pt-5 pb-[calc(var(--tab-h)+env(safe-area-inset-bottom)+4.5rem)] lg:pb-24">
          {children}
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-bg/95 backdrop-blur-sm lg:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        aria-label="Primary"
      >
        <ul className="mx-auto grid h-[var(--tab-h)] max-w-lg grid-cols-5">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active =
              item.to === "/"
                ? pathname === "/"
                : pathname === item.to || pathname.startsWith(`${item.to}/`);
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className={cn(
                    "flex h-full flex-col items-center justify-center gap-1 no-underline",
                    active ? "text-fg" : "text-dim",
                  )}
                >
                  <Icon className="size-4" strokeWidth={1.75} />
                  <span className="font-mono text-2xs tracking-widest uppercase">
                    {item.label}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

export function PageHeader({
  kicker,
  title,
  action,
}: {
  kicker: string;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex items-end justify-between gap-3">
      <div>
        <p className="font-mono text-2xs tracking-widest text-dim uppercase">{kicker}</p>
        <h1 className="mt-1 font-sans text-2xl font-extrabold tracking-tight text-fg sm:text-3xl">
          {title}
        </h1>
      </div>
      {action}
    </div>
  );
}

export function SearchHint() {
  return (
    <p className="mb-4 hidden items-center gap-2 font-mono text-2xs tracking-wide text-dim lg:flex">
      <Search className="size-3" />
      Press ⌘K or / to summon
    </p>
  );
}
