import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Settings, Shield, Zap, Check, Loader2, Monitor, Bell, Trash2, Info } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/app/lib/utils'
import { useAuthStore } from '@/app/store/authStore'
import type { PrivacyConfig } from '@/app/types'

// ── Local settings (localStorage) ────────────────────────────────────────────

interface LocalSettings {
  soundEnabled: boolean
  compactMode: boolean
  showTimestamps: boolean
  streamingSpeed: 'fast' | 'normal' | 'slow'
  defaultAgent: string
}

const DEFAULT_LOCAL: LocalSettings = {
  soundEnabled: false,
  compactMode: false,
  showTimestamps: true,
  streamingSpeed: 'normal',
  defaultAgent: 'chan',
}

function loadLocal(): LocalSettings {
  try {
    return { ...DEFAULT_LOCAL, ...JSON.parse(localStorage.getItem('rc-ui-settings') ?? '{}') }
  } catch {
    return DEFAULT_LOCAL
  }
}

function saveLocal(s: LocalSettings) {
  localStorage.setItem('rc-ui-settings', JSON.stringify(s))
}

// ── Types ────────────────────────────────────────────────────────────────────

type Mode = 'standard' | 'focused' | 'deep' | 'creative'

const MODES = [
  { id: 'standard' as Mode, label: 'Standard',  description: 'Balanced context and speed',         icon: '💬' },
  { id: 'focused'  as Mode, label: 'Focused',   description: 'Minimal context, faster responses',  icon: '🎯' },
  { id: 'deep'     as Mode, label: 'Deep',      description: 'Full memory + arc context enabled',  icon: '🌊' },
  { id: 'creative' as Mode, label: 'Creative',  description: 'More exploratory, less predictable', icon: '🎨' },
]

const PRIVACY_MODES = [
  { id: 'anonymous', label: 'Anonymous',  description: 'Identity stripped, no logging' },
  { id: 'private',   label: 'Private',    description: 'Minimal logging, headers cleaned' },
  { id: 'maximum',   label: 'Maximum',    description: 'Full PII scrub + ephemeral mode' },
] as const

// ── API helpers ───────────────────────────────────────────────────────────────

function getToken() { return localStorage.getItem('rc_token') ?? '' }

async function fetchModes(): Promise<{ modes: typeof MODES; active: Mode }> {
  const res = await fetch('/api/modes', { headers: { Authorization: `Bearer ${getToken()}` } })
  if (!res.ok) throw new Error(`Modes unavailable (${res.status})`)
  return res.json()
}

async function postMode(mode: Mode): Promise<void> {
  const res = await fetch('/api/modes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string }
    throw new Error(err.detail ?? `Server returned ${res.status}`)
  }
}

async function fetchPrivacy(): Promise<PrivacyConfig | null> {
  const res = await fetch('/proxy-config', { headers: { Authorization: `Bearer ${getToken()}` } })
  if (res.status === 503) return null  // proxy not configured — not an error
  if (!res.ok) throw new Error(`Privacy config unavailable (${res.status})`)
  const raw = await res.json() as Record<string, unknown>
  return {
    mode: String(raw.privacy_mode ?? raw.mode ?? 'anonymous') as PrivacyConfig['mode'],
    log_level: String(raw.log_level ?? 'full') as PrivacyConfig['log_level'],
    pii_scrub: Boolean(raw.privacy_scrub ?? raw.pii_scrub ?? false),
    ephemeral: Boolean(raw.ephemeral_mode ?? raw.ephemeral ?? false),
  }
}

