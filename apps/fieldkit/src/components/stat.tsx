import { cn } from "@/lib/utils";

export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "up" | "down" | "live";
}) {
  return (
    <div className="panel p-3">
      <p className="font-mono text-2xs tracking-widest text-dim uppercase">{label}</p>
      <p
        className={cn(
          "mt-1 font-mono text-lg tracking-tight tabular-nums",
          tone === "up" && "text-up",
          tone === "down" && "text-down",
          tone === "live" && "text-live",
          tone === "neutral" && "text-fg",
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-0.5 font-mono text-2xs tracking-wide text-dim">{hint}</p>
      ) : null}
    </div>
  );
}

export function PctTone(n: number | null | undefined): "up" | "down" | "neutral" {
  if (n == null || n === 0) return "neutral";
  return n > 0 ? "up" : "down";
}
