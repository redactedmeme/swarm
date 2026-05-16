import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Bot, RefreshCw } from 'lucide-react'
import { cn } from '@/app/lib/utils'
import { apiGetSwarmPending } from '@/app/lib/api'
import SwarmFeed from '@/app/components/SwarmFeed'

interface Agent {
  id: string
  label: string
  icon: string
  role: string
  description: string
  llm?: string
  status: 'online' | 'offline' | 'unknown'
  last_seen: string | null
}

async function fetchAgents(): Promise<{ agents: Agent[] }> {
  const res = await fetch('/api/agents', {
    headers: { Authorization: `Bearer ${localStorage.getItem('rc_token') ?? ''}` },
  })
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

const ROLE_COLOR: Record<string, string> = {
  core:  'text-violet-400 bg-violet-500/10 border-violet-500/20',
  agent: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  infra: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
}

const STATUS_DOT: Record<string, string> = {
  online:  'bg-emerald-500',
  offline: 'bg-red-500',
  unknown: 'bg-zinc-500',
}

// Map agent.id from /api/agents → Redis agent key used in swarm:pending
const AGENT_REDIS_KEY: Record<string, string> = {
  chan:    'redacted-chan',
  hermes:  'hermes',
  smolting:'smolting',
  builder: 'builder',
  runtime: 'runtime',
}

export default function AgentsPage() {
  const [selected, setSelected] = useState<string | null>(null)
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
    refetchInterval: 30_000,
  })
  const { data: pendingData } = useQuery({
    queryKey: ['swarm-pending'],
    queryFn: apiGetSwarmPending,
    refetchInterval: 10_000,
  })

  const agents = data?.agents ?? []
  const pending = pendingData?.pending ?? {}

  function pendingCount(agentId: string): number {
    const key = AGENT_REDIS_KEY[agentId]
    return key ? (pending[key]?.count ?? 0) : 0
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Bot size={18} className="text-primary" />
          <h1 className="text-base font-semibold text-foreground">Swarm Agents</h1>
          <div className="h-px flex-1 bg-border" />
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        {isLoading ? (
          <AgentSkeleton />
        ) : (
          <>
            {/* Spatial canvas */}
            <div className="relative mb-4 bg-card/30 border border-border rounded-xl overflow-hidden" style={{ minHeight: 320 }}>
              <SpatialCanvas agents={agents} selected={selected} onSelect={setSelected} pendingCount={pendingCount} />
            </div>

            {/* Agent cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
              <AnimatePresence>
                {agents.map((agent, i) => {
                  const pc = pendingCount(agent.id)
                  return (
                    <motion.div
                      key={agent.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <AgentCard
                        agent={agent}
                        selected={selected === agent.id}
                        onSelect={() => setSelected((s) => s === agent.id ? null : agent.id)}
                        pendingCount={pc}
                        pendingItems={pending[AGENT_REDIS_KEY[agent.id] ?? '']?.items ?? []}
                      />
                    </motion.div>
                  )
                })}
              </AnimatePresence>
            </div>

            {/* Swarm message feed */}
            <SwarmFeed />
          </>
        )}
      </div>
    </div>
  )
}

// ── Spatial canvas ────────────────────────────────────────────────────────────

interface SpatialCanvasProps {
  agents: Agent[]
  selected: string | null
  onSelect: (id: string) => void
  pendingCount: (id: string) => number
}

const INITIAL_POSITIONS: Record<string, { x: number; y: number }> = {
  chan:     { x: 0.5,  y: 0.5  },
  hermes:   { x: 0.2,  y: 0.25 },
  smolting: { x: 0.75, y: 0.22 },
  builder:  { x: 0.15, y: 0.72 },
  proxy:    { x: 0.78, y: 0.68 },
  runtime:  { x: 0.5,  y: 0.85 },
}

