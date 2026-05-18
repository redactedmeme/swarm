export function fmt(n: number | null | undefined): string {
  if (n == null) return '--'
  if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B'
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K'
  return '$' + n.toFixed(2)
}

export function fmtCompact(n: number | null | undefined): string {
  if (n == null) return '--'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n.toFixed(0)
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null) return '--'
  const sign = n >= 0 ? '+' : ''
  return sign + n.toFixed(2) + '%'
}

export function fmtNum(n: number | null | undefined): string {
  if (n == null) return '--'
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export function fmtPrice(p: number): string {
  return '$' + p.toFixed(p < 0.01 ? 8 : 4)
}

export function pctClass(n: number | null | undefined): string {
  if (n == null) return 'text-text-secondary'
  return n >= 0 ? 'text-pos' : 'text-neg'
}

export function truncate(addr: string, chars = 4): string {
  if (addr.length <= chars * 2 + 3) return addr
  return addr.slice(0, chars) + '…' + addr.slice(-chars)
}
