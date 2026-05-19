import type { Pool } from '@/lib/types'
import { fmt, fmtCompact, fmtPct } from '@/lib/formatters'
import { getVolume, getLiquidity, getEstimatedFees, getFeeRate, getBuyPct, buyPressureColor, poolLabel } from '@/lib/calculations'
import type { FeeRatesMap } from '@/lib/types'

interface PoolCardProps {
  pool: Pool
  feeRates: FeeRatesMap
  pinned?: boolean
  pinnedLabel?: string
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
  const feeLabelColor = feeLabel === 'HIGH' ? 'text-accent border-accent/30 bg-accent/10'
    : feeLabel === 'MID'  ? 'text-text-secondary border-border bg-bg-primary'
    : 'text-text-muted border-border bg-bg-primary'

  const hasFees = fees24h != null

  return (
    <div className={`bg-bg-card rounded-xl p-4 transition-all hover:border-accent/50 ${
      pinned ? 'border-2' : 'border'
    } ${hasFees ? 'border-accent/30' : 'border-border'}`}
      style={hasFees ? { boxShadow: '0 0 16px rgba(0,220,255,0.1), inset 0 0 12px rgba(0,220,255,0.03)' } : {}}>
      {pinned && pinnedLabel && (
        <div className="text-[8px] text-accent uppercase tracking-widest mb-2">{pinnedLabel}</div>
      )}
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-[12px] font-semibold">{poolLabel(pool)}</span>
          {feeLabel && (
            <span className={`ml-2 text-[8px] border px-1 py-0.5 rounded ${feeLabelColor}`}>{feeLabel}</span>
          )}
        </div>
        <span className="text-[10px] text-text-muted capitalize">{pool.dexId}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { l: 'Vol 24h', v: fmt(vol24h) },
          { l: 'Vol 6h',  v: fmt(vol6h) },
          { l: 'Txns 24h', v: fmtCompact(txns24) },
          { l: 'Liquidity', v: fmt(liq) },
          { l: 'Fee Rate', v: feeRate != null ? (feeRate * 100).toFixed(2) + '%' : '--' },
          { l: 'Buy %',    v: buyPct + '%' },
        ].map(({ l, v }) => (
          <div key={l} className="bg-bg-primary rounded-lg p-2 text-center">
            <div className="text-[8px] text-text-muted uppercase tracking-wide">{l}</div>
            <div className="text-[11px] font-semibold mt-0.5">{v}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 bg-bg-primary rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${buyPct}%`, background: buyPressureColor(buyPct) }} />
        </div>
        {fees24h != null && (
          <span className="text-[11px] font-semibold text-accent"
            style={{ textShadow: '0 0 8px rgba(0,220,255,0.5)' }}>
            {fmt(fees24h)}/day
          </span>
        )}
      </div>
    </div>
  )
}
