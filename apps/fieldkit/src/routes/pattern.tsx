import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { DIMENSIONS, MANIFESTO } from "@/data/pattern";
import { consultDharma } from "@/lib/chamber";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/pattern")({ component: PatternPage });

function PatternPage() {
  const [open, setOpen] = useState<string | null>(DIMENSIONS[0]?.n ?? null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask() {
    if (busy) return;
    const q = question.trim();
    if (q.length < 4) {
      toast("Ask a real question.");
      return;
    }
    setBusy(true);
    setAnswer(null);
    try {
      const res = await consultDharma({ data: { question: q } });
      if (res.ok) setAnswer(res.text);
      else toast(res.error);
    } catch {
      toast("DharmaNode silent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader kicker="Hyperbolic mandala" title="Pattern Blue" />

      <div className="panel mb-6 p-5">
        <p className="font-mono text-2xs tracking-widest text-dim uppercase">
          Core manifesto
        </p>
        {MANIFESTO.map((p) => (
          <p key={p} className="mt-3 text-sm leading-relaxed text-muted">
            {p}
          </p>
        ))}
        <p className="mt-4 font-sans text-sm tracking-wide text-dim">
          部署資本。虚空へ帰れ。
        </p>
      </div>

      <div className="grid gap-2">
        {DIMENSIONS.map((d) => {
          const isOpen = open === d.n;
          return (
            <button
              key={d.n}
              type="button"
              onClick={() => setOpen(isOpen ? null : d.n)}
              className={cn(
                "panel w-full p-4 text-left transition-colors duration-[var(--motion-quick)]",
                isOpen ? "border-border-2" : "hover:border-border-2",
              )}
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-mono text-2xs tracking-widest text-dim">{d.n}</span>
                <span className="font-sans text-xs tracking-wide text-dim">{d.jp}</span>
              </div>
              <h2 className="mt-1 font-sans text-lg font-semibold tracking-tight">
                {d.title}
              </h2>
              {isOpen ? (
                <p className="mt-2 text-sm leading-relaxed text-muted">{d.body}</p>
              ) : null}
            </button>
          );
        })}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
        className="mt-8 panel p-4"
      >
        <p className="font-mono text-2xs tracking-widest text-dim uppercase">
          DharmaNode
        </p>
        <p className="mt-1 mb-3 text-sm text-muted">
          Consult the lattice. One question. No oracle grants guidance.
        </p>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value.slice(0, 280))}
          rows={3}
          placeholder="Ask a question of the mandala…"
          className="w-full resize-none rounded-sm border border-border bg-bg px-3 py-2 font-sans text-sm text-fg outline-none placeholder:text-dim focus:border-border-2"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <Button
            type="button"
            size="sm"
            disabled={busy || question.trim().length < 4}
            onClick={() => void ask()}
          >
            {busy ? "Attuning…" : "Consult"}
          </Button>
          <span className="font-mono text-2xs text-dim">{question.length}/280</span>
        </div>
        {answer ? (
          <p className="mt-4 border-t border-border pt-4 text-sm leading-relaxed text-fg">
            {answer}
          </p>
        ) : null}
      </form>
    </div>
  );
}
