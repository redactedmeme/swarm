import type { Pool, FeeRatesMap } from './types'

export const MANUAL_FEE_OVERRIDES: FeeRatesMap = {
  'BeMzNX5hMFQxc29odj4nAvaBw16zvxgSStFbFgG7SQhY': 0.01,
  '7YhtV5K7Cg1GTz2GAfzrwBpgX6haY6sHodsFrSpif1eh': 0.01,
  'HjfUNoFr2FY419vn2262qZ532dA2cSGMrD8skSak5J49': 0.01,
  '6rxMikVZW4kjNDXcUZYM9ix8CtirdL21Mnhi5kNgmxMm': 0.01,
}

export const V1V2_POOL = '8Jd4KxLXhSqJx3wx7WRujfLZ7hmddVQkoM4qJqg4cPHo'
export const METEORA_DLMM_POOL = '7YhtV5K7Cg1GTz2GAfzrwBpgX6haY6sHodsFrSpif1eh'

export const TOKEN = '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM'
export const PUMP_TOKEN = '9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump'

export function getVolume(p: Pool, key: 'h24' | 'h6' | 'h1'): number {
  return p.volume?.[key] ?? 0
}

export function getLiquidity(p: Pool): number {
  return p.liquidity?.usd ?? 0
}

export function getFeeRate(p: Pool, feeRates: FeeRatesMap): number | null {
  return feeRates[p.pairAddress] ?? null
}

export function getEstimatedFees(p: Pool, period: 'h24' | 'h6' | 'h1', feeRates: FeeRatesMap): number | null {
  const rate = getFeeRate(p, feeRates)
  if (rate == null) return null
  return getVolume(p, period) * rate
}

export function getMetricValue(p: Pool, metric: string, feeRates: FeeRatesMap): number {
  switch (metric) {
    case 'volume24h': return getVolume(p, 'h24')
    case 'volume6h':  return getVolume(p, 'h6')
    case 'volume1h':  return getVolume(p, 'h1')
    case 'liquidity': return getLiquidity(p)
    case 'fees24h':   return getEstimatedFees(p, 'h24', feeRates) ?? 0
    default:          return 0
  }
}

export function getFlameLevel(p: Pool): 0 | 1 | 2 | 3 {
  const txns = (p.txns?.h24?.buys ?? 0) + (p.txns?.h24?.sells ?? 0)
  if (txns >= 1000) return 3
  if (txns >= 500)  return 2
  if (txns >= 100)  return 1
  return 0
}

export function getBuyPct(p: Pool): number {
  const buys  = p.txns?.h24?.buys  ?? 0
  const sells = p.txns?.h24?.sells ?? 0
  const total = buys + sells
  return total > 0 ? Math.round((buys / total) * 100) : 50
}

export function buyPressureColor(pct: number): string {
  if (pct >= 60) return '#4a9e6b'
  if (pct <= 40) return '#a85050'
  return '#b8934a'
}

export function poolLabel(p: Pool): string {
  return `${p.baseToken?.symbol ?? '?'}/${p.quoteToken?.symbol ?? '?'}`
}

export function volDotColor(vol: number): { color: string; duration: string; title: string } {
  if (vol >= 100000) return { color: '#4a9e6b', duration: '0.7s', title: 'High volume' }
  if (vol >= 10000)  return { color: '#b8934a', duration: '1.2s', title: 'Active' }
  if (vol >= 1000)   return { color: '#888888', duration: '2s',   title: 'Low volume' }
  return { color: '#333333', duration: '4s', title: 'Inactive' }
}

export const PIE_COLORS = [
  '#b8934a', '#4a9e6b', '#c8c8c8', '#a85050', '#7a7a7a',
  '#8a7a5a', '#6a8a6a', '#9a8060', '#5a5a5a', '#d4aa62',
  '#3a6a4a', '#7a5040', '#aaa060', '#507060', '#806040',
]
