import { cn } from "@/lib/utils";

export function LiveDot({
  on,
  className,
}: {
  on: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("live-dot inline-block shrink-0", !on && "off", className)}
      aria-hidden
    />
  );
}

export function LiveBadge({
  on,
  labelOn = "ONLINE",
  labelOff = "OFFLINE",
}: {
  on: boolean;
  labelOn?: string;
  labelOff?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-2xs tracking-widest uppercase",
        on ? "text-live" : "text-dim",
      )}
    >
      <LiveDot on={on} />
      {on ? labelOn : labelOff}
    </span>
  );
}
