'use client'
import { useState, useMemo } from 'react'
import { useDashboard } from '@/context/DashboardContext'
import { PoolCard } from './PoolCard'
import { V1V2_POOL, METEORA_DLMM_POOL, getVolume, getLiquidity, getEstimatedFees } from '@/lib/calculations'
import { SkeletonCard } from '@/components/ui/Skeleton'
import type { Pool } from '@/lib/types'

type SortKey = 'vol24h' | 'liquidity' | 'fees' | 'txns'

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'vol24h',    label: 'Vol 24h' },
  { key: 'liquidity', label: 'Liquidity' },
  { key: 'fees',      label: 'Fees' },
  { key: 'txns',      label: 'Txns' },
]

const PINNED_LABELS: Record<string, string> = {
  [V1V2_POOL]:       'REDACTED (liq) / REDACTED (fees) · Orca',
  [METEORA_DLMM_POOL]: 'REDACTED (fees) / REDACTED (liq) · Meteora DLMM',
}

function sortPool(a: Pool, b: Pool, key: SortKey, feeRatesMap: Record<string, number>): number {
  switch (key) {
    case 'vol24h':    return getVolume(b, 'h24') - getVolume(a, 'h24')
    case 'liquidity': return getLiquidity(b) - getLiquidity(a)
    case 'fees':      return (getEstimatedFees(b, 'h24', feeRatesMap) ?? 0) - (getEstimatedFees(a, 'h24', feeRatesMap) ?? 0)
    case 'txns':      return ((b.txns?.h24?.buys ?? 0) + (b.txns?.h24?.sells ?? 0)) - ((a.txns?.h24?.buys ?? 0) + (a.txns?.h24?.sells ?? 0))
    default:          return 0
  }
}

export function PoolGrid() {
  const { poolsData, feeRatesMap, loading } = useDashboard()
  const [sortKey, setSortKey] = useState<SortKey>('vol24h')
  const [dexFilter, setDexFilter] = useState<string>('all')

  const dexes = useMemo(() => {
    const set = new Set(poolsData.map(p => p.dexId))
    return ['all', ...Array.from(set).sort()]
  }, [poolsData])

  const pinnedAddrs = new Set([V1V2_POOL, METEORA_DLMM_POOL])

  const { pinned, others } = useMemo(() => {
    const filtered = dexFilter === 'all' ? poolsData : poolsData.filter(p => p.dexId === dexFilter)
    const pinned = filtered.filter(p => pinnedAddrs.has(p.pairAddress))
    const others = filtered
      .filter(p => !pinnedAddrs.has(p.pairAddress))
      .sort((a, b) => sortPool(a, b, sortKey, feeRatesMap))
    return { pinned, others }
  }, [poolsData, dexFilter, sortKey, feeRatesMap])

  if (loading && poolsData.length === 0) {
    return (
      <div className="space-y-3">
        <div className="h-8 bg-bg-card rounded-xl" style={{ background: 'linear-gradient(90deg, #121218 0%, #1a1a22 50%, #121218 100%)', backgroundSize: '200% 100%', animation: 'shimmer 2s linear infinite' }} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} lines={5} />)}
        </div>
      </div>
    )
  }

  if (poolsData.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-xl p-10 flex flex-col items-center gap-3 text-text-muted">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
          <circle cx="12" cy="12" r="10" /><line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
        </svg>
        <span className="text-[12px]">No pools found for this token</span>
      </div>
    )
  }

  return (
    <div className="space-y-3 animate-fadeIn">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] text-text-muted uppercase tracking-widest">Active Pools</span>
          <span className="text-[10px] text-text-muted bg-bg-card border border-border rounded-full px-2 py-0.5">{poolsData.length}</span>

          {/* DEX filter */}
          <div className="flex gap-1 flex-wrap">
            {dexes.map(dex => (
              <button
                key={dex}
                onClick={() => setDexFilter(dex)}
                className={`text-[9px] capitalize px-2 py-0.5 rounded-full border transition-colors ${
                  dexFilter === dex
                    ? 'border-accent text-accent bg-accent/5'
                    : 'border-border text-text-muted hover:border-accent/40'
                }`}
              >
                {dex}
              </button>
            ))}
          </div>
        </div>

        {/* Sort controls */}
        <div className="flex items-center gap-1">
          <span className="text-[9px] text-text-muted mr-1">Sort:</span>
          {SORT_OPTIONS.map(o => (
            <button
              key={o.key}
              onClick={() => setSortKey(o.key)}
              className={`text-[9px] px-2 py-0.5 rounded border transition-colors ${
                sortKey === o.key
                  ? 'border-accent text-accent bg-accent/5'
                  : 'border-border text-text-muted hover:border-accent/40'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {/* Pinned pools */}
      {pinned.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {pinned.map(pool => (
            <PoolCard
              key={pool.pairAddress}
              pool={pool}
              feeRates={feeRatesMap}
              pinned
              pinnedLabel={PINNED_LABELS[pool.pairAddress]}
            />
          ))}
        </div>
      )}

      {/* Other pools */}
      {others.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {others.map(pool => (
            <PoolCard key={pool.pairAddress} pool={pool} feeRates={feeRatesMap} />
          ))}
        </div>
      )}

      {pinned.length + others.length === 0 && (
        <div className="bg-bg-card border border-border rounded-xl p-6 text-center text-[11px] text-text-muted">
          No pools match the selected filter
        </div>
      )}
    </div>
  )
}
