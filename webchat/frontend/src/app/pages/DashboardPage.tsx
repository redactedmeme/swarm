import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Activity, Brain, Zap, Shield, BookHeart } from 'lucide-react'
import { apiGetMood, apiGetFacts, apiGetProxyLogs, apiGetVault } from '@/app/lib/api'
import AgentGrid from '@/app/components/Dashboard/AgentGrid'
import MoodPanel from '@/app/components/Dashboard/MoodPanel'
import FactsList from '@/app/components/Dashboard/FactsList'
import ProxyTable from '@/app/components/Dashboard/ProxyTable'
import VaultPanel from '@/app/components/Dashboard/VaultPanel'

const STAGGER = { hidden: {}, show: { transition: { staggerChildren: 0.07 } } }
const ITEM = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
}

export default function DashboardPage() {
  const mood = useQuery({ queryKey: ['mood'], queryFn: apiGetMood, refetchInterval: 30_000 })
  const facts = useQuery({ queryKey: ['facts'], queryFn: apiGetFacts, refetchInterval: 60_000 })
  const logs = useQuery({ queryKey: ['proxy-logs'], queryFn: apiGetProxyLogs, refetchInterval: 30_000 })
  const vault = useQuery({ queryKey: ['vault'], queryFn: () => apiGetVault(30), refetchInterval: 120_000 })

  // proxy logs endpoint may return { logs: [...] } or { entries: [...] }
  const proxyData = logs.data?.logs ?? (logs.data as { entries?: typeof logs.data.logs })?.entries

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

        <motion.div
          variants={STAGGER}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          {/* Agent heartbeats — full width */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<Zap size={14} />} title="Agent Heartbeats">
              <AgentGrid />
            </SectionCard>
          </motion.div>

          {/* Chan state — compact */}
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

          {/* Vault — full width */}
          <motion.div variants={ITEM} className="md:col-span-2">
            <SectionCard icon={<BookHeart size={14} />} title="Memory Vault">
              <VaultPanel data={vault.data?.entries} loading={vault.isLoading} />
            </SectionCard>
          </motion.div>

          {/* Proxy logs — full width */}
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
