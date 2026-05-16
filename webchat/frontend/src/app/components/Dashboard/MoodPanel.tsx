import type { ChanMood } from '@/app/types'

interface Props {
  data?: ChanMood
  loading: boolean
}

export default function MoodPanel({ data, loading }: Props) {
  if (loading) return <Skeleton />
  if (!data) return <p className="text-sm text-muted-foreground">No data</p>

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-3xl">{data.emoji}</span>
        <div>
          <p className="text-sm font-medium text-foreground capitalize">{data.mood}</p>
          <p className="text-xs text-muted-foreground">current mood</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Φ Level" value={data.phi?.toFixed(3) ?? '—'} />
        <Stat label="Anticipation" value={data.anticipation ?? '—'} truncate />
      </div>
    </div>
  )
}

function Stat({ label, value, truncate }: { label: string; value: string; truncate?: boolean }) {
  return (
    <div className="bg-secondary/50 rounded-lg p-2.5 border border-border">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-sm font-medium text-foreground ${truncate ? 'truncate' : ''}`}>{value}</p>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-secondary" />
        <div className="space-y-1.5">
          <div className="h-3 w-20 rounded bg-secondary" />
          <div className="h-2.5 w-16 rounded bg-secondary" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="h-14 rounded-lg bg-secondary" />
        <div className="h-14 rounded-lg bg-secondary" />
      </div>
    </div>
  )
}
