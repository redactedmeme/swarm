import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Radio } from 'lucide-react'
import { apiGetSwarmActivity } from '@/app/lib/api'
import type { SwarmMessage } from '@/app/types'
import { cn } from '@/app/lib/utils'

const AGENT_COLORS: Record<string, string> = {
  'redacted-chan': 'text-violet-400',
  hermes:         'text-cyan-400',
  smolting:       'text-emerald-400',
  builder:        'text-amber-400',
  runtime:        'text-orange-400',
  system:         'text-zinc-400',
}

const MSG_TYPE_BADGE: Record<string, string> = {
  task:      'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
  reply:     'bg-violet-500/10 text-violet-400 border-violet-500/20',
  result:    'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  error:     'bg-red-500/10 text-red-400 border-red-500/20',
  ping:      'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  heartbeat: 'bg-zinc-500/8 text-zinc-500 border-zinc-600/20',
}

function agentColor(name?: string) {
  if (!name) return 'text-muted-foreground'
  const key = Object.keys(AGENT_COLORS).find((k) => name.toLowerCase().includes(k))
  return key ? AGENT_COLORS[key] : 'text-muted-foreground'
}

function formatTs(ts?: string | number): string {
  if (!ts) return ''
  try {
    const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

function msgSummary(msg: SwarmMessage): string {
  const content = msg.content ?? (msg as Record<string, unknown>).message ?? (msg as Record<string, unknown>).text
  if (typeof content === 'string') return content.slice(0, 120)
  if (content) return JSON.stringify(content).slice(0, 120)
  return JSON.stringify(msg).slice(0, 120)
}

export default function SwarmFeed({ className }: { className?: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['swarm-activity'],
    queryFn: () => apiGetSwarmActivity(60),
    refetchInterval: 10_000,
  })

  const messages = data?.messages ?? []
  const realMessages = messages.filter((m) => m._source !== 'heartbeat')
  const heartbeats  = messages.filter((m) => m._source === 'heartbeat')

  return (
    <div className={cn('bg-card border border-border rounded-xl overflow-hidden', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Radio size={13} className="text-primary animate-pulse" />
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Swarm Activity</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-[10px] text-emerald-400">{heartbeats.length} alive</span>
          {realMessages.length > 0 && (
            <span className="text-[10px] text-cyan-400">{realMessages.length} messages</span>
          )}
          <span className="text-[10px] text-muted-foreground">10s</span>
        </div>
      </div>

      {/* Heartbeat status strip */}
      {heartbeats.length > 0 && (
        <div className="flex items-center gap-1.5 px-3 py-2 bg-secondary/20 border-b border-border/50 flex-wrap">
          {heartbeats.map((hb) => (
            <div key={String(hb.id)} className="flex items-center gap-1 text-[10px]">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
              <span className={agentColor(hb.from)}>{hb.from}</span>
              <span className="text-muted-foreground/40">{msgSummary(hb)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Message log */}
      <div className="max-h-56 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-1.5 p-3 animate-pulse">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-7 rounded bg-secondary" />
            ))}
          </div>
        ) : realMessages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 gap-1">
            <p className="text-xs text-muted-foreground">No inter-agent messages yet</p>
            <p className="text-[10px] text-muted-foreground/50">Messages appear when agents send tasks to each other</p>
          </div>
        ) : (
          <div className="divide-y divide-border/40">
            <AnimatePresence initial={false}>
              {realMessages.map((msg, i) => {
                const typeKey = (String(msg.type ?? '')).toLowerCase()
                const badgeClass = MSG_TYPE_BADGE[typeKey] ?? 'bg-secondary text-muted-foreground border-border'
                return (
                  <motion.div
                    key={String(msg.id ?? i)}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-start gap-2.5 px-3 py-2 text-xs hover:bg-secondary/30 transition-colors"
                  >
                    <span className="text-[10px] font-mono text-muted-foreground/50 shrink-0 pt-0.5 w-16">
                      {formatTs(msg.ts)}
                    </span>

                    <div className="flex items-center gap-1 shrink-0">
                      <span className={cn('font-medium', agentColor(String(msg.from ?? '')))}>{msg.from ?? '?'}</span>
                      <span className="text-muted-foreground/40 text-[10px]">→</span>
                      <span className={cn('font-medium', agentColor(String(msg.to ?? '')))}>{msg.to ?? '*'}</span>
                    </div>

                    {msg.type && (
                      <span className={cn('shrink-0 px-1 py-0.5 rounded border text-[9px] font-medium', badgeClass)}>
                        {msg.type}
                      </span>
                    )}

                    <span className="text-foreground/70 truncate flex-1">{msgSummary(msg)}</span>
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  )
}
