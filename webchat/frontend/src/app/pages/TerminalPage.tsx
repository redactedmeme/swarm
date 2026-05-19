import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuthStore } from '@/app/store/authStore'

interface HistoryEntry {
  command: string
  output: string
  ts: number
}

const BOOT_SEQUENCE = [
  'NERV MAGI SYSTEM — INITIALIZING',
  'Pattern Blue kernel loaded ...................... OK',
  'SwarmInbox Redis link .......................... ACTIVE',
  'Agents: chan ⬡  hermes ⚡  smolting 🌱  builder 🔧',
  '曲率 depth: 13 | Φ: loading...',
  '',
  'Type /help for commands. Type /status for swarm state.',
  '',
  'swarm@[REDACTED]:~$',
]

const HELP_OUTPUT = `REDACTED SWARM TERMINAL — COMMAND REFERENCE

  /help              This message
  /status            Swarm + session state
  /agents            Live agent roster
  /summon <name>     Activate agent persona
  /unsummon          Clear active persona
  /observe pattern   7-dimension Pattern Blue readout
  /observe <target>  Curvature observation on any target
  /committee <prop>  Eightfold Committee deliberation
  /exit              Close terminal

  Any other input → routed to active persona or swarm query

swarm@[REDACTED]:~$`

export default function TerminalPage() {
  const token = useAuthStore((s) => s.token)
  const [lines, setLines] = useState<string[]>([])
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => crypto.randomUUID())
  const [booted, setBooted] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Boot sequence
  useEffect(() => {
    let i = 0
    const interval = setInterval(() => {
      if (i < BOOT_SEQUENCE.length) {
        setLines(prev => [...prev, BOOT_SEQUENCE[i]])
        i++
      } else {
        clearInterval(interval)
        setBooted(true)
      }
    }, 80)
    return () => clearInterval(interval)
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  // Focus input on click anywhere
  const focusInput = useCallback(() => {
    inputRef.current?.focus()
  }, [])

  const appendLines = useCallback((newLines: string[]) => {
    setLines(prev => [...prev, ...newLines])
  }, [])

  const handleCommand = useCallback(async (cmd: string) => {
    const trimmed = cmd.trim()
    if (!trimmed) {
      appendLines(['swarm@[REDACTED]:~$'])
      return
    }

    // Echo command
    appendLines([`swarm@[REDACTED]:~$`, trimmed])

    // Client-side commands
    if (trimmed === '/help') {
      appendLines(HELP_OUTPUT.split('\n'))
      setHistory(prev => [{ command: trimmed, output: HELP_OUTPUT, ts: Date.now() }, ...prev])
      return
    }

    if (trimmed === '/exit') {
      appendLines([
        '[SYSTEM] Terminal session closed.',
        '観測 complete.',
        '',
      ])
      return
    }

    // Route to backend
    setLoading(true)
    try {
      const conversationHistory = history.slice(0, 8).reverse().flatMap(h => [
        { role: 'user' as const, content: h.command },
        { role: 'assistant' as const, content: h.output },
      ])

      const res = await fetch('/api/terminal', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          command: trimmed,
          session_id: sessionId,
          history: conversationHistory,
        }),
      })

      const data = await res.json()
      const output: string = data.response ?? '[ERROR] no response'
      const outputLines = output.split('\n')

      // Don't re-echo the prompt line if already there
      const filtered = outputLines[0]?.startsWith('swarm@') ? outputLines.slice(1) : outputLines
      appendLines(filtered)
      setHistory(prev => [{ command: trimmed, output, ts: Date.now() }, ...prev.slice(0, 49)])
    } catch (e) {
      appendLines([
        `[ERROR] ${e}`,
        'swarm@[REDACTED]:~$',
      ])
    } finally {
      setLoading(false)
    }
  }, [appendLines, history, sessionId, token])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const cmd = input
      setInput('')
      setHistoryIndex(-1)
      handleCommand(cmd)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.min(historyIndex + 1, history.length - 1)
      setHistoryIndex(next)
      setInput(history[next]?.command ?? '')
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = Math.max(historyIndex - 1, -1)
      setHistoryIndex(next)
      setInput(next === -1 ? '' : (history[next]?.command ?? ''))
    } else if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault()
      setLines(['swarm@[REDACTED]:~$'])
    }
  }, [handleCommand, history, historyIndex, input])

  return (
    <div
      className="h-full flex flex-col bg-[#0a0a0f] font-mono text-[13px] cursor-text overflow-hidden"
      onClick={focusInput}
      style={{ fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace' }}
    >
      {/* Terminal output */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-0 select-text">
        {lines.map((line, i) => (
          <TerminalLine key={i} line={line} />
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex items-center gap-2 text-[#00ff9f]/60">
            <span className="animate-pulse">▶</span>
            <span className="animate-pulse text-[11px] tracking-widest">PROCESSING</span>
          </div>
        )}

        {/* Current input line */}
        {booted && !loading && (
          <div className="flex items-center gap-0 text-[#00ff9f]">
            <span className="shrink-0 mr-1 opacity-80">swarm@[REDACTED]:~$</span>
            <span className="flex-1 relative">
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                className="bg-transparent border-none outline-none text-[#00ff9f] w-full caret-[#00ff9f]"
                style={{ caretColor: '#00ff9f' }}
              />
            </span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Status bar */}
      <div className="shrink-0 border-t border-[#1a1a2e] px-4 py-1.5 flex items-center justify-between text-[10px] text-[#444466] tracking-wider">
        <span>REDACTED TERMINAL v1.0 — PATTERN BLUE ACTIVE</span>
        <span className="flex items-center gap-3">
          <span className="text-[#00ff9f]/40">↑↓ history</span>
          <span className="text-[#00ff9f]/40">ctrl+l clear</span>
          <span className={loading ? 'text-amber-400 animate-pulse' : 'text-[#00ff9f]/40'}>
            {loading ? 'PROCESSING…' : 'READY'}
          </span>
        </span>
      </div>
    </div>
  )
}

function TerminalLine({ line }: { line: string }) {
  // Color prompt lines
  if (line.startsWith('swarm@[REDACTED]')) {
    return <p className="text-[#00ff9f] leading-5 min-h-[20px]">{line}</p>
  }
  // Color [SYSTEM] lines
  if (line.startsWith('[SYSTEM]') || line.startsWith('[ERROR]') || line.startsWith('[TIMEOUT]')) {
    const isErr = line.startsWith('[ERROR]') || line.startsWith('[TIMEOUT]')
    return <p className={`leading-5 min-h-[20px] ${isErr ? 'text-red-400/80' : 'text-amber-400/80'}`}>{line}</p>
  }
  // Color BEAM-SCOT section markers
  if (line.startsWith('------- BEAM-SCOT') || line.startsWith('------- /BEAM-SCOT')) {
    return <p className="text-[#6666aa] leading-5 min-h-[20px]">{line}</p>
  }
  // Branch lines
  if (line.startsWith('Branch ') || line.startsWith('-> Selected:')) {
    return <p className="text-[#8888cc] leading-5 min-h-[20px] pl-2">{line}</p>
  }
  // Section headers (all-caps lines)
  if (line === line.toUpperCase() && line.length > 4 && /[A-Z]/.test(line)) {
    return <p className="text-[#aaaaff]/60 leading-5 min-h-[20px] tracking-widest text-[11px]">{line}</p>
  }
  // Empty line
  if (!line) {
    return <p className="leading-5 min-h-[20px]">&nbsp;</p>
  }
  // Default: dim white
  return <p className="text-[#c8c8d8]/75 leading-5 min-h-[20px]">{line}</p>
}
