'use client'
import { useState } from 'react'
import { useDashboard } from '@/context/DashboardContext'
import { WalletButton } from '@/components/wallet/WalletButton'
import { TOKEN } from '@/lib/calculations'

export function Header() {
  const { loading, lastUpdated, refresh } = useDashboard()
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(TOKEN)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <header className="border-b border-border px-4 py-3 flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-semibold tracking-wide">
          <span className="text-accent">REDACTED</span> SWARM TRACKER
        </h1>
        <button
          onClick={copy}
          className="text-[10px] text-text-muted bg-bg-card px-2 py-0.5 rounded border border-border hover:border-accent transition-colors"
        >
          {copied ? 'Copied!' : '9a21gb7f…KgnM'}
        </button>
      </div>

      <div className="flex items-center gap-3">
        <WalletButton />
        <button
          onClick={refresh}
          disabled={loading}
          className="text-[11px] px-3 py-1 border border-border rounded text-text-secondary hover:border-accent hover:text-text-primary transition-colors disabled:opacity-40"
        >
          {loading ? '…' : 'Refresh'}
        </button>
        {lastUpdated && (
          <span className="text-[10px] text-text-muted hidden sm:block">
            Updated {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>
    </header>
  )
}