function SpatialCanvas({ agents, selected, onSelect, pendingCount }: SpatialCanvasProps) {
  const canvasW = 600
  const canvasH = 300

  return (
    <svg viewBox={`0 0 ${canvasW} ${canvasH}`} className="w-full h-full" style={{ minHeight: 240 }}>
      <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
        <circle cx="15" cy="15" r="0.8" fill="hsl(240 6% 14%)" />
      </pattern>
      <rect width="100%" height="100%" fill="url(#grid)" />

      {/* Connection lines from chan */}
      {agents.map((agent) => {
        if (agent.id === 'chan') return null
        const from = INITIAL_POSITIONS['chan'] ?? { x: 0.5, y: 0.5 }
        const to = INITIAL_POSITIONS[agent.id] ?? { x: 0.5, y: 0.5 }
        const pc = pendingCount(agent.id)
        return (
          <motion.line
            key={`line-${agent.id}`}
            x1={from.x * canvasW} y1={from.y * canvasH}
            x2={to.x * canvasW}   y2={to.y * canvasH}
            stroke={pc > 0 ? 'hsl(190 80% 50% / 0.35)' : 'hsl(245 60% 60% / 0.15)'}
            strokeWidth={pc > 0 ? 1.5 : 1}
            strokeDasharray="4 4"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 1, delay: 0.3 }}
          />
        )
      })}

      {/* Agent nodes */}
      {agents.map((agent) => {
        const pos = INITIAL_POSITIONS[agent.id] ?? { x: 0.5, y: 0.5 }
        const cx = pos.x * canvasW
        const cy = pos.y * canvasH
        const isSelected = selected === agent.id
        const isOnline = agent.status === 'online'
        const pc = pendingCount(agent.id)

        return (
          <g key={agent.id} style={{ cursor: 'pointer' }} onClick={() => onSelect(agent.id)}>
            {isOnline && (
              <motion.circle
                cx={cx} cy={cy} r={20}
                fill="none"
                stroke="hsl(245 60% 60% / 0.3)"
                strokeWidth="1"
                animate={{ r: [18, 26, 18], opacity: [0.6, 0, 0.6] }}
                transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
              />
            )}
            <motion.circle
              cx={cx} cy={cy} r={18}
              fill={isSelected ? 'hsl(245 60% 60% / 0.25)' : 'hsl(240 8% 7%)'}
              stroke={isSelected ? 'hsl(245 60% 60%)' : 'hsl(240 6% 14%)'}
              strokeWidth={isSelected ? 1.5 : 1}
              animate={{ scale: isSelected ? 1.1 : 1 }}
              transition={{ type: 'spring', stiffness: 300 }}
            />
            {/* Status dot */}
            <circle
              cx={cx + 12} cy={cy - 12} r={4}
              fill={isOnline ? '#10b981' : agent.status === 'offline' ? '#ef4444' : '#71717a'}
              stroke="hsl(240 10% 4%)" strokeWidth="1.5"
            />
            {/* Pending badge */}
            {pc > 0 && (
              <g>
                <circle cx={cx - 12} cy={cy - 12} r={7} fill="hsl(190 80% 45%)" />
                <text x={cx - 12} y={cy - 9} textAnchor="middle" fontSize="8" fill="white" fontWeight="bold">
                  {pc > 9 ? '9+' : pc}
                </text>
              </g>
            )}
            <text x={cx} y={cy + 5} textAnchor="middle" fontSize="14" className="select-none">
              {agent.icon}
            </text>
            <text
              x={cx} y={cy + 30}
              textAnchor="middle" fontSize="9"
              fill={isSelected ? 'hsl(245 60% 75%)' : 'hsl(240 5% 55%)'}
              className="select-none font-medium"
            >
              {agent.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ── Agent card ────────────────────────────────────────────────────────────────

interface AgentCardProps {
  agent: Agent
  selected: boolean
  onSelect: () => void
  pendingCount: number
  pendingItems: Array<{ content?: string; type?: string; from?: string; [k: string]: unknown }>
}

function AgentCard({ agent, selected, onSelect, pendingCount: pc, pendingItems }: AgentCardProps) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        'rounded-xl border p-4 cursor-pointer transition-all duration-200',
        selected
          ? 'border-primary/50 bg-primary/5'
          : 'border-border bg-card hover:border-border/80 hover:bg-secondary/30',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="relative shrink-0">
          <div className="w-10 h-10 rounded-xl bg-secondary border border-border flex items-center justify-center text-lg">
            {agent.icon}
          </div>
          <span className={cn('absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-background', STATUS_DOT[agent.status])} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-foreground">{agent.label}</p>
            <span className={cn('text-[10px] px-1.5 py-0.5 rounded border font-medium', ROLE_COLOR[agent.role] ?? ROLE_COLOR.infra)}>
              {agent.role}
            </span>
            {pc > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/25 text-cyan-400 font-medium">
                {pc} pending
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{agent.description}</p>
          {agent.llm && agent.llm !== '—' && (
            <p className="text-[10px] font-mono text-muted-foreground/50 mt-0.5 truncate">{agent.llm}</p>
          )}
        </div>
      </div>

      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-border/50 space-y-2">
              <div className="flex items-center justify-between">
                <span className={cn(
                  'text-xs font-medium',
                  agent.status === 'online' ? 'text-emerald-400' : agent.status === 'offline' ? 'text-red-400' : 'text-zinc-400',
                )}>
                  {agent.status === 'online' ? '● Online' : agent.status === 'offline' ? '● Offline' : '● Unknown'}
                </span>
                {agent.last_seen && (
                  <span className="text-[10px] text-muted-foreground">{agent.last_seen}</span>
                )}
              </div>
              {/* Pending inbox preview */}
              {pendingItems.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Inbox ({pendingItems.length})</p>
                  {pendingItems.slice(0, 3).map((item, i) => {
                    const preview = typeof item.content === 'string'
                      ? item.content.slice(0, 80)
                      : JSON.stringify(item).slice(0, 80)
                    return (
                      <div key={i} className="text-[11px] text-foreground/60 bg-secondary/50 rounded px-2 py-1 truncate">
                        {item.from && <span className="text-cyan-400 mr-1">{item.from}:</span>}
                        {preview}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function AgentSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-24 rounded-xl bg-card border border-border animate-pulse" />
      ))}
    </div>
  )
}
