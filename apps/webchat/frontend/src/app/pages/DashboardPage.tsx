import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Activity, Brain, Zap, Shield, BookHeart, BarChart2, Inbox, GitBranch } from 'lucide-react'
import {
  apiGetMood, apiGetFacts, apiGetProxyLogs, apiGetVault,
  apiGetSwarmPending, apiGetSwarmActivity,
} from '@/app/lib/api'
import type { ProxyLogEntry, SwarmMessage } from '@/app/types'
import AgentGrid from '@/app/components/Dashboard/AgentGrid'
import MoodPanel from '@/app/components/Dashboard/MoodPanel'
import FactsList from '@/app/components/Dashboard/FactsList'
import ProxyTable from '@/app/components/Dashboard/ProxyTable'
import VaultPanel from '@/app/components/Dashboard/VaultPanel'
import { cn } from '@/app/lib/utils'

const STAGGER = { hidden: {}, show: { transition: { staggerChildren: 0.07 } } }
const ITEM = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: { duration: 0.3 } } }

const PROVIDER_COLORS: Record<string, string> = {
  xai:       'bg-violet-500/15 text-violet-300 border-violet-500/20',
  groq:      'bg-emerald-500/15 text-emerald-300 border-emerald-500/20',
  anthropic: 'bg-amber-500/15 text-amber-300 border-amber-500/20',
  openai:    'bg-cyan-500/15 text-cyan-300 border-cyan-500/20',
  venice:    'bg-blue-500/15 text-blue-300 border-blue-500/20',
}

const AGENT_COLORS: Record<string, string> = {
  'redacted-chan': 'border-violet-500/30 bg-violet-500/5',
  hermes:          'border-cyan-500/30 bg-cyan-500/5',
  smolting:        'border-emerald-500/30 bg-emerald-500/5',
  builder:         'border-amber-500/30 bg-amber-500/5',
}

interface ProviderStats {
  provider: string; calls: number; tokens: number; avgLatency: number
}

function computeProviderStats(entries: ProxyLogEntry[]): ProviderStats[] {
  const map: Record<string, { calls: number; tokens: number; latencySum: number }> = {}
  for (const e of entries) {
    const p = (e.provider ?? 'unknown').toLowerCase()
    if (!map[p]) map[p] = { calls: 0, tokens: 0, latencySum: 0 }
    map[p].calls++
    map[p].tokens += e.tokens ?? 0
    map[p].latencySum += e.latency_ms ?? 0
  }
  return Object.entries(map)
    .map(([provider, s]) => ({
      provider, calls: s.calls, tokens: s.tokens,
      avgLatency: s.calls > 0 ? Math.round(s.latencySum / s.calls) : 0,
    }))
    .sort((a, b) => b.calls - a.calls)
}

