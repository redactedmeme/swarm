'use client'
import { useDashboard } from '@/context/DashboardContext'
import { fmt, fmtCompact } from '@/lib/formatters'
import { getEstimatedFees, getFlameLevel, getBuyPct, buyPressureColor, poolLabel } from '@/lib/calculations'

const MEDALS = ['🥇', '🥈', '🥉']
const FLAMES = ['', '🔥', '🔥🔥', '🔥🔥🔥']

export function HotPools() {
  const { poolsData, feeRatesMap } = useDashboard()

  const sorted = [...poolsData].sort((a, b) => {
    const tA = (a.txns?.h24?.buys ?? 0) + (a.txns?.h24?.sells ?? 0)
    const tB = (b.txns?.h24?.buys ?? 0) + (b.txns?.h24?.sells ?? 0)
    return tB - tA
  })

  const top12  = sorted.slice(0, 12)
  const podium = sorted.slice(0, 3)

  // fees by dex
  const dexFees: Record<string, number> = {}
  for (const p of poolsData) {
    const f = getEstimatedFees(p, 'h24', feeRatesMap) ?? 0
    dexFees[p.dexId] = (dexFees[p.dexId] ?? 0) + f
  }
  const dexList = Object.entries(dexFees).sort((a, b) => b[1] - a[1])
  const totalFees = dexList.reduce((s, [, f]) => s + f, 0)

  return (
    <div className="space-y-4">
      {/* Hot pools list */}
      <div>
        <div className="text-[10px] text-text-muted uppercase tracking-widest mb-3">
          Hot Pools <span className="text-text-muted">({poolsData.length})</span>
        </div>
        <div className="space-y-1.5">
          {top12.map(pool => {
            const txns  = (pool.txns?.h24?.buys ?? 0) + (pool.txns?.h24?.sells ?? 0)
            const level = getFlameLevel(pool)
            const buyPct = getBuyPct(pool)
            return (
              <div key={pool.pairAddress} className="bg-bg-card border border-border rounded-lg px-3 py-2 hover:border-accent/30 transition-colors">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px]">{FLAMES[level]}</span>
                    <span className="text-[10px] font-semibold">{poolLabel(pool)}</span>
                    <span className="text-[8px] text-text-muted capitalize">{pool.dexId}</span>
                  </div>
                  <span className="text-[10px] text-text-muted">{fmtCompact(txns)} txns</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-0.5 bg-bg-primary rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${buyPct}%`, background: buyPressureColor(buyPct) }} />
                  </div>
                  <span className="text-[9px] text-text-muted">{fmt(pool.volume?.h24 ?? 0)}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Podium */}
      {podium.length > 0 && (
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Top 3</div>
          <div className="space-y-1.5">
            {podium.map((pool, i) => {
              const txns = (pool.txns?.h24?.buys ?? 0) + (pool.txns?.h24?.sells ?? 0)
              return (
                <div key={pool.pairAddress}
                  className="bg-bg-card border border-border rounded-lg px-3 py-2 hover:border-accent/30 transition-colors">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px]">{MEDALS[i]} {poolLabel(pool)}</span>
                    <span className="text-[10px] text-text-muted">{fmtCompact(txns)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Fees by DEX */}
      {dexList.length > 0 && (
        <div>
          <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2">Fees by DEX</div>
          <div className="space-y-1.5">
            {dexList.map(([dex, fees]) => (
              <div key={dex} className="flex items-center justify-between bg-bg-card border border-border rounded-lg px-3 py-2">
                <span className="text-[10px] capitalize">{dex}</span>
                <div className="text-right">
                  <div className="text-[11px] font-semibold text-accent">{fmt(fees)}</div>
                  <div className="text-[9px] text-text-muted">{totalFees > 0 ? ((fees / totalFees) * 100).toFixed(1) : '0'}%</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
