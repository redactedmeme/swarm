import { useQuery } from '@tanstack/react-query'
import { apiGetHeartbeats } from '@/app/lib/api'
import { cn } from '@/app/lib/utils'

const AGENT_ICONS: Record<string, string> = {
  'redacted-chan': '⬡',
  hermes: '⚡',
  smolting: '🌱',
  builder: '🔧',
  runtime: '⚙',
}

function formatAge(age_s: number | null): string {
  if (age_s == null) return 'never'
  if (age_s < 60) return `${age_s}s ago`
  if (age_s < 3600) return `${Math.floor(age_s / 60)}m ago`
  return `${Math.floor(age_s / 3600)}h ago`
}

export default function AgentGrid() {
  const { data, isLoading } = useQuery({
    queryKey: ['heartbeats'],
    queryFn: apiGetHeartbeats,
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 animate-pulse">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg bg-secondary" />
        ))}
      </div>
    )
  }

  const agents = data?.agents ?? []

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
      {agents.map((agent) => {
        const icon = AGENT_ICONS[agent.id] ?? '●'
        return (
          <div
            key={agent.id}
            className="flex flex-col items-center gap-1.5 bg-secondary/50 rounded-lg p-2.5 border border-border"
          >
            <div className="relative">
              <div className="w-9 h-9 rounded-full bg-card border border-border flex items-center justify-center text-base">
                {icon}
              </div>
              <span
                className={cn(
                  'absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-background',
                  agent.online ? 'bg-emerald-500' : 'bg-zinc-500',
                )}
              />
            </div>
            <div className="text-center w-full">
              <p className="text-[11px] font-medium text-foreground truncate">{agent.label}</p>
              <p className={cn('text-[9px]', agent.online ? 'text-emerald-500' : 'text-muted-foreground')}>
                {agent.online ? formatAge(agent.age_s) : 'offline'}
              </p>
              <p className="text-[9px] text-muted-foreground/60 truncate font-mono mt-0.5">{agent.llm}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