function timeAgo(ts: string | number): string {
  const now = Date.now()
  const t = typeof ts === 'number' ? ts * 1000 : new Date(ts).getTime()
  const s = Math.floor((now - t) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

// ── Kanban board from Redis pending ──────────────────────────────────────────

const KANBAN_COLS = [
  { id: 'redacted-chan', label: 'chan ⬡', color: 'text-violet-400' },
  { id: 'hermes',        label: 'hermes ⚡', color: 'text-cyan-400' },
  { id: 'smolting',      label: 'smolting 🌱', color: 'text-emerald-400' },
  { id: 'builder',       label: 'builder 🔧', color: 'text-amber-400' },
]

function KanbanBoard() {
  const { data, isLoading } = useQuery({
    queryKey: ['swarm-pending'],
    queryFn: apiGetSwarmPending,
    refetchInterval: 10_000,
  })

  const pending = data?.pending ?? {}
  const hasAny = Object.values(pending).some((v) => (v?.count ?? 0) > 0)

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {KANBAN_COLS.map((col) => {
        const entry = pending[col.id]
        const items = entry?.items ?? []
        const count = entry?.count ?? 0
        return (
          <div
            key={col.id}
            className={cn('rounded-xl border p-3 min-h-[120px]', AGENT_COLORS[col.id] ?? 'border-border bg-card/50')}
          >
            <div className="flex items-center justify-between mb-2">
              <span className={cn('text-[11px] font-semibold tracking-wide', col.color)}>{col.label}</span>
              {count > 0 && (
                <span className="text-[10px] bg-secondary border border-border rounded-full px-1.5 py-0.5 text-muted-foreground">
                  {count}
                </span>
              )}
            </div>
            {isLoading ? (
              <div className="space-y-1.5 animate-pulse">
                <div className="h-8 rounded bg-secondary" />
                <div className="h-8 rounded bg-secondary" />
              </div>
            ) : items.length === 0 ? (
              <p className="text-[10px] text-muted-foreground/40 italic mt-2">no pending tasks</p>
            ) : (
              <div className="space-y-1.5">
                {items.slice(0, 4).map((item, i) => {
                  const content = typeof item.content === 'string'
                    ? item.content.slice(0, 60)
                    : JSON.stringify(item).slice(0, 60)
                  const from = item.from as string | undefined
                  return (
                    <div key={i} className="text-[10px] bg-secondary/60 rounded px-2 py-1.5 leading-relaxed">
                      {from && <span className="text-primary/70 mr-1">{from}:</span>}
                      <span className="text-foreground/70">{content}{content.length === 60 ? '…' : ''}</span>
                    </div>
                  )
                })}
                {items.length > 4 && (
                  <p className="text-[9px] text-muted-foreground/50 text-right">+{items.length - 4} more</p>
                )}
              </div>
            )}
          </div>
        )
      })}
      {!isLoading && !hasAny && (
        <div className="col-span-4 text-center py-4 text-xs text-muted-foreground/50">
          All queues empty — swarm is idle
        </div>
      )}
    </div>
  )
}

// ── Swarm activity feed ───────────────────────────────────────────────────────

const MSG_TYPE_BADGE: Record<string, string> = {
  task:    'bg-cyan-500/15 text-cyan-300 border-cyan-500/20',
  result:  'bg-emerald-500/15 text-emerald-300 border-emerald-500/20',
  whisper: 'bg-violet-500/15 text-violet-300 border-violet-500/20',
  error:   'bg-red-500/15 text-red-300 border-red-500/20',
}

function ActivityFeed() {
  const { data, isLoading } = useQuery({
    queryKey: ['swarm-activity'],
    queryFn: () => apiGetSwarmActivity(40),
    refetchInterval: 15_000,
  })

  const messages: SwarmMessage[] = data?.messages ?? []

  return (
    <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
      {isLoading && (
        <div className="space-y-1.5 animate-pulse">
          {[1, 2, 3].map((i) => <div key={i} className="h-10 rounded-lg bg-secondary" />)}
        </div>
      )}
      {!isLoading && messages.length === 0 && (
        <p className="text-sm text-muted-foreground/50 italic text-center py-6">No recent swarm activity</p>
      )}
      {messages.map((msg, i) => (
        <div key={i} className="flex items-start gap-2 text-[11px] bg-secondary/40 rounded-lg px-2.5 py-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              {msg.from && <span className="text-primary/80 font-medium">{msg.from}</span>}
              {msg.to && <span className="text-muted-foreground">→ {msg.to}</span>}
              {msg.type && (
                <span className={cn('text-[9px] px-1 py-0.5 rounded border', MSG_TYPE_BADGE[msg.type] ?? 'bg-secondary border-border text-muted-foreground')}>
                  {msg.type}
                </span>
              )}
              {msg.ts && <span className="text-muted-foreground/50 ml-auto">{timeAgo(msg.ts)}</span>}
            </div>
            {msg.content && (
              <p className="text-foreground/60 mt-0.5 truncate">{String(msg.content).slice(0, 120)}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Main dashboard ─────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const mood  = useQuery({ queryKey: ['mood'],       queryFn: apiGetMood,                 refetchInterval: 30_000 })
  const facts = useQuery({ queryKey: ['facts'],      queryFn: apiGetFacts,                refetchInterval: 60_000 })
  const logs  = useQuery({ queryKey: ['proxy-logs'], queryFn: apiGetProxyLogs,            refetchInterval: 30_000 })
  const vault = useQuery({ queryKey: ['vault'],      queryFn: () => apiGetVault(30),      refetchInterval: 120_000 })

  const proxyData = logs.data?.logs ?? logs.data?.entries ?? []
  const providerStats = useMemo(() => computeProviderStats(proxyData ?? []), [proxyData])
  const totalCalls  = providerStats.reduce((s, p) => s + p.calls,  0)
  const totalTokens = providerStats.reduce((s, p) => s + p.tokens, 0)

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-6">
          <Activity size={18} className="text-primary" />
          <h1 className="text-base font-semibold text-foreground">Swarm Dashboard</h1>
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-muted-foreground">Live · auto-refresh</span>
        </div>

        <motion.div variants={STAGGER} initial="hidden" animate="show" className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* Agent heartbeats */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<Zap size={14} />} title="Agent Heartbeats">
              <AgentGrid />
            </SectionCard>
          </motion.div>

          {/* Kanban */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<Inbox size={14} />} title="Task Queue — Swarm Inbox">
              <KanbanBoard />
            </SectionCard>
          </motion.div>

          {/* Swarm activity */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<GitBranch size={14} />} title="Swarm Activity Feed">
              <ActivityFeed />
            </SectionCard>
          </motion.div>

          {/* Chan state */}
          <motion.div variants={ITEM}>
            <SectionCard icon={<Brain size={14} />} title="Chan State">
              <MoodPanel data={mood.data} loading={mood.isLoading} />
            </SectionCard>
          </motion.div>

          {/* Facts */}
          <motion.div variants={ITEM}>
            <SectionCard icon={<Brain size={14} />} title="Active Facts">
              <FactsList data={facts.data?.facts} loading={facts.isLoading} />
            </SectionCard>
          </motion.div>

          {/* Token / provider summary */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard
              icon={<BarChart2 size={14} />}
              title={`Proxy Usage · ${totalCalls.toLocaleString()} calls · ${totalTokens.toLocaleString()} tokens`}
            >
              {logs.isLoading ? (
                <div className="flex gap-3 animate-pulse">
                  {[1, 2, 3].map((i) => <div key={i} className="h-16 flex-1 rounded-lg bg-secondary" />)}
                </div>
              ) : providerStats.length === 0 ? (
                <p className="text-sm text-muted-foreground">No proxy data yet</p>
              ) : (
                <div className="space-y-3">
                  <div className="flex gap-1.5 h-6 rounded-lg overflow-hidden">
                    {providerStats.map((p) => {
                      const pct = totalCalls > 0 ? (p.calls / totalCalls) * 100 : 0
                      const colorClass = PROVIDER_COLORS[p.provider]
                      return (
                        <div
                          key={p.provider}
                          className={cn('transition-all', colorClass?.split(' ')[0])}
                          style={{ width: `${pct}%`, minWidth: pct > 0 ? '2px' : '0' }}
                          title={`${p.provider}: ${p.calls} calls`}
                        />
                      )
                    })}
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {providerStats.map((p) => {
                      const colorClass = PROVIDER_COLORS[p.provider] ?? 'bg-secondary text-muted-foreground border-border'
                      const pct = totalCalls > 0 ? ((p.calls / totalCalls) * 100).toFixed(0) : '0'
                      return (
                        <div key={p.provider} className={cn('rounded-lg border px-3 py-2', colorClass)}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[11px] font-medium capitalize">{p.provider}</span>
                            <span className="text-[10px] opacity-70">{pct}%</span>
                          </div>
                          <p className="text-sm font-mono font-medium">{p.calls.toLocaleString()}</p>
                          <p className="text-[10px] opacity-60">{p.tokens.toLocaleString()} tok · {p.avgLatency}ms avg</p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </SectionCard>
          </motion.div>

          {/* Vault */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<BookHeart size={14} />} title="Memory Vault">
              <VaultPanel data={vault.data?.entries} loading={vault.isLoading} />
            </SectionCard>
          </motion.div>

          {/* Proxy logs */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<Shield size={14} />} title={`Proxy Activity${proxyData.length ? ` · ${proxyData.length} entries` : ''}`}>
              <ProxyTable data={proxyData} loading={logs.isLoading} />
            </SectionCard>
          </motion.div>

        </motion.div>
      </div>
    </div>
  )
}

function SectionCard({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}
