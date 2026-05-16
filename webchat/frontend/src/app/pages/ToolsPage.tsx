import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Wrench, CheckCircle2, XCircle, Clock, AlertTriangle, Inbox } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/app/lib/utils'
import { apiGetSwarmPending } from '@/app/lib/api'
import type { SwarmMessage } from '@/app/types'

interface PendingTool {
  id: string
  name: string
  description?: string
  args?: Record<string, unknown>
  requested_at: string
  agent?: string
}

async function fetchPending(): Promise<{ pending: PendingTool[] }> {
  const res = await fetch('/api/tools/pending', {
    headers: { Authorization: `Bearer ${localStorage.getItem('rc_token') ?? ''}` },
  })
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

async function decideTools(body: { tool_id: string; approved: boolean; reason?: string }) {
  const res = await fetch('/api/tools/decide', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('rc_token') ?? ''}`,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed')
}

const CATALOG = [
  { id: 'web_fetch',     name: 'web_fetch',     agent: 'hermes',  icon: '🌐', description: 'Fetch and parse URLs (SSRF-guarded)' },
  { id: 'web_search',    name: 'web_search',    agent: 'hermes',  icon: '🔍', description: 'DuckDuckGo search via lite API' },
  { id: 'python_exec',   name: 'python_exec',   agent: 'hermes',  icon: '🐍', description: 'Sandboxed Python execution (EXEC_ENABLED)' },
  { id: 'skill_recall',  name: 'skill_recall',  agent: 'hermes',  icon: '🧠', description: 'Recall stored skill solutions by keyword' },
  { id: 'railway_deploy',name: 'railway_deploy',agent: 'hermes',  icon: '🚂', description: 'Deploy or query Railway services' },
  { id: 'redis_pub',     name: 'redis_pub',     agent: 'runtime', icon: '📨', description: 'Publish to SwarmInbox for agent routing' },
]

export default function ToolsPage() {
  const qc = useQueryClient()
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['tools-pending'],
    queryFn: fetchPending,
    refetchInterval: 5_000,
  })
  const { data: swarmData } = useQuery({
    queryKey: ['swarm-pending'],
    queryFn: apiGetSwarmPending,
    refetchInterval: 10_000,
  })

  const decide = useMutation({
    mutationFn: decideTools,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tools-pending'] })
      refetch()
    },
  })

  const pending = data?.pending ?? []
  const hermesPending = swarmData?.pending?.hermes ?? { count: 0, items: [] }

  async function approve(tool: PendingTool) {
    try {
      await decide.mutateAsync({ tool_id: tool.id, approved: true })
      toast.success(`Approved: ${tool.name}`)
    } catch {
      toast.error('Failed to approve')
    }
  }

  async function reject(tool: PendingTool) {
    try {
      await decide.mutateAsync({ tool_id: tool.id, approved: false, reason: 'Rejected by user' })
      toast.success(`Rejected: ${tool.name}`)
    } catch {
      toast.error('Failed to reject')
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-6">
          <Wrench size={18} className="text-primary" />
          <h1 className="text-base font-semibold text-foreground">Tools</h1>
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-muted-foreground">Auto-refreshes every 5–10s</span>
        </div>

        {/* HITL Approval Queue */}
        <Section title="Pending Approval" icon={<AlertTriangle size={14} className="text-amber-400" />}>
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2].map((i) => <div key={i} className="h-20 rounded-xl bg-secondary animate-pulse" />)}
            </div>
          ) : pending.length === 0 ? (
            <div className="flex items-center gap-2 py-6 justify-center">
              <CheckCircle2 size={16} className="text-emerald-500" />
              <p className="text-sm text-muted-foreground">No tools awaiting approval</p>
            </div>
          ) : (
            <div className="space-y-3">
              <AnimatePresence>
                {pending.map((tool) => (
                  <motion.div
                    key={tool.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                    className="bg-card border border-amber-500/20 rounded-xl p-4"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
                        <AlertTriangle size={14} className="text-amber-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-mono font-medium text-foreground">{tool.name}</p>
                          {tool.agent && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-secondary border border-border rounded text-muted-foreground">
                              {tool.agent}
                            </span>
                          )}
                          <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                            <Clock size={10} /> {new Date(tool.requested_at).toLocaleTimeString()}
                          </span>
                        </div>
                        {tool.description && (
                          <p className="text-xs text-muted-foreground mt-1">{tool.description}</p>
                        )}
                        {tool.args && Object.keys(tool.args).length > 0 && (
                          <pre className="mt-2 text-xs font-mono bg-secondary rounded-lg p-2 overflow-x-auto text-muted-foreground">
                            {JSON.stringify(tool.args, null, 2)}
                          </pre>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2 mt-3 ml-11">
                      <button
                        onClick={() => approve(tool)}
                        disabled={decide.isPending}
                        className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-colors"
                      >
                        <CheckCircle2 size={13} /> Approve
                      </button>
                      <button
                        onClick={() => reject(tool)}
                        disabled={decide.isPending}
                        className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-medium hover:bg-red-500/20 transition-colors"
                      >
                        <XCircle size={13} /> Reject
                      </button>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </Section>

        {/* Hermes Inbox (Redis swarm:pending:hermes) */}
        <Section
          title={`Hermes Inbox${hermesPending.count > 0 ? ` · ${hermesPending.count}` : ''}`}
          icon={<Inbox size={14} className={hermesPending.count > 0 ? 'text-cyan-400' : 'text-muted-foreground'} />}
          className="mt-4"
        >
          {hermesPending.count === 0 ? (
            <div className="flex items-center gap-2 py-4 justify-center">
              <CheckCircle2 size={14} className="text-emerald-500" />
              <p className="text-sm text-muted-foreground">Hermes inbox is empty</p>
            </div>
          ) : (
            <div className="space-y-2">
              {hermesPending.items.map((item: SwarmMessage, i: number) => {
                const content = typeof item.content === 'string'
                  ? item.content
                  : JSON.stringify(item.content ?? item)
                return (
                  <div key={i} className="bg-secondary/40 border border-border rounded-lg p-3 text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      {item.from && (
                        <span className="text-cyan-400 font-medium">{item.from}</span>
                      )}
                      {item.type && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border bg-secondary text-muted-foreground border-border">
                          {item.type}
                        </span>
                      )}
                      {item.ts && (
                        <span className="text-muted-foreground/50 text-[10px] ml-auto">
                          {new Date(typeof item.ts === 'number' ? item.ts * 1000 : item.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                    <p className="text-foreground/70 leading-relaxed line-clamp-3">{content.slice(0, 300)}</p>
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        {/* Tool Catalog */}
        <Section title="Tool Catalog" icon={<Wrench size={14} className="text-muted-foreground" />} className="mt-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {CATALOG.map((tool, i) => (
              <motion.div
                key={tool.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
                className="flex items-start gap-3 bg-card border border-border rounded-xl p-3"
              >
                <span className="text-xl shrink-0">{tool.icon}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-mono font-medium text-foreground">{tool.name}</p>
                    <span className="text-[10px] px-1.5 py-0.5 bg-secondary border border-border rounded text-muted-foreground">
                      {tool.agent}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{tool.description}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  )
}

function Section({
  title, icon, children, className,
}: {
  title: string; icon: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <div className={cn('bg-card border border-border rounded-xl overflow-hidden', className)}>
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <span>{icon}</span>
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}
