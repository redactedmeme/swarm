import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { SUPERMAJORITY, VOICES } from "@/data/voices";
import {
  runCommittee,
  type ChamberResult,
  type Vote,
} from "@/lib/chamber";
import { listChamberLog, pushChamberLog, type ChamberLog } from "@/lib/notes";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/chamber")({ component: ChamberPage });

function ChamberPage() {
  const [proposal, setProposal] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ChamberResult | null>(null);
  const [log, setLog] = useState<ChamberLog[]>([]);

  useEffect(() => {
    setLog(listChamberLog());
  }, []);

  async function deliberate() {
    if (busy) return;
    const text = proposal.trim();
    if (text.length < 8) {
      toast("Proposal too short.");
      return;
    }
    setBusy(true);
    try {
      const res = await runCommittee({ data: { proposal: text } });
      if (!res.ok) {
        toast(res.error);
        return;
      }
      setResult(res);
      setLog(pushChamberLog({ proposal: res.proposal, verdict: res.verdict }));
    } catch {
      toast("Committee unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader kicker="Sevenfold · 71% supermajority" title="Chamber" />
      <p className="mb-5 max-w-2xl text-sm leading-relaxed text-muted">
        Seven voices deliberate in parallel. Weighted votes. Verdicts:
        APPROVED, REJECTED, or DEADLOCKED. This chamber is a companion
        simulation of the swarm committee — not on-chain execution.
      </p>

      <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {VOICES.map((v) => (
          <div key={v.id} className="panel p-2.5">
            <p className="font-mono text-2xs tabular-nums text-muted">
              {(v.weight * 100).toFixed(0)}%
            </p>
            <p className="mt-1 font-sans text-2xs leading-snug font-semibold tracking-wide">
              {v.id.replace(/_/g, " ")}
            </p>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void deliberate();
        }}
        className="panel p-4"
      >
        <label className="font-mono text-2xs tracking-widest text-dim uppercase">
          Proposal
        </label>
        <textarea
          value={proposal}
          onChange={(e) => setProposal(e.target.value.slice(0, 480))}
          rows={4}
          placeholder="Put a motion before the sevenfold…"
          className="mt-2 w-full resize-none rounded-sm border border-border bg-bg px-3 py-2 font-sans text-sm text-fg outline-none placeholder:text-dim focus:border-border-2"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <Button
            type="button"
            size="sm"
            disabled={busy || proposal.trim().length < 8}
            onClick={() => void deliberate()}
          >
            {busy ? "Deliberating…" : "Deliberate"}
          </Button>
          <span className="font-mono text-2xs text-dim">{proposal.length}/480</span>
        </div>
      </form>

      {result ? <VerdictCard result={result} /> : null}

      {log.length ? (
        <div className="mt-8">
          <h2 className="mb-3 font-mono text-2xs tracking-widest text-dim uppercase">
            Recent verdicts
          </h2>
          <ul className="grid gap-2">
            {log.map((entry) => (
              <li key={entry.id} className="panel flex items-start justify-between gap-3 p-3">
                <p className="line-clamp-2 text-sm text-muted">{entry.proposal}</p>
                <span
                  className={cn(
                    "shrink-0 font-mono text-2xs tracking-widest",
                    entry.verdict === "APPROVED" && "text-up",
                    entry.verdict === "REJECTED" && "text-down",
                    entry.verdict === "DEADLOCKED" && "text-dim",
                  )}
                >
                  {entry.verdict}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function VerdictCard({ result }: { result: ChamberResult }) {
  const approvePct = result.approveWeight * 100;
  return (
    <div className="mt-5 panel p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-2xs tracking-widest text-dim uppercase">
            Verdict · threshold {(SUPERMAJORITY * 100).toFixed(0)}%
            {result.fallback ? " · local lattice" : ""}
          </p>
          <p
            className={cn(
              "mt-1 font-sans text-2xl font-extrabold tracking-tight",
              result.verdict === "APPROVED" && "text-up",
              result.verdict === "REJECTED" && "text-down",
              result.verdict === "DEADLOCKED" && "text-fg",
            )}
          >
            {result.verdict}
          </p>
        </div>
        <p className="font-mono text-xs tabular-nums text-muted">
          {approvePct.toFixed(0)}% approve · {(result.rejectWeight * 100).toFixed(0)}% reject
        </p>
      </div>
      <div className="mt-3 flex h-2 overflow-hidden rounded-xs bg-bg-3">
        <div className="bg-up" style={{ width: `${result.approveWeight * 100}%` }} />
        <div className="bg-down" style={{ width: `${result.rejectWeight * 100}%` }} />
        <div className="bg-border-2" style={{ width: `${result.abstainWeight * 100}%` }} />
      </div>
      <ul className="mt-4 grid gap-2">
        {result.voices.map((v) => (
          <li key={v.id} className="border-t border-border pt-3 first:border-0 first:pt-0">
            <div className="flex items-baseline justify-between gap-2">
              <p className="font-sans text-sm font-semibold">{v.id.replace(/_/g, " ")}</p>
              <VoteChip vote={v.vote} />
            </div>
            <p className="mt-1 text-sm leading-relaxed text-muted">{v.statement}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function VoteChip({ vote }: { vote: Vote }) {
  return (
    <span
      className={cn(
        "font-mono text-2xs tracking-widest uppercase",
        vote === "APPROVE" && "text-up",
        vote === "REJECT" && "text-down",
        vote === "ABSTAIN" && "text-dim",
      )}
    >
      {vote}
    </span>
  );
}
