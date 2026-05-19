'use client'
import { useDashboard } from '@/context/DashboardContext'
import { TokenIcon } from './TokenIcon'
import { fmt, fmtPct, fmtNum, pctClass } from '@/lib/formatters'
import { getEstimatedFees, getVolume, getLiquidity, volDotColor } from '@/lib/calculations'

function VolDot({ vol }: { vol: number }) {
  const { color, duration, title } = volDotColor(vol)
  return (
    <span
      title={title}
      className="inline-block rounded-full ml-1 align-middle animate-volPulse"
      style={{ width: 7, height: 7, background: color, animationDuration: duration }}
    />
  )
}

export function FlywheelCard() {
  const { poolsData, serverSnapshots, tokenData, v2Data, v1v2PoolData, feeRatesMap } = useDashboard()

  const v1Vol24h = poolsData.reduce((s, p) => s + getVolume(p, 'h24'), 0)
  const v1Liq    = poolsData.reduce((s, p) => s + getLiquidity(p), 0)
  const v1Price  = poolsData[0]?.priceUsd ? parseFloat(poolsData[0].priceUsd) : 0
  const v1Mcap   = poolsData[0]?.marketCap ?? poolsData[0]?.fdv ?? 0
  const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
  const fees24h  = knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)

  const v2Price  = v2Data.price  ?? 0
  const v2Mcap   = v2Data.mcap   ?? 0
  const v2Vol24h = v2Data.vol24h ?? 0
  const v2Ch24   = v2Data.priceChange?.h24
  const v2BuyPressure = v2Price > 0 ? fees24h / v2Price : null

  const v1PriceStr = v1Price ? '$' + v1Price.toFixed(v1Price < 0.01 ? 8 : 4) : '--'
  const v2PriceStr = v2Price ? '$' + v2Price.toFixed(v2Price < 0.01 ? 8 : 4) : '--'

  const orcaPrice = v1v2PoolData?.price ?? null
  const rawRatio  = orcaPrice ?? (v2Price > 0 && v1Price > 0 ? v1Price / v2Price : null)
  const ratioStr  = rawRatio == null ? '--'
    : rawRatio >= 1000 ? fmtNum(rawRatio) + ' REDACTED'
    : rawRatio >= 1    ? rawRatio.toFixed(4) + ' REDACTED'
    : (1 / rawRatio).toFixed(4) + ' REDACTED'

  const imageUrl = serverSnapshots.at(-1)?.image_url ?? tokenData.image_url ?? ''

  if (!v2Data.price) return null

  return (
    <div className="bg-bg-card border rounded-xl p-4 mb-3 relative overflow-hidden"
      style={{ borderColor: 'rgba(0,220,255,0.2)', boxShadow: '0 0 32px rgba(0,220,255,0.08)' }}>
      {/* gradient overlay */}
      <div className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(135deg, rgba(0,220,255,0.04) 0%, rgba(0,220,255,0.01) 100%)' }} />

      {/* header */}
      <div className="flex items-center justify-between mb-4 relative">
        <span className="text-[10px] text-text-muted uppercase tracking-widest">REDACTED Ecosystem</span>
        <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse2" />
      </div>

      {/* body: liq | flow | pump */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-center relative">

        {/* Liquidity token */}
        <div className="bg-white/[0.02] border border-border rounded-lg p-3 opacity-80">
          <div className="flex items-center gap-2 mb-3">
            <TokenIcon url={imageUrl} size={28} />
            <div>
              <div className="text-[11px] font-semibold flex items-center gap-1">
                REDACTED
                <span className="text-[9px] text-text-muted bg-bg-primary border border-border px-1 py-0.5 rounded">liquidity</span>
                {/* orange blinking dot for liquidity */}
                <span className="inline-block rounded-full ml-1 align-middle animate-blinkOrange" style={{ width: 7, height: 7 }} />
              </div>
              <div className="text-[8px] text-text-muted mt-0.5">9a21gb7f…KgnM</div>
            </div>
          </div>
          {[['Price', v1PriceStr], ['MCap', fmt(v1Mcap)], ['Vol 24h', fmt(v1Vol24h)], ['Liquidity', fmt(v1Liq)]].map(([l, v]) => (
            <div key={l} className="flex justify-between items-baseline mb-1">
              <span className="text-[9px] text-text-muted">{l}</span>
              <span className="text-[11px] font-semibold">{v}</span>
            </div>
          ))}
        </div>

        {/* Flow arrow */}
        <div className="flex flex-col items-center gap-2 px-3">
          {/* vol badge — orange indicator */}
          <div className="relative bg-white/[0.03] border border-border rounded-md px-2.5 py-1.5 text-center">
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full animate-blinkOrange" />
            <div className="text-[13px] font-bold text-text-primary">{fmt(v1Vol24h)}</div>
            <div className="text-[8px] text-text-muted mt-0.5">24H Vol</div>
          </div>
          {/* fee badge — green indicator */}
          <div className="relative rounded-md px-2.5 py-1.5 text-center"
            style={{ background: 'rgba(0,220,255,0.08)', border: '1px solid rgba(0,220,255,0.25)' }}>
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full animate-blinkGreen" />
            <div className="text-[14px] font-bold text-accent">{fmt(fees24h)}</div>
            <div className="text-[8px] text-text-muted mt-0.5">fees / day</div>
          </div>
          {/* animated arrow — green */}
          <div className="relative flex flex-col items-center" style={{ width: 36, height: 52 }}>
            <div className="relative overflow-hidden rounded-sm" style={{ width: 2, height: '100%', background: 'rgba(255,255,255,0.08)' }}>
              <div className="absolute animate-flowDown rounded-sm"
                style={{ left: -1, width: 4, height: '45%', background: 'linear-gradient(to bottom, transparent, rgba(0,220,255,0.9), rgba(0,220,255,0.4))', boxShadow: '0 0 12px rgba(0,220,255,0.7)' }} />
            </div>
            <div className="mt-0.5 animate-arrowPulse"
              style={{ width: 0, height: 0, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '8px solid #00ff88', filter: 'drop-shadow(0 0 4px rgba(0,255,136,0.8))' }} />
          </div>
          <div className="text-[9px] font-medium text-text-secondary text-center">buys REDACTED</div>
          {v2BuyPressure != null && (
            <div className="text-[9px] text-accent text-center">{fmtNum(v2BuyPressure)}<br />tokens/day</div>
          )}
        </div>

        {/* Pump / fees token — purple highlight */}
        <div className="rounded-lg p-3"
          style={{ border: '1px solid rgba(184,68,255,0.35)', background: 'rgba(184,68,255,0.05)', boxShadow: '0 0 16px rgba(184,68,255,0.1)' }}>
          <div className="flex items-center gap-2 mb-3">
            <TokenIcon url={v2Data.image_url} size={36} />
            <div>
              <div className="text-[13px] font-semibold flex items-center gap-1" style={{ color: '#b844ff' }}>
                REDACTED
                <span className="text-[9px] text-text-muted bg-bg-primary border border-border px-1 py-0.5 rounded">fees</span>
                {/* green blinking dot for fees token */}
                <span className="inline-block rounded-full ml-1 align-middle animate-blinkGreen" style={{ width: 7, height: 7 }} />
              </div>
              <div className="text-[8px] text-text-muted mt-0.5">9mtKd1o8…pump</div>
            </div>
          </div>
          {[
            ['Price', <span key="p" className={pctClass(v2Ch24)}>{v2PriceStr}</span>],
            ['MCap',  fmt(v2Mcap)],
            ['Vol 24h', fmt(v2Vol24h)],
            ['24h', <span key="ch" className={pctClass(v2Ch24)}>{fmtPct(v2Ch24)}</span>],
          ].map(([l, v]) => (
            <div key={String(l)} className="flex justify-between items-baseline mb-1">
              <span className="text-[9px] text-text-muted">{l}</span>
              <span className="text-[13px] font-semibold" style={{ color: '#b844ff' }}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* footer */}
      {(v1v2PoolData.tvl || ratioStr !== '--') && (
        <div className="mt-3 pt-3 border-t border-border flex justify-between items-center flex-wrap gap-2">
          {v1v2PoolData.tvl && (
            <div className="text-center">
              <div className="text-[9px] text-text-muted">Orca Pool TVL</div>
              <div className="text-[12px] font-semibold mt-0.5">{fmt(v1v2PoolData.tvl)}</div>
            </div>
          )}
          {ratioStr !== '--' && (
            <div className="text-center">
              <div className="text-[9px] text-text-muted">Exchange Rate</div>
              <div className="text-[12px] font-semibold mt-0.5">{ratioStr}</div>
            </div>
          )}
          {v1v2PoolData.vol24h && (
            <div className="text-center">
              <div className="text-[9px] text-text-muted">Pool Vol 24h</div>
              <div className="text-[12px] font-semibold mt-0.5">{fmt(v1v2PoolData.vol24h)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
