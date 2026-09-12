import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowUpRight, Trash2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { CopyCa } from "@/components/copy-ca";
import { PageHeader } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { SKILL_COMMANDS } from "@/data/pattern";
import { LINKS } from "@/lib/constants";
import { addNote, listNotes, removeNote, type FieldNote } from "@/lib/notes";

export const Route = createFileRoute("/field")({ component: FieldPage });

function FieldPage() {
  const [notes, setNotes] = useState<FieldNote[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setNotes(listNotes());
  }, []);

  function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setNotes(addNote(draft));
    setDraft("");
  }

  return (
    <div>
      <PageHeader kicker="Companion kit" title="Field" />

      <CopyCa />
      <p className="mt-2 mb-6 font-mono text-2xs tracking-wide text-dim">
        WARNING — verify contract before interaction
      </p>

      <Section title="Systems">
        <div className="grid gap-2 sm:grid-cols-2">
          <Ext href={LINKS.site} label="redacted.meme" sub="Canon site" />
          <Ext href={LINKS.terminal} label="Terminal" sub="NERV CLI" />
          <Ext href={LINKS.webchat} label="Webchat" sub="Talk to agents" />
          <Ext href={LINKS.dashboard} label="Dashboard" sub="Official ops" />
        </div>
      </Section>

      <Section title="Social">
        <div className="grid grid-cols-3 gap-2">
          <Ext href={LINKS.x} label="X" sub="@RedactedMemeFi" />
          <Ext href={LINKS.telegram} label="Telegram" sub="t.me" />
          <Ext href={LINKS.github} label="GitHub" sub="swarm" />
        </div>
      </Section>

      <Section title="Trade">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Ext href={LINKS.dexscreener} label="Dex" sub="Screener" />
          <Ext href={LINKS.birdeye} label="Birdeye" sub="Token" />
          <Ext href={LINKS.solscan} label="Solscan" sub="Explorer" />
          <Ext href={LINKS.jupiter} label="Jupiter" sub="Swap" />
        </div>
      </Section>

      <Section title="Canon">
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link to="/pattern">Pattern Blue</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <a href={LINKS.skill} target="_blank" rel="noopener noreferrer">
              Skill.md
            </a>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <a href={LINKS.llms} target="_blank" rel="noopener noreferrer">
              llms.txt
            </a>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <a href={LINKS.patternBlue} target="_blank" rel="noopener noreferrer">
              pattern-blue
            </a>
          </Button>
        </div>
      </Section>

      <Section title="Terminal commands">
        <div className="grid gap-3 sm:grid-cols-2">
          {SKILL_COMMANDS.map((g) => (
            <div key={g.group} className="panel p-3">
              <p className="mb-2 font-mono text-2xs tracking-widest text-dim uppercase">
                {g.group}
              </p>
              <ul className="space-y-1">
                {g.cmds.map((c) => (
                  <li key={c} className="font-mono text-xs text-muted">
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Field notes">
        <form onSubmit={onAdd} className="panel p-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value.slice(0, 400))}
            rows={3}
            placeholder="Local notes. Stay on this device."
            className="w-full resize-none rounded-sm border border-border bg-bg px-3 py-2 font-sans text-sm text-fg outline-none placeholder:text-dim focus:border-border-2"
          />
          <div className="mt-2 flex justify-end">
            <Button type="submit" size="sm" variant="ghost" disabled={!draft.trim()}>
              Keep
            </Button>
          </div>
        </form>
        <ul className="mt-3 grid gap-2">
          {notes.map((n) => (
            <li key={n.id} className="panel flex items-start justify-between gap-3 p-3">
              <div>
                <p className="text-sm text-fg">{n.body}</p>
                <p className="mt-1 font-mono text-2xs text-dim">
                  {new Date(n.at).toLocaleString()}
                </p>
              </div>
              <button
                type="button"
                aria-label="Delete note"
                className="text-dim hover:text-warn"
                onClick={() => setNotes(removeNote(n.id))}
              >
                <Trash2 className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="mb-3 font-mono text-2xs tracking-widest text-dim uppercase">{title}</h2>
      {children}
    </section>
  );
}

function Ext({ href, label, sub }: { href: string; label: string; sub: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="panel flex items-center justify-between gap-2 p-3 no-underline hover:border-border-2"
    >
      <span>
        <span className="block font-sans text-sm font-semibold">{label}</span>
        <span className="font-mono text-2xs tracking-widest text-dim uppercase">{sub}</span>
      </span>
      <ArrowUpRight className="size-3.5 text-dim" />
    </a>
  );
}