async function postPrivacy(config: Partial<PrivacyConfig>): Promise<void> {
  const payload: Record<string, unknown> = {}
  if (config.mode      !== undefined) payload.privacy_mode    = config.mode
  if (config.log_level !== undefined) payload.log_level       = config.log_level
  if (config.pii_scrub !== undefined) payload.privacy_scrub   = config.pii_scrub
  if (config.ephemeral !== undefined) payload.ephemeral_mode  = config.ephemeral
  const res = await fetch('/proxy-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Failed to save (${res.status})`)
}

// ── Animation variants ────────────────────────────────────────────────────────

const STAGGER = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } }
const ITEM    = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.25 } } }

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const qc = useQueryClient()
  const logout = useAuthStore((s) => s.logout)
  const sessionId = useAuthStore((s) => s.sessionId)

  const [local, setLocal] = useState<LocalSettings>(loadLocal)
  const [localPrivacy, setLocalPrivacy] = useState<Partial<PrivacyConfig>>({})
  const [savingPrivacy, setSavingPrivacy] = useState(false)

  const { data: modesData, error: modesError } = useQuery({
    queryKey: ['modes'],
    queryFn: fetchModes,
    retry: 1,
  })

  const { data: privacy, isLoading: privacyLoading } = useQuery({
    queryKey: ['privacy-config'],
    queryFn: fetchPrivacy,
    retry: 1,
  })

  useEffect(() => { if (privacy) setLocalPrivacy(privacy) }, [privacy])

  const activeMode = modesData?.active ?? 'standard'

  const setModeMutation = useMutation({
    mutationFn: postMode,
    onSuccess: (_data, mode) => {
      qc.setQueryData(['modes'], (old: typeof modesData) => old ? { ...old, active: mode } : old)
      toast.success(`Mode set to ${mode}`)
    },
    onError: (err: Error) => toast.error(`Failed to set mode: ${err.message}`),
  })

  function updateLocal(patch: Partial<LocalSettings>) {
    setLocal((prev) => {
      const next = { ...prev, ...patch }
      saveLocal(next)
      return next
    })
  }

  async function savePrivacy() {
    setSavingPrivacy(true)
    try {
      await postPrivacy(localPrivacy)
      qc.invalidateQueries({ queryKey: ['privacy-config'] })
      toast.success('Privacy settings saved')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save privacy settings')
    } finally {
      setSavingPrivacy(false)
    }
  }

  function clearChatHistory() {
    localStorage.removeItem('webchat-chat-store')
    toast.success('Chat history cleared — reload to apply')
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-6">
          <Settings size={18} className="text-primary" />
          <h1 className="text-base font-semibold text-foreground">Settings</h1>
          <div className="h-px flex-1 bg-border" />
        </div>

        <motion.div variants={STAGGER} initial="hidden" animate="show" className="space-y-6">

          {/* LLM Mode */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Zap size={14} />} title="Conversation Mode" />
            {modesError ? (
              <p className="text-xs text-amber-400 mt-2 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                Mode service unavailable — chan-bot may be offline
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2 mt-3">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setModeMutation.mutate(m.id)}
                    disabled={setModeMutation.isPending}
                    className={cn(
                      'flex items-start gap-3 p-3 rounded-xl border text-left transition-all duration-150',
                      activeMode === m.id
                        ? 'border-primary/50 bg-primary/8'
                        : 'border-border bg-card hover:border-border/70 hover:bg-secondary/30',
                    )}
                  >
                    <span className="text-xl">{m.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-foreground">{m.label}</p>
                        {activeMode === m.id && <Check size={12} className="text-primary" />}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{m.description}</p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </motion.section>

          {/* UI Settings */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Monitor size={14} />} title="Interface" />
            <div className="mt-3 space-y-2">
              <Toggle
                label="Show Timestamps"
                description="Display message send times in chat"
                checked={local.showTimestamps}
                onChange={(v) => updateLocal({ showTimestamps: v })}
              />
              <Toggle
                label="Compact Mode"
                description="Reduce message padding and spacing"
                checked={local.compactMode}
                onChange={(v) => updateLocal({ compactMode: v })}
              />
              <Toggle
                label="Sound Notifications"
                description="Play a tone when messages arrive"
                checked={local.soundEnabled}
                onChange={(v) => updateLocal({ soundEnabled: v })}
              />
            </div>

            {/* Streaming speed */}
            <div className="mt-3">
              <p className="text-xs font-medium text-muted-foreground mb-2">Response Streaming Speed</p>
              <div className="flex gap-2">
                {(['fast', 'normal', 'slow'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => updateLocal({ streamingSpeed: s })}
                    className={cn(
                      'flex-1 py-1.5 rounded-lg border text-xs font-medium capitalize transition-all',
                      local.streamingSpeed === s
                        ? 'border-primary/50 bg-primary/10 text-primary'
                        : 'border-border bg-card text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </motion.section>

          {/* Privacy */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Shield size={14} />} title="Privacy Mode" />

            {privacyLoading ? (
              <div className="grid grid-cols-3 gap-2 mt-3 animate-pulse">
                {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-secondary" />)}
              </div>
            ) : privacy === null ? (
              <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground bg-secondary/50 border border-border rounded-lg px-3 py-2.5">
                <Info size={13} className="shrink-0" />
                <span>Privacy proxy not configured — set <code className="font-mono text-foreground/70">PROXY_INTERNAL_URL</code> on the webchat service to enable.</span>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-2 mt-3">
                  {PRIVACY_MODES.map((pm) => {
                    const active = (localPrivacy.mode ?? privacy.mode) === pm.id
                    return (
                      <button
                        key={pm.id}
                        onClick={() => setLocalPrivacy((p) => ({ ...p, mode: pm.id }))}
                        className={cn(
                          'flex flex-col items-start p-3 rounded-xl border text-left transition-all duration-150',
                          active
                            ? 'border-primary/50 bg-primary/8'
                            : 'border-border bg-card hover:border-border/70 hover:bg-secondary/30',
                        )}
                      >
                        <div className="flex items-center justify-between w-full">
                          <p className="text-sm font-medium text-foreground">{pm.label}</p>
                          {active && <Check size={12} className="text-primary" />}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{pm.description}</p>
                      </button>
                    )
                  })}
                </div>

                <div className="mt-3 space-y-2">
                  <Toggle
                    label="PII Scrubbing"
                    description="Redact personal identifiers from all LLM calls"
                    checked={localPrivacy.pii_scrub ?? privacy.pii_scrub ?? false}
                    onChange={(v) => setLocalPrivacy((p) => ({ ...p, pii_scrub: v }))}
                  />
                  <Toggle
                    label="Ephemeral Mode"
                    description="No conversation logs stored on proxy"
                    checked={localPrivacy.ephemeral ?? privacy.ephemeral ?? false}
                    onChange={(v) => setLocalPrivacy((p) => ({ ...p, ephemeral: v }))}
                  />
                </div>

                <div className="mt-3">
                  <p className="text-xs font-medium text-muted-foreground mb-2">Log Level</p>
                  <div className="flex gap-2">
                    {(['full', 'minimal', 'none'] as const).map((level) => {
                      const active = (localPrivacy.log_level ?? privacy.log_level) === level
                      return (
                        <button
                          key={level}
                          onClick={() => setLocalPrivacy((p) => ({ ...p, log_level: level }))}
                          className={cn(
                            'flex-1 py-1.5 rounded-lg border text-xs font-medium capitalize transition-all',
                            active
                              ? 'border-primary/50 bg-primary/10 text-primary'
                              : 'border-border bg-card text-muted-foreground hover:text-foreground',
                          )}
                        >
                          {level}
                        </button>
                      )
                    })}
                  </div>
                </div>

                <button
                  onClick={savePrivacy}
                  disabled={savingPrivacy}
                  className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                >
                  {savingPrivacy && <Loader2 size={14} className="animate-spin" />}
                  {savingPrivacy ? 'Saving…' : 'Save Privacy Settings'}
                </button>
              </>
            )}
          </motion.section>

          {/* Notifications placeholder */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Bell size={14} />} title="Notifications" />
            <div className="mt-3 space-y-2">
              <Toggle
                label="Browser Notifications"
                description="Desktop alerts when agents respond (requires browser permission)"
                checked={false}
                onChange={() => {
                  Notification.requestPermission().then((p) => {
                    if (p === 'granted') toast.success('Browser notifications enabled')
                    else toast.error('Permission denied')
                  })
                }}
              />
            </div>
          </motion.section>

          {/* Session info */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Info size={14} />} title="Session" />
            <div className="mt-3 space-y-2 text-xs text-muted-foreground">
              <div className="flex items-center justify-between py-2 border-b border-border/40">
                <span>Session ID</span>
                <code className="font-mono text-[10px] text-foreground/50">{sessionId?.slice(0, 16) ?? '—'}…</code>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border/40">
                <span>Token status</span>
                <span className="text-emerald-400">● valid</span>
              </div>
            </div>
            <button
              onClick={clearChatHistory}
              className="mt-3 flex items-center gap-2 text-xs text-red-400 hover:text-red-300 bg-red-500/5 hover:bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 transition-all"
            >
              <Trash2 size={13} />
              Clear chat history (local)
            </button>
          </motion.section>

          {/* Keyboard shortcuts */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Settings size={14} />} title="Keyboard Shortcuts" />
            <div className="mt-3 space-y-1.5">
              {[
                ['Open command palette', '⌘ K'],
                ['Clear chat',          '⌘ ⇧ L'],
                ['Close modals',        'Esc'],
                ['Terminal clear',      'Ctrl+L (in terminal)'],
                ['History up/down',     '↑ / ↓ (in terminal)'],
              ].map(([label, keys]) => (
                <div key={label} className="flex items-center justify-between py-2 border-b border-border/40 last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <kbd className="px-2 py-1 rounded border border-border bg-secondary text-xs font-mono text-foreground">{keys}</kbd>
                </div>
              ))}
            </div>
          </motion.section>

          {/* Logout */}
          <motion.section variants={ITEM}>
            <button
              onClick={logout}
              className="w-full py-2.5 rounded-xl border border-red-500/20 text-red-400 hover:bg-red-500/10 text-sm font-medium transition-all"
            >
              Log out
            </button>
          </motion.section>

        </motion.div>
      </div>
    </div>
  )
}

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground">{icon}</span>
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}

function Toggle({ label, description, checked, onChange }: {
  label: string; description: string; checked: boolean; onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between py-2.5 px-3 bg-card border border-border rounded-xl">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative w-9 h-5 rounded-full border transition-all duration-200 shrink-0',
          checked ? 'bg-primary border-primary' : 'bg-secondary border-border',
        )}
      >
        <motion.span
          className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm"
          animate={{ x: checked ? 16 : 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
        />
      </button>
    </div>
  )
}
