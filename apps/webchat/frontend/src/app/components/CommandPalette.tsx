import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, MessageCircle, LayoutDashboard, Bot, Wrench, Settings, Trash2, LogOut } from 'lucide-react'
import { cn } from '@/app/lib/utils'
import { useAuthStore } from '@/app/store/authStore'
import { useChatStore } from '@/app/store/chatStore'

interface PaletteItem {
  id: string
  label: string
  description?: string
  icon: React.ReactNode
  action: () => void
  group: string
  keywords?: string[]
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function CommandPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const inputRef = useRef<HTMLInputElement>(null)

  const ALL_ITEMS = useMemo<PaletteItem[]>(() => [
    {
      id: 'nav-chat', label: 'Go to Chat', icon: <MessageCircle size={15} />,
      action: () => navigate('/chat'), group: 'Navigation', keywords: ['chat', 'message'],
    },
    {
      id: 'nav-dashboard', label: 'Go to Dashboard', icon: <LayoutDashboard size={15} />,
      action: () => navigate('/dashboard'), group: 'Navigation', keywords: ['dashboard', 'status', 'swarm'],
    },
    {
      id: 'nav-agents', label: 'Go to Agents', icon: <Bot size={15} />,
      action: () => navigate('/agents'), group: 'Navigation', keywords: ['agents', 'hermes', 'smolting'],
    },
    {
      id: 'nav-tools', label: 'Go to Tools', icon: <Wrench size={15} />,
      action: () => navigate('/tools'), group: 'Navigation', keywords: ['tools', 'hitl', 'approval'],
    },
    {
      id: 'nav-settings', label: 'Go to Settings', icon: <Settings size={15} />,
      action: () => navigate('/settings'), group: 'Navigation', keywords: ['settings', 'privacy', 'proxy'],
    },
    {
      id: 'chat-clear', label: 'Clear Chat History', description: 'Remove all messages from this session',
      icon: <Trash2 size={15} />, action: () => clearMessages(), group: 'Chat', keywords: ['clear', 'delete', 'reset'],
    },
    {
      id: 'auth-logout', label: 'Log Out', description: 'End your session',
      icon: <LogOut size={15} />,
      action: () => { logout(); navigate('/login', { replace: true }) },
      group: 'Account', keywords: ['logout', 'signout', 'exit'],
    },
  ], [navigate, logout, clearMessages])

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim()
    if (!q) return ALL_ITEMS
    return ALL_ITEMS.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.description?.toLowerCase().includes(q) ||
        item.keywords?.some((k) => k.includes(q)),
    )
  }, [query, ALL_ITEMS])

  // Group items
  const grouped = useMemo(() => {
    const map = new Map<string, PaletteItem[]>()
    for (const item of filtered) {
      if (!map.has(item.group)) map.set(item.group, [])
      map.get(item.group)!.push(item)
    }
    return map
  }, [filtered])

  const flatFiltered = filtered

  useEffect(() => {
    if (open) {
      setQuery('')
      setCursor(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  useEffect(() => {
    setCursor(0)
  }, [query])

  function execute(item: PaletteItem) {
    item.action()
    onClose()
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(c + 1, flatFiltered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(c - 1, 0))
    } else if (e.key === 'Enter') {
      const item = flatFiltered[cursor]
      if (item) execute(item)
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          {/* Panel */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="fixed top-[20%] left-1/2 -translate-x-1/2 z-50 w-full max-w-md"
          >
            <div className="bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
              {/* Search */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                <Search size={15} className="text-muted-foreground shrink-0" />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type a command or search…"
                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 outline-none"
                />
                <kbd className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5 font-mono">
                  ESC
                </kbd>
              </div>

              {/* Results */}
              <div className="max-h-80 overflow-y-auto py-1">
                {flatFiltered.length === 0 && (
                  <p className="text-center text-sm text-muted-foreground py-8">No results</p>
                )}
                {Array.from(grouped.entries()).map(([group, items]) => (
                  <div key={group}>
                    <p className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                      {group}
                    </p>
                    {items.map((item) => {
                      const idx = flatFiltered.indexOf(item)
                      return (
                        <button
                          key={item.id}
                          onClick={() => execute(item)}
                          onMouseEnter={() => setCursor(idx)}
                          className={cn(
                            'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors',
                            idx === cursor ? 'bg-primary/10 text-foreground' : 'text-muted-foreground hover:text-foreground',
                          )}
                        >
                          <span className={cn('shrink-0', idx === cursor ? 'text-primary' : '')}>
                            {item.icon}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium">{item.label}</p>
                            {item.description && (
                              <p className="text-xs text-muted-foreground/70 truncate">{item.description}</p>
                            )}
                          </div>
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>

              {/* Footer */}
              <div className="border-t border-border px-4 py-2 flex items-center gap-3 text-[10px] text-muted-foreground/50">
                <span><kbd className="font-mono">↑↓</kbd> navigate</span>
                <span><kbd className="font-mono">↵</kbd> select</span>
                <span><kbd className="font-mono">esc</kbd> close</span>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
