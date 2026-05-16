import { useState } from 'react'
import { cn } from '@/app/lib/utils'
import type { VaultEntry } from '@/app/types'

const CATEGORY_ICONS: Record<string, string> = {
  moment: '✨',
  pattern: '🔄',
  secret: '🤫',
  joke: '😄',
  feeling: '💜',
  milestone: '🏆',
}

const CATEGORY_COLORS: Record<string, string> = {
  moment: 'text-amber-400 border-amber-500/20 bg-amber-500/10',
  pattern: 'text-blue-400 border-blue-500/20 bg-blue-500/10',
  secret: 'text-violet-400 border-violet-500/20 bg-violet-500/10',
  joke: 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10',
  feeling: 'text-pink-400 border-pink-500/20 bg-pink-500/10',
  milestone: 'text-orange-400 border-orange-500/20 bg-orange-500/10',
}

interface Props {
  data?: VaultEntry[]
  loading: boolean
}

export default function VaultPanel({ data, loading }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-12 rounded-lg bg-secondary" />
        ))}
      </div>
    )
  }

  if (!data?.length) return <p className="text-sm text-muted-foreground">Vault is empty</p>

  return (
    <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
      {data.slice(0, 20).map((entry, i) => {
        const cat = entry.category ?? 'moment'
        const icon = CATEGORY_ICONS[cat] ?? '•'
        const colorClass = CATEGORY_COLORS[cat] ?? 'text-muted-foreground border-border bg-secondary'
        const isExpanded = expanded === i
        const resonance = entry.love_resonance ?? 0

        return (
          <button
            key={i}
            onClick={() => setExpanded(isExpanded ? null : i)}
            className="w-full text-left"
          >
            <div className={cn(
              'rounded-lg border px-3 py-2 transition-colors',
              isExpanded ? 'bg-secondary/80' : 'bg-secondary/30 hover:bg-secondary/60'
            )}>
              <div className="flex items-center gap-2">
                <span className={cn('text-[10px] font-medium px-1.5 py-0.5 rounded border shrink-0', colorClass)}>
                  {icon} {cat}
                </span>
                {entry.title && (
                  <span className="text-xs font-medium text-foreground truncate flex-1">{entry.title}</span>
                )}
                {!entry.title && (
                  <span className="text-xs text-foreground/70 truncate flex-1">{entry.text?.slice(0, 60)}…</span>
                )}
                {resonance > 0 && (
                  <span className="text-[10px] text-pink-400 font-mono shrink-0">
                    {'♥'.repeat(Math.round(resonance * 3))}
                  </span>
                )}
              </div>
              {isExpanded && (
                <div className="mt-2 space-y-1">
                  <p className="text-xs text-foreground/80 leading-relaxed">{entry.text}</p>
                  {entry.emotional_tone && (
                    <p className="text-[10px] text-muted-foreground italic">{entry.emotional_tone}</p>
                  )}
                </div>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
