import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Settings, Shield, Zap, Check, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/app/lib/utils'
import { apiGetPrivacyConfig, apiSetPrivacyConfig } from '@/app/lib/api'
import type { PrivacyConfig } from '@/app/types'

type Mode = 'standard' | 'focused' | 'deep' | 'creative'

type ModeInfo = { id: Mode; label: string; description: string; icon: string }

const MODES: ModeInfo[] = [
  { id: 'standard',  label: 'Standard',  description: 'Balanced context and speed',            icon: '💬' },
  { id: 'focused',   label: 'Focused',   description: 'Minimal context, faster responses',     icon: '🎯' },
  { id: 'deep',      label: 'Deep',      description: 'Full memory + arc context enabled',     icon: '🌊' },
  { id: 'creative',  label: 'Creative',  description: 'More exploratory, less predictable',    icon: '🎨' },
]

const PRIVACY_MODES = [
  { id: 'anonymous', label: 'Anonymous',  description: 'Identity stripped, no logging' },
  { id: 'private',   label: 'Private',    description: 'Minimal logging, headers cleaned' },
  { id: 'maximum',   label: 'Maximum',    description: 'Full PII scrub + ephemeral mode' },
] as const

async function fetchModes(): Promise<{ modes: ModeInfo[]; active: Mode }> {
  const res = await fetch('/api/modes', {
    headers: { Authorization: `Bearer ${localStorage.getItem('rc_token') ?? ''}` },
  })
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

async function setMode(mode: Mode): Promise<void> {
  const res = await fetch('/api/modes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('rc_token') ?? ''}`,
    },
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) throw new Error('Failed to set mode')
}

const STAGGER = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } }
const ITEM = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.25 } } }

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data: modesData } = useQuery({ queryKey: ['modes'], queryFn: fetchModes })
  const { data: privacy, isLoading: privacyLoading } = useQuery({
    queryKey: ['privacy-config'],
    queryFn: apiGetPrivacyConfig,
  })

  const [localPrivacy, setLocalPrivacy] = useState<Partial<PrivacyConfig>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (privacy) setLocalPrivacy(privacy)
  }, [privacy])

  const activeMode = modesData?.active ?? 'standard'

  const setModeMutation = useMutation({
    mutationFn: setMode,
    onSuccess: (_data, mode) => {
      qc.setQueryData(['modes'], (old: typeof modesData) => old ? { ...old, active: mode } : old)
      toast.success(`Mode set to ${mode}`)
    },
    onError: () => toast.error('Failed to set mode'),
  })

  async function savePrivacy() {
    setSaving(true)
    try {
      await apiSetPrivacyConfig(localPrivacy)
      qc.invalidateQueries({ queryKey: ['privacy-config'] })
      toast.success('Privacy settings saved')
    } catch {
      toast.error('Failed to save privacy settings')
    } finally {
      setSaving(false)
    }
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
            <div className="grid grid-cols-2 gap-2 mt-3">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setModeMutation.mutate(m.id)}
                  disabled={setModeMutation.isPending}
                  className={cn(
                    'flex items-start gap-3 p-3 rounded-xl border text-left transition-all duration-150',
                    activeMode === m.id
                      ? 'border-primary/50 bg-primary/8 glow-sm'
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
          </motion.section>

          {/* Privacy */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Shield size={14} />} title="Privacy Mode" />
            {privacyLoading ? (
              <div className="grid grid-cols-3 gap-2 mt-3 animate-pulse">
                {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-secondary" />)}
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2 mt-3">
                {PRIVACY_MODES.map((pm) => {
                  const active = (localPrivacy.mode ?? privacy?.mode) === pm.id
                  return (
                    <button
                      key={pm.id}
                      onClick={() => setLocalPrivacy((p) => ({ ...p, mode: pm.id }))}
                      className={cn(
                        'flex flex-col items-start p-3 rounded-xl border text-left transition-all duration-150',
                        active
                          ? 'border-primary/50 bg-primary/8 glow-sm'
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
            )}

            {/* Toggles */}
            <div className="mt-3 space-y-2">
              <Toggle
                label="PII Scrubbing"
                description="Redact personal identifiers from all LLM calls"
                checked={localPrivacy.pii_scrub ?? privacy?.pii_scrub ?? false}
                onChange={(v) => setLocalPrivacy((p) => ({ ...p, pii_scrub: v }))}
              />
              <Toggle
                label="Ephemeral Mode"
                description="No conversation logs stored on proxy"
                checked={localPrivacy.ephemeral ?? privacy?.ephemeral ?? false}
                onChange={(v) => setLocalPrivacy((p) => ({ ...p, ephemeral: v }))}
              />
            </div>

            {/* Log level */}
            <div className="mt-3">
              <p className="text-xs font-medium text-muted-foreground mb-2">Log Level</p>
              <div className="flex gap-2">
                {(['full', 'minimal', 'none'] as const).map((level) => {
                  const active = (localPrivacy.log_level ?? privacy?.log_level) === level
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
              disabled={saving}
              className={cn(
                'mt-4 w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium transition-all',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'disabled:opacity-40 disabled:cursor-not-allowed',
              )}
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {saving ? 'Saving…' : 'Save Privacy Settings'}
            </button>
          </motion.section>

          {/* Keyboard shortcuts */}
          <motion.section variants={ITEM}>
            <SectionHeader icon={<Settings size={14} />} title="Keyboard Shortcuts" />
            <div className="mt-3 space-y-1.5">
              {[
                ['Open command palette', '⌘ K'],
                ['Clear chat', '⌘ ⇧ L'],
                ['Close modals', 'Esc'],
              ].map(([label, keys]) => (
                <div key={label} className="flex items-center justify-between py-2 border-b border-border/40 last:border-0">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <kbd className="px-2 py-1 rounded border border-border bg-secondary text-xs font-mono text-foreground">{keys}</kbd>
                </div>
              ))}
            </div>
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

function Toggle({
  label, description, checked, onChange,
}: {
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
          'relative w-9 h-5 rounded-full border transition-all duration-200',
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
