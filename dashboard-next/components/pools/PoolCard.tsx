'use client'
import { useState } from 'react'
import type { Pool, FeeRatesMap } from '@/lib/types'
import { fmt, fmtCompact } from '@/lib/formatters'
import { getVolume, getLiquidity, getEstimatedFees, getFeeRate, getBuyPct, buyPressureColor, poolLabel } from '@/lib/calculations'
import { Tooltip } from '@/components/ui/Tooltip'

interface PoolCardProps {
  pool: Pool
  feeRates: FeeRatesMap
  pinned?: boolean
  pinnedLabel?: string
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  function copy(e: React.MouseEvent) {
    e.preventDefault()
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }
  return (
    <Tooltip content={copied ? 'Copied!' : `Copy ${label}`}>
      <button
        onClick={copy}
        className="text-[9px] text-text-muted hover:text-accent transition-colors px-1 py-0.5 rounded border border-transparent hover:border-accent/30"
      >
        {copied ? '✓' : '⧉'}
      </button>
    </Tooltip>
  )
}

const DEX_LINK: Record<string, (addr: string) => string> = {
  raydium:  addr => `https://dexscreener.com/solana/${addr}`,
  orca:     addr => `https://dexscreener.com/solana/${addr}`,
  meteora:  addr => `https://dexscreener.com/solana/${addr}`,
}

function ExternalLink({ pool }: { pool: Pool }) {
  const url = (DEX_LINK[pool.dexId] ?? DEX_LINK.raydium)(pool.pairAddress)
  return (
    <Tooltip content="View on DexScreener">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[9px] text-text-muted hover:text-accent transition-colors px-1 py-0.5 rounded border border-transparent hover:border-accent/30"
        onClick={e => e.stopPropagation()}
      >
        ↗
      </a>
    </Tooltip>
  )
}

export function PoolCard({ pool, feeRates, pinned, pinnedLabel }: PoolCardProps) {
  const feeRate  = getFeeRate(pool, feeRates)
  const fees24h  = getEstimatedFees(pool, 'h24', feeRates)
  const buyPct   = getBuyPct(pool)
  const vol24h   = getVolume(pool, 'h24')
  const vol6h    = getVolume(pool, 'h6')
  const liq      = getLiquidity(pool)
  const txns24   = (pool.txns?.h24?.buys ?? 0) + (pool.txns?.h24?.sells ?? 0)

  const feeLabel = feeRate != null
    ? feeRate >= 0.005 ? 'HIGH' : feeRate >= 0.002 ? 'MID' : 'LOW'
    : null
  const feeLabelStyle = feeLabel === 'HIGH'
    ? 'text-accent border-accent/40 bg-accent/10'
    : feeLabel === 'MID'
    ? 'text-amber border-amber/30 bg-amber/5'
    : 'text-text-muted border-border bg-bg-primary'

  const hasFees = fees24h != null
  const pressureColor = buyPressureColor(buyPct)

  const truncAddr = pool.pairAddress.slice(0, 4) + '…' + pool.pairAddress.slice(-4)
  const dexLabel = pool.dexId.charAt(0).toUpperCase() + pool.dexId.slice(1)

  return (
    <div
      className={`bg-bg-card rounded-xl p-4 transition-all hover:translate-y-[-1px] group ${
        pinned ? 'border-2' : 'border'
      } ${hasFees ? 'border-accent/30 hover:border-accent/50' : 'border-border hover:border-border/80'}`}
      style={hasFees ? { boxShadow: '0 0 20px rgba(0,220,255,0.08), inset 0 0 16px rgba(0,220,255,0.02)' } : {}}
    >
      {/* Pinned label */}
      {pinned && pinnedLabel && (
        <div className="text-[8px] text-accent uppercase tracking-widest mb-2 font-semibold">{pinnedLabel}</div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] font-bold">{poolLabel(pool)}</span>
          {feeLabel && (
            <span className={`text-[8px] border px-1.5 py-0.5 rounded-full font-semibold ${feeLabelStyle}`}>
              {feeLabel}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 text-[10px] text-text-muted">
          <span className="capitalize font-medium">{dexLabel}</span>
          <CopyButton text={pool.pairAddress} label="pool address" />
          <ExternalLink pool={pool} />
        </div>
      </div>

      {/* Address */}
      <div className="text-[9px] text-text-muted font-mono mb-3 opacity-60">{truncAddr}</div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { l: 'Vol 24h',   v: fmt(vol24h),                           accent: false },
          { l: 'Vol 6h',    v: fmt(vol6h),                            accent: false },
          { l: 'Txns 24h',  v: fmtCompact(txns24),                    accent: false },
          { l: 'Liquidity', v: fmt(liq),                              accent: false },
          { l: 'Fee Rate',  v: feeRate != null ? (feeRate * 100).toFixed(2) + '%' : '--', accent: hasFees },
          { l: 'Buy %',     v: buyPct + '%',                          accent: false },
        ].map(({ l, v, accent }) => (
          <div key={l} className="bg-bg-primary rounded-lg p-2 text-center">
            <div className="text-[8px] text-text-muted uppercase tracking-wide mb-0.5">{l}</div>
            <div className={`text-[11px] font-semibold ${accent ? 'text-accent' : ''}`}>{v}</div>
          </div>
        ))}
      </div>

      {/* Buy pressure + fees footer */}
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <div className="h-1.5 bg-bg-primary rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${buyPct}%`, background: pressureColor }}
            />
          </div>
          <div className="text-[8px] text-text-muted mt-1">{buyPct}% buy pressure</div>
        </div>
        {fees24h != null && (
          <div className="text-right shrink-0">
            <div
              className="text-[12px] font-bold text-accent"
              style={{ textShadow: '0 0 10px rgba(0,220,255,0.5)' }}
            >
              {fmt(fees24h)}
            </div>
            <div className="text-[8px] text-text-muted">/ day fees</div>
          </div>
        )}
      </div>
    </div>
  )
}
