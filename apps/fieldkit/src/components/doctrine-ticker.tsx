import { DOCTRINE } from "@/lib/constants";

export function DoctrineTicker() {
  const seq = [...DOCTRINE, ...DOCTRINE];
  return (
    <div
      className="relative overflow-hidden border-y border-border bg-bg-2"
      aria-label="Swarm doctrine"
    >
      <div className="ticker-track py-1.5">
        {[0, 1].map((copy) => (
          <div key={copy} className="flex items-center">
            {seq.map((item, i) => (
              <span key={`${copy}-${i}`} className="flex items-center">
                <span className="px-3 font-mono text-2xs tracking-widest text-dim uppercase whitespace-nowrap">
                  {item}
                </span>
                <span className="text-border-2" aria-hidden>
                  ◆
                </span>
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
