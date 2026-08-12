'use client'
import { useDashboard } from '@/context/DashboardContext'
import { TokenIcon } from './TokenIcon'
import { fmt, fmtCompact, fmtPct, pctClass } from '@/lib/formatters'
import { getEstimatedFees, getVolume, getLiquidity, getBuyPct, buyPressureColor } from '@/lib/calculations'

export function HeroCard() {
  const { poolsData, serverSnapshots, tokenData, feeRatesMap } = useDashboard()

  const total24h   = poolsData.reduce((s, p) => s + getVolume(p, 'h24'), 0)
  const total6h    = poolsData.reduce((s, p) => s + getVolume(p, 'h6'),  0)
  const total1h    = poolsData.reduce((s, p) => s + getVolume(p, 'h1'),  0)
  const totalLiq   = poolsData.reduce((s, p) => s + getLiquidity(p), 0)
  const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
  const fees24h    = knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  const fees7d     = fees24h * 7

  const price       = poolsData[0]?.priceUsd ? parseFloat(poolsData[0].priceUsd) : 0
  const priceStr    = price ? '$' + price.toFixed(price < 0.01 ? 8 : 4) : '--'
  const marketCap   = poolsData[0]?.marketCap ?? poolsData[0]?.fdv ?? 0
  const priceChange = poolsData[0]?.priceChange?.h24 ?? null
  const priceChange1h = poolsData[0]?.priceChange?.h1 ?? null
  const priceChange6h = poolsData[0]?.priceChange?.h6 ?? null

  const totalBuys24  = poolsData.reduce((s, p) => s + (p.txns?.h24?.buys  ?? 0), 0)
  const totalSells24 = poolsData.reduce((s, p) => s + (p.txns?.h24?.sells ?? 0), 0)
  const totalTxns24  = totalBuys24 + totalSells24
  const buyPct       = totalTxns24 > 0 ? Math.round((totalBuys24 / totalTxns24) * 100) : 50
  const imageUrl     = serverSnapshots.at(-1)?.image_url ?? tokenData.image_url ?? ''

  const avgFeeRate   = knownPools.length > 0
    ? knownPools.reduce((s, p) => s + (feeRatesMap[p.pairAddress] ?? 0), 0) / knownPools.length * 100
    : 0
  const feeApr       = totalLiq > 0 ? (fees24h * 365 / totalLiq) * 100 : 0

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 mb-3">
      {/* token identity */}
      <div className="flex items-center gap-3 mb-3">
        <TokenIcon url={imageUrl} size={32} />
        <div>
          <div className="text-sm font-semibold">REDACTED</div>
          <div className="text-[9px] text-text-muted">Liquidity Token</div>
        </div>
      </div>

      {/* price + mcap */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="bg-bg-primary border border-border rounded-lg p-3">
          <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1">Market Cap</div>
          <div className="text-lg font-bold">{fmt(marketCap)}</div>
        </div>
        <div className="bg-bg-primary border border-border rounded-lg p-3">
          <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1">Price</div>
          <div className="text-lg font-bold">{priceStr}</div>
          <div className={`text-[10px] mt-0.5 ${pctClass(priceChange)}`}>{fmtPct(priceChange)} (24h)</div>
        </div>
      </div>

      {/* vol / liq / pools */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { l: '24H Vol', v: fmt(total24h) },
          { l: 'Liquidity', v: fmt(totalLiq) },
          { l: 'AMM Pools', v: String(poolsData.length) },
        ].map(({ l, v }) => (
          <div key={l} className="text-center">
            <div className="text-[9px] text-text-muted uppercase tracking-wide">{l}</div>
            <div className="text-sm font-semibold mt-0.5">{v}</div>
          </div>
        ))}
      </div>

      <div className="border-t border-border pt-3 mb-3">
        <div className="grid grid-cols-3 gap-2">
          {[
            { l: 'Est. 24h Fees', v: fmt(fees24h), cls: 'text-accent' },
            { l: 'Est. 7d Fees',  v: fmt(fees7d),  cls: 'text-accent-bright' },
            { l: '24h Txns',      v: fmtCompact(totalTxns24) },
          ].map(({ l, v, cls }) => (
            <div key={l} className="text-center">
              <div className="text-[9px] text-text-muted uppercase tracking-wide">{l}</div>
              <div className={`text-sm font-semibold mt-0.5 ${cls ?? ''}`}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* buy pressure */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] text-pos">{fmtCompact(totalBuys24)}B</span>
        <span className="text-text-muted text-[10px]">/</span>
        <span className="text-[10px] text-neg">{fmtCompact(totalSells24)}S</span>
        <div className="flex-1 h-1 bg-bg-primary rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all"
            style={{ width: `${buyPct}%`, background: buyPressureColor(buyPct) }} />
        </div>
        <span className="text-[10px] text-text-muted">{buyPct}% buys</span>
      </div>

      {/* price change pills */}
      <div className="flex gap-2">
        {[['1H', priceChange1h], ['6H', priceChange6h], ['24H', priceChange]].map(([label, val]) => (
          <div key={String(label)} className="flex-1 text-center bg-bg-primary border border-border rounded px-2 py-1">
            <div className="text-[8px] text-text-muted">{label}</div>
            <div className={`text-[11px] font-semibold ${pctClass(val as number)}`}>{fmtPct(val as number)}</div>
          </div>
        ))}
      </div>

      {/* security */}
      {(tokenData.holder_count || tokenData.top10_pct) && (
        <div className="mt-3 pt-3 border-t border-border">
          <div className="text-[9px] text-text-muted uppercase tracking-widest mb-2">Token Security</div>
          <div className="grid grid-cols-2 gap-2">
            {tokenData.holder_count != null && (
              <div className="bg-bg-primary border border-border rounded-lg p-2">
                <div className="text-[8px] text-text-muted">Holders</div>
                <div className="text-[12px] font-semibold mt-0.5">
                  {fmtCompact(tokenData.holder_count)}{tokenData.holder_count_capped ? '+' : ''}
                </div>
              </div>
            )}
            {tokenData.top10_pct != null && (
              <div className="bg-bg-primary border border-border rounded-lg p-2">
                <div className="text-[8px] text-text-muted">Top 10 Hold</div>
                <div className="text-[12px] font-semibold mt-0.5">{tokenData.top10_pct}%</div>
              </div>
            )}
            {tokenData.mint_authority_revoked != null && (
              <div className={`bg-bg-primary border rounded-lg p-2 ${tokenData.mint_authority_revoked ? 'border-pos/30' : 'border-neg/30'}`}>
                <div className="text-[8px] text-text-muted">Mint Auth</div>
                <div className={`text-[11px] font-semibold mt-0.5 ${tokenData.mint_authority_revoked ? 'text-pos' : 'text-neg'}`}>
                  {tokenData.mint_authority_revoked ? '✓ Revoked' : '⚠ Active'}
                </div>
              </div>
            )}
            {tokenData.freeze_authority_revoked != null && (
              <div className={`bg-bg-primary border rounded-lg p-2 ${tokenData.freeze_authority_revoked ? 'border-pos/30' : 'border-neg/30'}`}>
                <div className="text-[8px] text-text-muted">Freeze Auth</div>
                <div className={`text-[11px] font-semibold mt-0.5 ${tokenData.freeze_authority_revoked ? 'text-pos' : 'text-neg'}`}>
                  {tokenData.freeze_authority_revoked ? '✓ Revoked' : '⚠ Active'}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
