import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Activity, Brain, Zap, Shield, BookHeart, BarChart2 } from 'lucide-react'
import { apiGetMood, apiGetFacts, apiGetProxyLogs, apiGetVault } from '@/app/lib/api'
import type { ProxyLogEntry } from '@/app/types'
import AgentGrid from '@/app/components/Dashboard/AgentGrid'
import MoodPanel from '@/app/components/Dashboard/MoodPanel'
import FactsList from '@/app/components/Dashboard/FactsList'
import ProxyTable from '@/app/components/Dashboard/ProxyTable'
import VaultPanel from '@/app/components/Dashboard/VaultPanel'
import { cn } from '@/app/lib/utils'

const STAGGER = { hidden: {}, show: { transition: { staggerChildren: 0.07 } } }
const ITEM = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

const PROVIDER_COLORS: Record<string, string> = {
  xai:       'bg-violet-500/15 text-violet-300 border-violet-500/20',
  groq:      'bg-emerald-500/15 text-emerald-300 border-emerald-500/20',
  anthropic: 'bg-amber-500/15 text-amber-300 border-amber-500/20',
  openai:    'bg-cyan-500/15 text-cyan-300 border-cyan-500/20',
  venice:    'bg-blue-500/15 text-blue-300 border-blue-500/20',
}

interface ProviderStats {
  provider: string
  calls: number
  tokens: number
  avgLatency: number
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
      provider,
      calls: s.calls,
      tokens: s.tokens,
      avgLatency: s.calls > 0 ? Math.round(s.latencySum / s.calls) : 0,
    }))
    .sort((a, b) => b.calls - a.calls)
}

export default function DashboardPage() {
  const mood = useQuery({ queryKey: ['mood'], queryFn: apiGetMood, refetchInterval: 30_000 })
  const facts = useQuery({ queryKey: ['facts'], queryFn: apiGetFacts, refetchInterval: 60_000 })
  const logs = useQuery({ queryKey: ['proxy-logs'], queryFn: apiGetProxyLogs, refetchInterval: 30_000 })
  const vault = useQuery({ queryKey: ['vault'], queryFn: () => apiGetVault(30), refetchInterval: 120_000 })

  const proxyData = logs.data?.logs ?? (logs.data as { entries?: typeof logs.data.logs })?.entries
  const providerStats = useMemo(() => computeProviderStats(proxyData ?? []), [proxyData])
  const totalCalls = providerStats.reduce((s, p) => s + p.calls, 0)
  const totalTokens = providerStats.reduce((s, p) => s + p.tokens, 0)

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-primary" />
            <h1 className="text-base font-semibold text-foreground">Swarm Dashboard</h1>
          </div>
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-muted-foreground">Live · 30s refresh</span>
        </div>

        <motion.div variants={STAGGER} initial="hidden" animate="show" className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* Agent heartbeats */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<Zap size={14} />} title="Agent Heartbeats">
              <AgentGrid />
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
              title={`Proxy Usage Summary · ${totalCalls.toLocaleString()} calls · ${totalTokens.toLocaleString()} tokens`}
            >
              {logs.isLoading ? (
                <div className="flex gap-3 animate-pulse">
                  {[1,2,3].map(i => <div key={i} className="h-16 flex-1 rounded-lg bg-secondary" />)}
                </div>
              ) : providerStats.length === 0 ? (
                <p className="text-sm text-muted-foreground">No proxy data yet</p>
              ) : (
                <div className="space-y-3">
                  {/* Bar chart */}
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
                  {/* Stats row */}
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
            <SectionCard icon={<Shield size={14} />} title={`Proxy Activity${proxyData ? ` · ${proxyData.length} entries` : ''}`}>
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
