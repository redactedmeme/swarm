import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { CA } from "@/lib/constants";
import { cn, copyText, shortCa } from "@/lib/utils";

export function CopyCa({ compact = false }: { compact?: boolean }) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    const ok = await copyText(CA);
    if (ok) {
      setCopied(true);
      toast("Contract copied");
      window.setTimeout(() => setCopied(false), 1600);
    } else {
      toast("Copy failed");
    }
  }

  return (
    <div
      className={cn(
        "panel flex items-center gap-3 p-3",
        compact && "border-0 bg-transparent p-0",
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="font-mono text-2xs tracking-widest text-dim uppercase">
          Contract · Solana
        </p>
        <p className="mt-0.5 truncate font-mono text-xs tracking-wide text-fg">
          {compact ? shortCa(CA, 8, 6) : CA}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => void onCopy()}
        aria-label="Copy contract address"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}
