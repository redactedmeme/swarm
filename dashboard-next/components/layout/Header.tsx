'use client'
import { useState, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useDashboard } from '@/context/DashboardContext'
import { TOKEN } from '@/lib/calculations'

const WalletButton = dynamic(
  () => import('@/components/wallet/WalletButton').then(m => m.WalletButton),
  { ssr: false }
)

const REFRESH_INTERVAL = 30

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className={spinning ? 'animate-spin' : ''}
    >
      <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
    </svg>
  )
}

export function Header() {
  const { loading, lastUpdated, refresh } = useDashboard()
  const [copied, setCopied] = useState(false)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)

  useEffect(() => {
    if (!lastUpdated) return
    const tick = () => {
      const elapsed = Math.floor((Date.now() - lastUpdated.getTime()) / 1000)
      setCountdown(Math.max(0, REFRESH_INTERVAL - elapsed))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [lastUpdated])

  function copy() {
    navigator.clipboard.writeText(TOKEN)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const countdownUrgent = countdown <= 5

  return (
    <header
      className="sticky top-0 z-20 border-b border-border px-4 h-12 flex items-center justify-between"
      style={{ background: 'rgba(10,10,15,0.97)', backdropFilter: 'blur(12px)' }}
    >
      {/* Left: brand */}
      <div className="flex items-center gap-3">
        {/* Live dot */}
        <div className="flex items-center gap-1.5">
          <span
            className="block w-2 h-2 rounded-full bg-pos animate-pulse2"
            style={{ boxShadow: '0 0 8px rgba(0,255,136,0.9)' }}
          />
          <span className="text-[9px] text-text-muted uppercase tracking-widest hidden lg:block">live</span>
        </div>

        <div className="w-px h-4 bg-border" />

        <h1 className="text-[13px] font-semibold tracking-wide flex items-center gap-1.5">
          <span className="text-accent" style={{ textShadow: '0 0 14px rgba(0,220,255,0.6)' }}>
            REDACTED
          </span>
          <span className="text-text-secondary font-normal hidden sm:inline">SWARM TRACKER</span>
        </h1>

        {/* Token address pill */}
        <button
          onClick={copy}
          title={copied ? 'Copied!' : TOKEN}
          className="hidden sm:flex items-center gap-1.5 text-[10px] text-text-muted bg-bg-card px-2.5 py-1 rounded-full border border-border hover:border-accent hover:text-accent transition-all"
        >
          <span className="font-mono">{copied ? '✓ copied' : '9a21…KgnM'}</span>
        </button>
      </div>

      {/* Right: controls */}
      <div className="flex items-center gap-2">
        {/* Countdown */}
        {lastUpdated && (
          <div className="hidden sm:flex items-center gap-1 text-[10px] text-text-muted">
            <span>in</span>
            <span
              className={`font-mono tabular-nums transition-colors ${countdownUrgent ? 'text-accent' : ''}`}
            >
              {countdown}s
            </span>
          </div>
        )}

        {/* Refresh button */}
        <button
          onClick={refresh}
          disabled={loading}
          title="Refresh data"
          className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 border border-border rounded-lg text-text-secondary hover:border-accent hover:text-accent transition-all disabled:opacity-40"
        >
          <RefreshIcon spinning={loading} />
          <span className="hidden sm:block">{loading ? 'Loading…' : 'Refresh'}</span>
        </button>

        <WalletButton />
      </div>
    </header>
  )
}
