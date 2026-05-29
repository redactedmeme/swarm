'use client'
import { useDashboard } from '@/context/DashboardContext'
import { fmt, fmtCompact } from '@/lib/formatters'
import { getEstimatedFees, getVolume, getLiquidity, buyPressureColor } from '@/lib/calculations'
import { InfoIcon } from '@/components/ui/Tooltip'
import { SkeletonCard } from '@/components/ui/Skeleton'

function StatBlock({
  label,
  value,
  sub,
  accent,
  tooltip,
  trend,
}: {
  label: string
  value: string
  sub?: string
  accent?: 'cyan' | 'bright' | 'pos'
  tooltip?: string
  trend?: 'up' | 'down' | 'flat'
}) {
  const valueClass = accent === 'cyan' ? 'text-accent' : accent === 'bright' ? 'text-accent-bright' : accent === 'pos' ? 'text-pos' : ''
  const trendEl = trend === 'up'
    ? <span className="text-pos text-[9px] ml-1">▲</span>
    : trend === 'down'
    ? <span className="text-neg text-[9px] ml-1">▼</span>
    : null

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 hover:border-accent/20 transition-colors">
      <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
        {label}
        {tooltip && <InfoIcon tooltip={tooltip} />}
      </div>
      <div className={`text-[17px] font-bold flex items-baseline ${valueClass}`}>
        {value}{trendEl}
      </div>
      {sub && <div className="text-[10px] text-text-secondary mt-0.5">{sub}</div>}
    </div>
  )
}

export function LeftColumn() {
  const { poolsData, serverSnapshots, feeRatesMap, loading } = useDashboard()

  if (loading && poolsData.length === 0) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} lines={2} />)}
      </div>
    )
  }

  const total24h   = poolsData.reduce((s, p) => s + getVolume(p, 'h24'), 0)
  const total6h    = poolsData.reduce((s, p) => s + getVolume(p, 'h6'),  0)
  const total1h    = poolsData.reduce((s, p) => s + getVolume(p, 'h1'),  0)
  const totalLiq   = poolsData.reduce((s, p) => s + getLiquidity(p), 0)
  const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
  const fees24h    = knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  const fees7d     = fees24h * 7
  const avgFeeRate = knownPools.length > 0
    ? knownPools.reduce((s, p) => s + (feeRatesMap[p.pairAddress] ?? 0), 0) / knownPools.length * 100
    : 0
  const feeApr     = totalLiq > 0 ? (fees24h * 365 / totalLiq) * 100 : 0

  const totalBuys  = poolsData.reduce((s, p) => s + (p.txns?.h24?.buys  ?? 0), 0)
  const totalSells = poolsData.reduce((s, p) => s + (p.txns?.h24?.sells ?? 0), 0)
  const totalTxns  = totalBuys + totalSells
  const buyPct     = totalTxns > 0 ? Math.round((totalBuys / totalTxns) * 100) : 50

  // Compute trend from recent snapshots (compare last two)
  const snaps = serverSnapshots
  const prevVol = snaps.length >= 2 ? snaps[snaps.length - 2].vol24h : null
  const curVol  = snaps.length >= 1 ? snaps[snaps.length - 1].vol24h : null
  const volTrend = prevVol && curVol
    ? curVol > prevVol * 1.02 ? 'up' : curVol < prevVol * 0.98 ? 'down' : 'flat'
    : undefined

  const pressureColor = buyPressureColor(buyPct)

  return (
    <div className="space-y-2 p-4">
      <StatBlock
        label="24h Volume"
        value={fmt(total24h)}
        sub={`${poolsData.length} pools active`}
        tooltip="Total rolling 24h volume across all tracked pools"
        trend={volTrend as 'up' | 'down' | 'flat' | undefined}
      />
      <StatBlock
        label="6h / 1h Volume"
        value={fmt(total6h)}
        sub={`1h: ${fmt(total1h)}`}
        tooltip="Short-term volume — useful for momentum signals"
      />
      <StatBlock
        label="Total Liquidity"
        value={fmt(totalLiq)}
        tooltip="Sum of USD liquidity across all AMM pools"
      />

      {/* Transactions + pressure */}
      <div className="bg-bg-card border border-border rounded-xl p-4 hover:border-accent/20 transition-colors">
        <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
          24h Transactions
          <InfoIcon tooltip="Buy + sell transactions in the last 24 hours" />
        </div>
        <div className="text-[17px] font-bold mb-1">{fmtCompact(totalTxns)}</div>
        <div className="text-[10px] mb-2">
          <span className="text-pos">{fmtCompact(totalBuys)} buys</span>
          <span className="text-text-muted"> / </span>
          <span className="text-neg">{fmtCompact(totalSells)} sells</span>
        </div>
        <div className="h-2 bg-bg-primary rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${buyPct}%`, background: pressureColor }}
          />
        </div>
        <div className="text-[9px] text-text-muted mt-1.5 flex justify-between">
          <span>Sell</span>
          <span style={{ color: pressureColor }} className="font-semibold">{buyPct}% buys</span>
          <span>Buy</span>
        </div>
      </div>

      <div className="h-px bg-border" />

      <StatBlock
        label="Est. 24h Fees"
        value={fmt(fees24h)}
        sub={`avg ${avgFeeRate.toFixed(2)}% · ${knownPools.length} pools`}
        accent="cyan"
        tooltip="Volume × fee rate per pool, summed across known-fee pools"
      />
      <StatBlock
        label="Est. 7d Fees"
        value={fmt(fees7d)}
        sub="projected from 24h rate"
        accent="bright"
        tooltip="7-day fee projection based on current 24h rate"
      />
      <StatBlock
        label="Fee APR (est.)"
        value={feeApr > 0 ? feeApr.toFixed(1) + '%' : '--'}
        sub={feeApr > 0 ? `${fmt(fees24h * 365)} annualised` : undefined}
        accent="pos"
        tooltip="Annualised fee yield relative to total liquidity"
      />
    </div>
  )
}
