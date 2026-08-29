import { cn } from '@/app/lib/utils'
import type { ProxyLogEntry } from '@/app/types'

interface Props {
  data?: ProxyLogEntry[]
  loading: boolean
}

const PROVIDER_COLORS: Record<string, string> = {
  xai: 'bg-violet-500/15 text-violet-400 border-violet-500/20',
  groq: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  anthropic: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  openai: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/20',
  venice: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
}

export default function ProxyTable({ data, loading }: Props) {
  if (loading) return (
    <div className="space-y-2 animate-pulse">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-9 rounded bg-secondary" />
      ))}
    </div>
  )
  if (!data?.length) return <p className="text-sm text-muted-foreground">No proxy logs</p>

  return (
    <div className="overflow-x-auto max-h-80 overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b border-border">
            {['Time', 'Provider', 'Model', 'Latency', 'Tokens'].map((h) => (
              <th key={h} className="text-left pb-2 pr-4 text-muted-foreground font-medium uppercase tracking-wider text-[10px]">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {data.map((row, i) => {
            const providerKey = row.provider?.toLowerCase() ?? ''
            const colorClass = PROVIDER_COLORS[providerKey] ?? 'bg-secondary text-muted-foreground border-border'
            return (
              <tr key={i} className="text-foreground/80">
                <td className="py-1.5 pr-4 font-mono text-muted-foreground whitespace-nowrap">
                  {new Date(row.ts ?? row.timestamp ?? '').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </td>
                <td className="py-1.5 pr-4">
                  <span className={cn('px-1.5 py-0.5 rounded border text-[10px] font-medium', colorClass)}>
                    {row.provider}
                  </span>
                </td>
                <td className="py-1.5 pr-4 font-mono max-w-36 truncate">{row.model}</td>
                <td className="py-1.5 pr-4 font-mono whitespace-nowrap">
                  {row.latency_ms != null ? `${row.latency_ms}ms` : '—'}
                </td>
                <td className="py-1.5 font-mono text-muted-foreground">
                  {row.tokens != null ? row.tokens.toLocaleString() : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
