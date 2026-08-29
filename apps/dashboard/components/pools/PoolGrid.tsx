'use client'
import { useDashboard } from '@/context/DashboardContext'
import { PoolCard } from './PoolCard'
import { V1V2_POOL, METEORA_DLMM_POOL } from '@/lib/calculations'

export function PoolGrid() {
  const { poolsData, v1v2PoolData, meteoraPoolData, feeRatesMap, loading } = useDashboard()

  if (loading && poolsData.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-xl p-8 text-center text-text-muted text-[11px]">
        Loading pools…
      </div>
    )
  }

  if (poolsData.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-xl p-8 text-center text-text-muted text-[11px]">
        No pools found for this token
      </div>
    )
  }

  const pinnedAddrs = new Set([V1V2_POOL, METEORA_DLMM_POOL])
  const pinnedPools = poolsData.filter(p => pinnedAddrs.has(p.pairAddress))
  const otherPools  = poolsData.filter(p => !pinnedAddrs.has(p.pairAddress))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-text-muted uppercase tracking-widest">Active Pools</span>
        <span className="text-[10px] text-text-muted">{poolsData.length} pools</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {pinnedPools.map(pool => (
          <PoolCard key={pool.pairAddress} pool={pool} feeRates={feeRatesMap} pinned
            pinnedLabel={pool.pairAddress === V1V2_POOL ? 'REDACTED (liq) / REDACTED (fees) · Orca' : 'REDACTED (fees) / REDACTED (liq) · Meteora DLMM'} />
        ))}
        {otherPools.map(pool => (
          <PoolCard key={pool.pairAddress} pool={pool} feeRates={feeRatesMap} />
        ))}
      </div>
    </div>
  )
}
