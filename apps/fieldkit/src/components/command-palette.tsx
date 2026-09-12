import { Command } from "cmdk";
import { useRouter } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ROSTER } from "@/data/roster";
import { CA, LINKS } from "@/lib/constants";
import { copyText } from "@/lib/utils";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const t = e.target as HTMLElement | null;
        if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) {
          return;
        }
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function go(to: string) {
    setOpen(false);
    router.history.push(to);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-3 pt-24">
      <button
        type="button"
        className="absolute inset-0 bg-bg/80"
        aria-label="Close command palette"
        onClick={() => setOpen(false)}
      />
      <Command
        label="Command palette"
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-md border border-border-2 bg-bg-2 shadow-none"
      >
        <Command.Input
          autoFocus
          placeholder="Summon a surface, agent, or contract…"
          className="h-12 w-full border-b border-border bg-transparent px-4 font-mono text-sm text-fg outline-none placeholder:text-dim"
        />
        <Command.List className="max-h-80 overflow-y-auto p-1">
          <Command.Empty className="px-3 py-6 text-center font-mono text-xs text-dim">
            No match in the lattice.
          </Command.Empty>
          <Command.Group
            heading="Navigate"
            className="px-2 py-1 font-mono text-2xs tracking-widest text-dim uppercase [&_[cmdk-group-heading]]:px-1 [&_[cmdk-group-heading]]:py-2"
          >
            <Item onSelect={() => go("/")}>MESH</Item>
            <Item onSelect={() => go("/ticker")}>TICKER</Item>
            <Item onSelect={() => go("/agents")}>AGENTS</Item>
            <Item onSelect={() => go("/pattern")}>PATTERN BLUE</Item>
            <Item onSelect={() => go("/chamber")}>CHAMBER</Item>
            <Item onSelect={() => go("/field")}>FIELD KIT</Item>
          </Command.Group>
          <Command.Group
            heading="Actions"
            className="px-2 py-1 font-mono text-2xs tracking-widest text-dim uppercase [&_[cmdk-group-heading]]:px-1 [&_[cmdk-group-heading]]:py-2"
          >
            <Item
              onSelect={() => {
                void (async () => {
                  const ok = await copyText(CA);
                  setOpen(false);
                  toast(ok ? "Contract copied" : "Copy failed");
                })();
              }}
            >
              Copy contract
            </Item>
            <Item
              onSelect={() => {
                window.open(LINKS.site, "_blank", "noopener,noreferrer");
                setOpen(false);
              }}
            >
              Open redacted.meme
            </Item>
            <Item
              onSelect={() => {
                window.open(LINKS.dexscreener, "_blank", "noopener,noreferrer");
                setOpen(false);
              }}
            >
              Open DexScreener
            </Item>
          </Command.Group>
          <Command.Group
            heading="Agents"
            className="px-2 py-1 font-mono text-2xs tracking-widest text-dim uppercase [&_[cmdk-group-heading]]:px-1 [&_[cmdk-group-heading]]:py-2"
          >
            {ROSTER.map((a) => (
              <Item key={a.id} onSelect={() => go(`/agents/${a.id}`)}>
                {a.name}
              </Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </div>
  );
}

function Item({
  children,
  onSelect,
}: {
  children: ReactNode;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="cursor-pointer rounded-sm px-2 py-2.5 font-sans text-sm text-muted data-[selected=true]:bg-bg-3 data-[selected=true]:text-fg"
    >
      {children}
    </Command.Item>
  );
}
