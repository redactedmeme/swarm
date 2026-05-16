import type { ChanFact } from '@/app/types'

interface Props {
  data?: ChanFact[]
  loading: boolean
}

export default function FactsList({ data, loading }: Props) {
  if (loading) return (
    <div className="space-y-2 animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-8 rounded bg-secondary" />
      ))}
    </div>
  )
  if (!data?.length) return <p className="text-sm text-muted-foreground">No facts yet</p>

  return (
    <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
      {data.slice(0, 15).map((fact, i) => (
        <div key={i} className="flex items-start gap-2.5 text-sm">
          <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-primary/60 shrink-0" />
          <p className="text-foreground/90 leading-relaxed flex-1">{fact.text}</p>
          {fact.resonance != null && (
            <span className="shrink-0 text-[10px] text-muted-foreground font-mono mt-1">
              {(fact.resonance * 100).toFixed(0)}%
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
