import { useQuery } from '@tanstack/react-query'
import { Command } from 'lucide-react'
import { apiGetMood } from '@/app/lib/api'

interface Props {
  onPaletteOpen?: () => void
}

export default function ChanHeader({ onPaletteOpen }: Props) {
  const { data } = useQuery({ queryKey: ['mood'], queryFn: apiGetMood, refetchInterval: 60_000 })

  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/50 shrink-0">
      <div className="relative">
        <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-sm">
          {data?.emoji ?? '⬡'}
        </div>
        <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-background" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">redacted-chan</p>
        {data ? (
          <p className="text-xs text-muted-foreground truncate">
            {data.mood} · φ {data.phi?.toFixed(2) ?? '—'}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">connecting…</p>
        )}
      </div>
      {onPaletteOpen && (
        <button
          onClick={onPaletteOpen}
          className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-secondary text-xs transition-all"
          title="Command palette (⌘K)"
        >
          <Command size={12} />
          <span className="font-mono">K</span>
        </button>
      )}
    </div>
  )
}
