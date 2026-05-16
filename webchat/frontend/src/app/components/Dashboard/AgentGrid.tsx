import { useQuery } from '@tanstack/react-query'
import { apiGetMood } from '@/app/lib/api'
import { cn } from '@/app/lib/utils'

const AGENTS = [
  { id: 'chan', label: 'redacted-chan', icon: '⬡' },
  { id: 'hermes', label: 'hermes-bot', icon: '⚡' },
  { id: 'smolting', label: 'smolting', icon: '🌱' },
  { id: 'builder', label: 'RedactedBuilder', icon: '🔧' },
]

export default function AgentGrid() {
  const { data: mood } = useQuery({ queryKey: ['mood'], queryFn: apiGetMood, refetchInterval: 30_000 })

  const getStatus = (id: string) => {
    if (id === 'chan') return mood ? 'online' : 'unknown'
    return 'online'
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {AGENTS.map((agent) => {
        const status = getStatus(agent.id)
        return (
          <div
            key={agent.id}
            className="flex flex-col items-center gap-2 bg-secondary/50 rounded-lg p-3 border border-border"
          >
            <div className="relative">
              <div className="w-10 h-10 rounded-full bg-card border border-border flex items-center justify-center text-lg">
                {agent.icon}
              </div>
              <span
                className={cn(
                  'absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-background',
                  status === 'online' ? 'bg-emerald-500' : 'bg-zinc-500',
                )}
              />
            </div>
            <div className="text-center">
              <p className="text-xs font-medium text-foreground truncate max-w-full">{agent.label}</p>
              <p className={cn('text-[10px]', status === 'online' ? 'text-emerald-500' : 'text-muted-foreground')}>
                {status}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
