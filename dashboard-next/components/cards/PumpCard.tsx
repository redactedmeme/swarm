'use client'
import { useDashboard } from '@/context/DashboardContext'
import { TokenIcon } from './TokenIcon'
import { fmt, fmtPct, pctClass } from '@/lib/formatters'

export function PumpCard() {
  const { v2Data } = useDashboard()
  if (!v2Data.price) return null

  const price   = v2Data.price
  const priceStr = '$' + price.toFixed(price < 0.01 ? 8 : 4)
  const ch24 = v2Data.priceChange?.h24
  const ch1  = v2Data.priceChange?.h1

  const stats = [
    { label: 'Market Cap', value: fmt(v2Data.mcap) },
    { label: '24h Volume', value: fmt(v2Data.vol24h) },
    { label: 'Liquidity',  value: fmt(v2Data.liq) },
    { label: '1h Change',  value: fmtPct(ch1),  cls: pctClass(ch1) },
    { label: '6h Volume',  value: fmt(v2Data.vol6h) },
    { label: 'Pools',      value: String(v2Data.pools ?? '--') },
  ]

  return (
    <div className="bg-bg-card border rounded-xl p-4 mb-3"
      style={{ borderColor: 'rgba(184,147,74,0.2)', boxShadow: '0 0 20px rgba(184,147,74,0.06)' }}>
      {/* top row */}
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center"
          style={{ background: 'rgba(184,147,74,0.12)' }}>
          <TokenIcon url={v2Data.image_url} size={36} />
        </div>
        <div>
          <div className="text-sm font-bold text-accent leading-tight">
            REDACTED <span className="text-[10px] font-normal text-text-muted">fees token</span>
          </div>
          <div className="text-[9px] text-text-muted mt-0.5">9mtKd1o8…pump</div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-lg font-bold text-accent">{priceStr}</div>
          <div className={`text-[10px] mt-0.5 ${pctClass(ch24)}`}>{fmtPct(ch24)} 24h</div>
        </div>
      </div>

      {/* stats grid */}
      <div className="grid grid-cols-3 gap-2">
        {stats.map(({ label, value, cls }) => (
          <div key={label} className="rounded-lg px-2.5 py-2"
            style={{ background: 'rgba(184,147,74,0.03)', border: '1px solid rgba(184,147,74,0.08)' }}>
            <div className="text-[9px] text-text-muted uppercase tracking-wide mb-1">{label}</div>
            <div className={`text-[13px] font-semibold ${cls ?? 'text-text-primary'}`}>{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
