import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Hexagon, Eye, EyeOff, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { useAuthStore } from '@/app/store/authStore'
import { apiLogin } from '@/app/lib/api'
import { cn } from '@/app/lib/utils'

export default function LoginPage() {
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)
  const navigate = useNavigate()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!password.trim() || loading) return
    setLoading(true)
    try {
      const { token, session_id } = await apiLogin(password)
      setAuth(token, session_id)
      navigate('/chat', { replace: true })
    } catch {
      toast.error('Invalid password')
      setShake(true)
      setTimeout(() => setShake(false), 500)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-dvh w-full flex items-center justify-center bg-background relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
        <div className="absolute top-1/3 left-1/3 w-48 h-48 bg-accent/5 rounded-full blur-2xl" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-sm px-4"
      >
        {/* Logo + title */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <motion.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
            className="text-primary"
          >
            <Hexagon size={40} strokeWidth={1} />
          </motion.div>
          <div className="text-center">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">REDACTED</h1>
            <p className="text-sm text-muted-foreground mt-0.5">AI Swarm Interface</p>
          </div>
        </div>

        {/* Card */}
        <AnimatePresence>
          <motion.div
            animate={shake ? { x: [-8, 8, -6, 6, -3, 3, 0] } : { x: 0 }}
            transition={{ duration: 0.4 }}
            className="bg-card border border-border rounded-xl p-6 shadow-xl"
          >
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Access Key
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPw ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    autoFocus
                    className={cn(
                      'w-full bg-input border border-border rounded-lg px-3 py-2.5 pr-10',
                      'text-sm text-foreground placeholder:text-muted-foreground/50',
                      'focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60',
                      'transition-all duration-150',
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !password.trim()}
                className={cn(
                  'w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-medium text-sm',
                  'bg-primary text-primary-foreground',
                  'hover:bg-primary/90 active:scale-[0.98]',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                  'transition-all duration-150',
                )}
              >
                {loading ? <Loader2 size={15} className="animate-spin" /> : null}
                {loading ? 'Authenticating…' : 'Enter Swarm'}
              </button>
            </form>
          </motion.div>
        </AnimatePresence>

        <p className="text-center text-xs text-muted-foreground/50 mt-6">
          End-to-end encrypted · Privacy-first
        </p>
      </motion.div>
    </div>
  )
}
