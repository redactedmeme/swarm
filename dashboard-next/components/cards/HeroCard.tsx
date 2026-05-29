'use client'
import { useDashboard } from '@/context/DashboardContext'
import { TokenIcon } from './TokenIcon'
import { fmt, fmtCompact, fmtPct, pctClass, fmtPrice } from '@/lib/formatters'
import { getEstimatedFees, getVolume, getLiquidity, getBuyPct, buyPressureColor } from '@/lib/calculations'
import { InfoIcon } from '@/components/ui/Tooltip'
import { SkeletonCard } from '@/components/ui/Skeleton'

function TrendArrow({ value }: { value: number | null | undefined }) {
  if (value == null) return null
  if (value > 0) return <span className="text-pos text-[10px]">▲</span>
  if (value < 0) return <span className="text-neg text-[10px]">▼</span>
  return <span className="text-text-muted text-[10px]">—</span>
}

function PriceChangePill({ label, value }: { label: string; value: number | null | undefined }) {
  const cls = pctClass(value ?? null)
  return (
    <div className="flex-1 text-center bg-bg-primary border border-border rounded-lg px-2 py-2 hover:border-accent/30 transition-colors">
      <div className="text-[8px] text-text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-[12px] font-bold flex items-center justify-center gap-1 ${cls}`}>
        <TrendArrow value={value} />
        {fmtPct(value ?? null)}
      </div>
    </div>
  )
}

