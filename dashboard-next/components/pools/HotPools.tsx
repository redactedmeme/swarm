'use client'
import { useDashboard } from '@/context/DashboardContext'
import { fmt, fmtCompact } from '@/lib/formatters'
import { getEstimatedFees, getFlameLevel, getBuyPct, buyPressureColor, poolLabel } from '@/lib/calculations'
import { SkeletonCard } from '@/components/ui/Skeleton'

const MEDALS = ['🥇', '🥈', '🥉']
const FLAMES = ['', '🔥', '🔥🔥', '🔥🔥🔥']

const DEX_COLORS: Record<string, string> = {
  raydium: '#9945ff',
  orca:    '#00c2ff',
  meteora: '#38bdf8',
}

export function HotPools() {
  const { poolsData, feeRatesMap, loading } = useDashboard()

  if (loading && poolsData.length === 0) {
    return (
      <div className="space-y-4 p-4">
        {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} lines={2} />)}
      </div>
    )
  }

  const sorted = [...poolsData].sort((a, b) => {
    const tA = (a.txns?.h24?.buys ?? 0) + (a.txns?.h24?.sells ?? 0)
    const tB = (b.txns?.h24?.buys ?? 0) + (b.txns?.h24?.sells ?? 0)
    return tB - tA
  })

  const top12  = sorted.slice(0, 12)
  const podium = sorted.slice(0, 3)

  const dexFees: Record<string, number> = {}
  for (const p of poolsData) {
    const f = getEstimatedFees(p, 'h24', feeRatesMap) ?? 0
    dexFees[p.dexId] = (dexFees[p.dexId] ?? 0) + f
  }
  const dexList = Object.entries(dexFees).sort((a, b) => b[1] - a[1])
  const totalFees = dexList.reduce((s, [, f]) => s + f, 0)

  return (
    <div className="space-y-5 p-4">

      {/* Hot pools list */}
      <div>
        <div className="text-[9px] text-text-muted uppercase tracking-widest mb-3 flex items-center justify-between">
          <span>Hot Pools</span>
          <span className="bg-bg-card border border-border rounded-full px-1.5 py-0.5 text-[9px]">{poolsData.length}</span>
        </div>
        <div className="space-y-1.5">
          {top12.map((pool, idx) => {
            const txns    = (pool.txns?.h24?.buys ?? 0) + (pool.txns?.h24?.sells ?? 0)
            const level   = getFlameLevel(pool)
            const buyPct  = getBuyPct(pool)
            const dexColor = DEX_COLORS[pool.dexId] ?? '#a0a0b0'
            return (
              <div
                key={pool.pairAddress}
                className="bg-bg-card border border-border rounded-lg px-3 py-2.5 hover:border-accent/30 transition-colors"
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-[9px] text-text-muted w-4 shrink-0">#{idx + 1}</span>
                    {level > 0 && <span className="text-[9px] shrink-0">{FLAMES[level]}</span>}
                    <span className="text-[10px] font-semibold truncate">{poolLabel(pool)}</span>
                  </div>
                  <span className="text-[9px] text-text-muted shrink-0 ml-2">{fmtCompact(txns)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1 bg-bg-primary rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${buyPct}%`, background: buyPressureColor(buyPct) }}
                    />
                  </div>
                  <span className="text-[9px] shrink-0" style={{ color: dexColor }}>
                    {pool.dexId}
                  </span>
                  <span className="text-[9px] text-text-muted shrink-0">{fmt(pool.volume?.h24 ?? 0)}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Podium */}
      {podium.length > 0 && (
        <div>
          <div className="text-[9px] text-text-muted uppercase tracking-widest mb-2">Top 3</div>
          <div className="space-y-1.5">
            {podium.map((pool, i) => {
              const txns = (pool.txns?.h24?.buys ?? 0) + (pool.txns?.h24?.sells ?? 0)
              const gradients = [
                'linear-gradient(135deg, rgba(255,215,0,0.08), rgba(255,215,0,0.02))',
                'linear-gradient(135deg, rgba(192,192,192,0.06), rgba(192,192,192,0.02))',
                'linear-gradient(135deg, rgba(205,127,50,0.06), rgba(205,127,50,0.02))',
              ]
              return (
                <div
                  key={pool.pairAddress}
                  className="border border-border rounded-lg px-3 py-2 hover:border-accent/30 transition-colors"
                  style={{ background: gradients[i] }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold">
                      {MEDALS[i]} {poolLabel(pool)}
                    </span>
                    <div className="text-right">
                      <div className="text-[10px] text-text-secondary font-mono">{fmtCompact(txns)}</div>
                      <div className="text-[8px] text-text-muted">txns</div>
                    </div>
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
          <div className="text-[9px] text-text-muted uppercase tracking-widest mb-2">Fees by DEX</div>
          <div className="space-y-2">
            {dexList.map(([dex, fees]) => {
              const pct = totalFees > 0 ? (fees / totalFees) * 100 : 0
              const color = DEX_COLORS[dex] ?? '#a0a0b0'
              return (
                <div key={dex} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] capitalize font-medium" style={{ color }}>{dex}</span>
                    <div className="text-right">
                      <span className="text-[11px] font-bold text-accent">{fmt(fees)}</span>
                      <span className="text-[9px] text-text-muted ml-1.5">{pct.toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="h-1 bg-bg-primary rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${pct}%`, background: color }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
