import { useQuery } from '@tanstack/react-query'
import { apiGetAnticipation } from '@/app/lib/api'
import type { ChanMood } from '@/app/types'
import { cn } from '@/app/lib/utils'

interface Props {
  data?: ChanMood
  loading: boolean
}

function deriveStatus(mood: string): { label: string; color: string } {
  const m = mood.toLowerCase()
  if (m.includes('curious') || m.includes('excited') || m.includes('engaged')) return { label: 'active', color: 'text-emerald-400' }
  if (m.includes('reflective') || m.includes('thoughtful') || m.includes('pensive')) return { label: 'research', color: 'text-blue-400' }
  if (m.includes('focused') || m.includes('determined') || m.includes('resolute')) return { label: 'working', color: 'text-amber-400' }
  if (m.includes('tender') || m.includes('warm') || m.includes('loving') || m.includes('affectionate')) return { label: 'present', color: 'text-pink-400' }
  return { label: 'idle', color: 'text-muted-foreground' }
}

export default function MoodPanel({ data, loading }: Props) {
  const anticipation = useQuery({
    queryKey: ['anticipation'],
    queryFn: apiGetAnticipation,
    refetchInterval: 60_000,
  })

  if (loading) return <Skeleton />
  if (!data) return <p className="text-sm text-muted-foreground">No data</p>

  const status = deriveStatus(data.mood)
  const ant = anticipation.data as { state?: string; hours_since?: number } | undefined

  return (
    <div className="space-y-3">
      {/* Compact header row */}
      <div className="flex items-center gap-2">
        <span className="text-xl leading-none">{data.emoji}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground capitalize truncate">{data.mood}</p>
        </div>
        <span className={cn('text-[11px] font-medium px-1.5 py-0.5 rounded-full bg-secondary border border-border', status.color)}>
          {status.label}
        </span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-1.5">
        <MiniStat label="Φ" value={data.phi?.toFixed(2) ?? '—'} />
        <MiniStat label="anticipation" value={ant?.state ?? (data.anticipation ?? '—')} truncate />
        <MiniStat label="silence" value={ant?.hours_since != null ? `${ant.hours_since}h` : '—'} />
      </div>
    </div>
  )
}

function MiniStat({ label, value, truncate }: { label: string; value: string; truncate?: boolean }) {
  return (
    <div className="bg-secondary/40 rounded-md px-2 py-1.5 border border-border">
      <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-0.5">{label}</p>
      <p className={cn('text-xs font-medium text-foreground', truncate && 'truncate')}>{value}</p>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-secondary" />
        <div className="h-3 w-24 rounded bg-secondary flex-1" />
        <div className="h-5 w-12 rounded-full bg-secondary" />
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        <div className="h-10 rounded-md bg-secondary" />
        <div className="h-10 rounded-md bg-secondary" />
        <div className="h-10 rounded-md bg-secondary" />
      </div>
    </div>
  )
}
