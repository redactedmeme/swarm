import { useQuery } from '@tanstack/react-query'
import { Command } from 'lucide-react'
import { apiGetMood } from '@/app/lib/api'
import { cn } from '@/app/lib/utils'

export type ChatAgent = 'chan' | 'hermes' | 'smolting' | 'builder'

const AGENTS: { id: ChatAgent; label: string; icon: string; available: boolean; llm: string }[] = [
  { id: 'chan',     label: 'redacted-chan', icon: '⬡',  available: true,  llm: 'gemma-4-uncensored' },
  { id: 'hermes',  label: 'hermes-bot',    icon: '⚡', available: true,  llm: 'openai/gpt-oss-120b' },
  { id: 'smolting',label: 'smolting',       icon: '🌱', available: true,  llm: 'llama-3.1-8b'       },
  { id: 'builder', label: 'builder',        icon: '🔧', available: true,  llm: 'claude-haiku-4-5'  },
]

interface Props {
  onPaletteOpen?: () => void
  selectedAgent: ChatAgent
  onSelectAgent: (agent: ChatAgent) => void
}

export default function ChanHeader({ onPaletteOpen, selectedAgent, onSelectAgent }: Props) {
  const { data } = useQuery({ queryKey: ['mood'], queryFn: apiGetMood, refetchInterval: 60_000 })

  const active = AGENTS.find((a) => a.id === selectedAgent) ?? AGENTS[0]

  return (
    <div className="shrink-0 border-b border-border bg-card/50">
      {/* Agent tab row */}
      <div className="flex items-center gap-1 px-3 pt-2 pb-0">
        {AGENTS.map((agent) => (
          <button
            key={agent.id}
            onClick={() => agent.available && onSelectAgent(agent.id)}
            title={agent.available ? agent.label : `${agent.label} — not available for web chat`}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1.5 rounded-t-lg text-xs font-medium transition-all border-b-2',
              selectedAgent === agent.id
                ? 'bg-card border-primary text-foreground'
                : agent.available
                  ? 'border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50 cursor-pointer'
                  : 'border-transparent text-muted-foreground/30 cursor-not-allowed',
            )}
          >
            <span className="text-sm leading-none">{agent.icon}</span>
            <span className="hidden sm:inline">{agent.label}</span>
            {!agent.available && (
              <span className="text-[9px] opacity-50">—</span>
            )}
          </button>
        ))}
        <div className="flex-1" />
        {onPaletteOpen && (
          <button
            onClick={onPaletteOpen}
            className="flex items-center gap-1 px-2 py-1 mb-1 rounded border border-border text-muted-foreground hover:text-foreground hover:bg-secondary text-xs transition-all"
            title="Command palette (⌘K)"
          >
            <Command size={11} />
            <span className="font-mono text-[10px]">K</span>
          </button>
        )}
      </div>

      {/* Active agent info bar */}
      <div className="flex items-center gap-3 px-4 py-2">
        <div className="relative">
          <div className="w-7 h-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-sm">
            {active.icon}
          </div>
          <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500 border-2 border-background" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-foreground">{active.label}</p>
          {active.id === 'chan' && data ? (
            <p className="text-[10px] text-muted-foreground truncate">
              {data.mood} · φ {data.phi?.toFixed(2) ?? '—'} · <span className="font-mono">{active.llm}</span>
            </p>
          ) : (
            <p className="text-[10px] text-muted-foreground font-mono">{active.llm}</p>
          )}
        </div>
        {active.id === 'hermes' && (
          <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-1.5 py-0.5">
            async · up to 60s
          </span>
        )}
      </div>
    </div>
  )
}
