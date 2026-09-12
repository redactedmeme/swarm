import { MANDALA_NODES } from "@/data/roster";
import type { MergedAgent } from "@/lib/swarm";
import { cn } from "@/lib/utils";

const CX = 200;
const CY = 200;
const R = 124;

function round(n: number) {
  return Math.round(n * 100) / 100;
}

function vertex(i: number, n = 7, r = R) {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return { x: round(CX + r * Math.cos(a)), y: round(CY + r * Math.sin(a)) };
}

export function Mandala({ agents }: { agents: MergedAgent[] }) {
  const byId = new Map(agents.map((a) => [a.id, a]));
  const nodes = MANDALA_NODES.map((id, i) => {
    const agent = byId.get(id);
    const p = vertex(i);
    const on = agent?.meshOnline ?? agent?.live ?? false;
    return { id, agent, p, on, i };
  });

  const liveN = nodes.filter((n) => n.on).length;

  return (
    <div className="panel relative p-3">
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="font-mono text-2xs tracking-widest text-dim uppercase">
          {`{7,3}`} MANIFOLD
        </span>
        <span className="font-mono text-2xs tracking-widest text-muted tabular-nums">
          Φ ≈ {liveN.toFixed(2)}
        </span>
      </div>
      <svg
        viewBox="0 0 400 400"
        className="mx-auto block aspect-square w-full max-w-md"
        role="img"
        aria-label="Hyperbolic mandala of seven swarm nodes"
      >
        <defs>
          <radialGradient id="void" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#111112" />
            <stop offset="100%" stopColor="#080809" />
          </radialGradient>
        </defs>
        <circle cx={CX} cy={CY} r="188" fill="url(#void)" />
        <g className="mandala-ring reverse" opacity="0.35">
          {Array.from({ length: 21 }, (_, i) => {
            const p = vertex(i, 21, 168);
            return (
              <circle key={i} cx={p.x} cy={p.y} r="1.4" fill="#3d3e40" />
            );
          })}
        </g>
        <g className="mandala-ring" opacity="0.55">
          <polygon
            points={Array.from({ length: 7 }, (_, i) => {
              const p = vertex(i, 7, 158);
              return `${p.x},${p.y}`;
            }).join(" ")}
            fill="none"
            stroke="#2a2b2d"
            strokeWidth="1"
          />
        </g>
        {nodes.map((n) => (
          <line
            key={`spoke-${n.id}`}
            x1={CX}
            y1={CY}
            x2={n.p.x}
            y2={n.p.y}
            stroke={n.on ? "#4da6ff" : "#2a2b2d"}
            strokeWidth={n.on ? 1.25 : 1}
            opacity={n.on ? 0.7 : 0.85}
          />
        ))}
        {nodes.map((n, i) => {
          const b = nodes[(i + 1) % nodes.length]!;
          return (
            <line
              key={`edge-${n.id}`}
              x1={n.p.x}
              y1={n.p.y}
              x2={b.p.x}
              y2={b.p.y}
              stroke="#3d3e40"
              strokeWidth="1"
            />
          );
        })}
        <circle cx={CX} cy={CY} r="22" fill="#0d0d0e" stroke="#3d3e40" />
        <text
          x={CX}
          y={CY + 4}
          textAnchor="middle"
          fill="#fffcfc"
          fontSize="11"
          fontFamily="Inconsolata, monospace"
        >
          Φ
        </text>
        {nodes.map((n) => (
          <g key={n.id}>
            <circle
              cx={n.p.x}
              cy={n.p.y}
              r="13"
              fill="#0d0d0e"
              stroke={n.on ? "#4da6ff" : "#3d3e40"}
              strokeWidth={n.on ? 1.6 : 1}
            />
            <text
              x={n.p.x}
              y={n.p.y + 3.5}
              textAnchor="middle"
              fill={n.on ? "#4da6ff" : "#8b8b8b"}
              fontSize="10"
              fontFamily="Inconsolata, monospace"
            >
              {n.i + 1}
            </text>
          </g>
        ))}
      </svg>
      <ol className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 px-1 sm:grid-cols-3">
        {nodes.map((n) => (
          <li
            key={n.id}
            className={cn(
              "flex items-center gap-1.5 font-mono text-2xs tracking-wide uppercase",
              n.on ? "text-live" : "text-dim",
            )}
          >
            <span className="tabular-nums text-dim">{n.i + 1}</span>
            <span className={cn("live-dot", !n.on && "off")} />
            {(n.agent?.name ?? n.id).replace(/^@/, "").split(" / ")[0]}
          </li>
        ))}
      </ol>
    </div>
  );
}