export function HeroCard() {
  const { poolsData, serverSnapshots, tokenData, feeRatesMap, loading } = useDashboard()

  if (loading && poolsData.length === 0) return <SkeletonCard lines={6} />

  const total24h   = poolsData.reduce((s, p) => s + getVolume(p, 'h24'), 0)
  const totalLiq   = poolsData.reduce((s, p) => s + getLiquidity(p), 0)
  const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
  const fees24h    = knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  const fees7d     = fees24h * 7
  const feeApr     = totalLiq > 0 ? (fees24h * 365 / totalLiq) * 100 : 0

  const price         = poolsData[0]?.priceUsd ? parseFloat(poolsData[0].priceUsd) : 0
  const marketCap     = poolsData[0]?.marketCap ?? poolsData[0]?.fdv ?? 0
  const priceChange   = poolsData[0]?.priceChange?.h24 ?? null
  const priceChange1h = poolsData[0]?.priceChange?.h1 ?? null
  const priceChange6h = poolsData[0]?.priceChange?.h6 ?? null

  const totalBuys24  = poolsData.reduce((s, p) => s + (p.txns?.h24?.buys  ?? 0), 0)
  const totalSells24 = poolsData.reduce((s, p) => s + (p.txns?.h24?.sells ?? 0), 0)
  const totalTxns24  = totalBuys24 + totalSells24
  const buyPct       = totalTxns24 > 0 ? Math.round((totalBuys24 / totalTxns24) * 100) : 50
  const imageUrl     = serverSnapshots.at(-1)?.image_url ?? tokenData.image_url ?? ''

  const pressureColor = buyPressureColor(buyPct)

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 animate-fadeIn">

      {/* Token identity row */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <TokenIcon url={imageUrl} size={36} />
          <div>
            <div className="text-[14px] font-bold tracking-wide">REDACTED</div>
            <div className="text-[9px] text-text-muted uppercase tracking-widest">Liquidity Token · Solana</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1">Price</div>
          <div className="text-[18px] font-bold tabular-nums" style={{ letterSpacing: '-0.5px' }}>
            {price ? fmtPrice(price) : '--'}
          </div>
          <div className={`text-[10px] flex items-center justify-end gap-1 mt-0.5 ${pctClass(priceChange)}`}>
            <TrendArrow value={priceChange} />
            {fmtPct(priceChange)} 24h
          </div>
        </div>
      </div>

      {/* Key metrics hero row */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-bg-primary border border-border rounded-xl p-3 hover:border-accent/20 transition-colors">
          <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
            Market Cap <InfoIcon tooltip="Fully diluted market cap from DexScreener" />
          </div>
          <div className="text-[15px] font-bold">{fmt(marketCap)}</div>
        </div>
        <div className="bg-bg-primary border border-border rounded-xl p-3 hover:border-accent/20 transition-colors">
          <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
            24h Volume <InfoIcon tooltip="Aggregated 24h volume across all AMM pools" />
          </div>
          <div className="text-[15px] font-bold">{fmt(total24h)}</div>
        </div>
        <div className="bg-bg-primary border border-border rounded-xl p-3 hover:border-accent/20 transition-colors">
          <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
            Liquidity <InfoIcon tooltip="Total USD liquidity across all pools" />
          </div>
          <div className="text-[15px] font-bold">{fmt(totalLiq)}</div>
        </div>
      </div>

      {/* Fees row */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-bg-primary border border-accent/20 rounded-xl p-3" style={{ boxShadow: '0 0 12px rgba(0,220,255,0.06)' }}>
          <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
            Fees 24h <InfoIcon tooltip="Estimated fees: pool volume × fee rate" />
          </div>
          <div className="text-[15px] font-bold text-accent">{fmt(fees24h)}</div>
        </div>
        <div className="bg-bg-primary border border-accent/20 rounded-xl p-3" style={{ boxShadow: '0 0 12px rgba(0,220,255,0.06)' }}>
          <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5">
            Fees 7d (est.)
          </div>
          <div className="text-[15px] font-bold text-accent-bright">{fmt(fees7d)}</div>
        </div>
        <div className="bg-bg-primary border border-border rounded-xl p-3">
          <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1.5 flex items-center gap-1">
            Fee APR <InfoIcon tooltip="Annualised fee yield on total liquidity" />
          </div>
          <div className="text-[15px] font-bold text-pos">{feeApr > 0 ? feeApr.toFixed(1) + '%' : '--'}</div>
        </div>
      </div>

      {/* Buy / sell pressure */}
      <div className="bg-bg-primary border border-border rounded-xl p-3 mb-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] text-text-muted uppercase tracking-widest">Buy Pressure</span>
          <div className="flex items-center gap-3 text-[10px]">
            <span className="text-pos">{fmtCompact(totalBuys24)} buys</span>
            <span className="text-text-muted">/</span>
            <span className="text-neg">{fmtCompact(totalSells24)} sells</span>
            <span className="text-text-muted">·</span>
            <span className="text-text-secondary font-semibold">{fmtCompact(totalTxns24)} total</span>
          </div>
        </div>
        <div className="h-2 bg-bg-card rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${buyPct}%`, background: pressureColor }}
          />
        </div>
        <div className="flex justify-between mt-1.5 text-[9px] text-text-muted">
          <span>Sell</span>
          <span className="font-semibold" style={{ color: pressureColor }}>{buyPct}% buys</span>
          <span>Buy</span>
        </div>
      </div>

      {/* Price change pills */}
      <div className="flex gap-2 mb-3">
        <PriceChangePill label="1H" value={priceChange1h} />
        <PriceChangePill label="6H" value={priceChange6h} />
        <PriceChangePill label="24H" value={priceChange} />
      </div>

      {/* Security section */}
      {(tokenData.holder_count || tokenData.top10_pct != null || tokenData.mint_authority_revoked != null) && (
        <div className="pt-3 border-t border-border">
          <div className="text-[9px] text-text-muted uppercase tracking-widest mb-2 flex items-center gap-1">
            Token Security
            <InfoIcon tooltip="On-chain security data from Solana token metadata" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {tokenData.holder_count != null && (
              <div className="bg-bg-primary border border-border rounded-lg p-2.5">
                <div className="text-[8px] text-text-muted mb-1">Holders</div>
                <div className="text-[13px] font-semibold">
                  {fmtCompact(tokenData.holder_count)}{tokenData.holder_count_capped ? '+' : ''}
                </div>
              </div>
            )}
            {tokenData.top10_pct != null && (
              <div className="bg-bg-primary border border-border rounded-lg p-2.5">
                <div className="text-[8px] text-text-muted mb-1">Top 10 Hold</div>
                <div className={`text-[13px] font-semibold ${tokenData.top10_pct > 50 ? 'text-neg' : tokenData.top10_pct > 30 ? 'text-amber' : 'text-pos'}`}>
                  {tokenData.top10_pct}%
                </div>
              </div>
            )}
            {tokenData.mint_authority_revoked != null && (
              <div className={`bg-bg-primary border rounded-lg p-2.5 ${tokenData.mint_authority_revoked ? 'border-pos/30' : 'border-neg/40'}`}>
                <div className="text-[8px] text-text-muted mb-1">Mint Auth</div>
                <div className={`text-[11px] font-semibold ${tokenData.mint_authority_revoked ? 'text-pos' : 'text-neg'}`}>
                  {tokenData.mint_authority_revoked ? '✓ Revoked' : '⚠ Active'}
                </div>
              </div>
            )}
            {tokenData.freeze_authority_revoked != null && (
              <div className={`bg-bg-primary border rounded-lg p-2.5 ${tokenData.freeze_authority_revoked ? 'border-pos/30' : 'border-neg/40'}`}>
                <div className="text-[8px] text-text-muted mb-1">Freeze Auth</div>
                <div className={`text-[11px] font-semibold ${tokenData.freeze_authority_revoked ? 'text-pos' : 'text-neg'}`}>
                  {tokenData.freeze_authority_revoked ? '✓ Revoked' : '⚠ Active'}
                </div>
              </div>
            )}
          </div>
          {poolsData.length > 0 && (
            <div className="mt-2 text-[9px] text-text-muted text-right">{poolsData.length} AMM pools tracked</div>
          )}
        </div>
      )}
    </div>
  )
}
