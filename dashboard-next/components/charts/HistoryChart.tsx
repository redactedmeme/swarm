'use client'
import { useState, useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { Chart, LineElement, PointElement, LinearScale, TimeScale, Tooltip, Filler, CategoryScale } from 'chart.js'
import { useDashboard } from '@/context/DashboardContext'
import { getEstimatedFees } from '@/lib/calculations'
import type { HistoryRange } from '@/lib/types'
import { fmt } from '@/lib/formatters'

Chart.register(LineElement, PointElement, LinearScale, TimeScale, Tooltip, Filler, CategoryScale)

const RANGES: { key: HistoryRange; label: string; seconds: number }[] = [
  { key: '1h',  label: '1H',  seconds: 3600 },
  { key: '6h',  label: '6H',  seconds: 21600 },
  { key: '24h', label: '24H', seconds: 86400 },
  { key: '7d',  label: '7D',  seconds: 604800 },
]

function formatLabel(ts: number, range: HistoryRange): string {
  const d = new Date(ts * 1000)
  if (range === '1h' || range === '6h') {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  if (range === '24h') {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

type ActiveDataset = 'vol' | 'liq' | 'fees'

export function HistoryChart() {
  const { serverSnapshots, clientSnapshots, poolsData, feeRatesMap } = useDashboard()
  const [range, setRange] = useState<HistoryRange>('24h')
  const [active, setActive] = useState<Set<ActiveDataset>>(new Set<ActiveDataset>(['vol', 'liq']))

  const snaps = serverSnapshots.length >= 2 ? serverSnapshots : clientSnapshots
  const now = Date.now() / 1000
  const cutoffSeconds = RANGES.find(r => r.key === range)?.seconds ?? 86400
  const filtered = snaps.filter(s => s.ts >= now - cutoffSeconds)

  const fees24h = useMemo(() => {
    const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
    return knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  }, [poolsData, feeRatesMap])

  const labels  = filtered.map(s => formatLabel(s.ts, range))
  const vol     = filtered.map(s => s.vol24h)
  const liq     = filtered.map(s => s.liq)
  const lastVol = filtered.at(-1)?.vol24h || 1
  const fees    = filtered.map(s => (s.vol24h > 0 ? fees24h * (s.vol24h / lastVol) : 0) * 10)

  type DS = {
    label: string; data: number[]; borderColor: string; backgroundColor: string
    fill: boolean; tension: number; pointRadius: number; pointHoverRadius: number
    borderWidth: number; borderDash?: number[]
  }

  const datasets: DS[] = []
  if (active.has('vol')) datasets.push({
    label: '24h Vol', data: vol, borderColor: '#ff9d00',
    backgroundColor: 'rgba(255,157,0,0.07)', fill: true, tension: 0.4,
    pointRadius: 0, pointHoverRadius: 4, borderWidth: 1.5,
  })
  if (active.has('liq')) datasets.push({
    label: 'Liquidity', data: liq, borderColor: '#00ff88',
    backgroundColor: 'rgba(0,255,136,0.05)', fill: true, tension: 0.4,
    pointRadius: 0, pointHoverRadius: 4, borderWidth: 1.5,
  })
  if (active.has('fees')) datasets.push({
    label: 'Fees ×10', data: fees, borderColor: '#00dcff',
    backgroundColor: 'rgba(0,220,255,0.05)', fill: false, tension: 0.4,
    pointRadius: 0, pointHoverRadius: 4, borderWidth: 1.5, borderDash: [5, 4],
  })

  const chartData = { labels, datasets }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(10,10,15,0.95)',
        borderColor: '#242430',
        borderWidth: 1,
        titleColor: '#606070',
        bodyColor: '#f0f0f7',
        padding: 10,
        callbacks: {
          label: (ctx: { dataset: { label?: string }; parsed: { y: number } }) =>
            ` ${ctx.dataset.label}: ${fmt(ctx.parsed.y)}`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.03)' },
        ticks: { color: '#444', font: { size: 9 }, maxTicksLimit: 6 },
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.03)' },
        ticks: {
          color: '#444',
          font: { size: 9 },
          callback: (v: number | string) => {
            const n = Number(v)
            if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(1) + 'M'
            if (n >= 1_000) return '$' + (n / 1_000).toFixed(0) + 'K'
            return '$' + n.toFixed(0)
          },
        },
      },
    },
  }

  function toggleDataset(key: ActiveDataset) {
    setActive(prev => {
      const next = new Set(prev)
      if (next.has(key)) { next.delete(key) } else { next.add(key) }
      return next
    })
  }

  const legendItems: { key: ActiveDataset; label: string; color: string }[] = [
    { key: 'vol',  label: '24h Vol',    color: '#ff9d00' },
    { key: 'liq',  label: 'Liquidity',  color: '#00ff88' },
    { key: 'fees', label: 'Fees ×10',   color: '#00dcff' },
  ]

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4">
      {/* Header row */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-text-muted uppercase tracking-widest">Volume History</span>
          {/* Legend toggles */}
          <div className="flex gap-2">
            {legendItems.map(({ key, label, color }) => (
              <button
                key={key}
                onClick={() => toggleDataset(key)}
                className={`flex items-center gap-1 text-[9px] transition-opacity ${active.has(key) ? 'opacity-100' : 'opacity-30'}`}
              >
                <span className="w-2.5 h-0.5 rounded-full inline-block" style={{ background: color }} />
                <span className="text-text-muted">{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Time range buttons */}
        <div className="flex gap-1">
          {RANGES.map(r => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                range === r.key
                  ? 'border-accent text-accent bg-accent/5'
                  : 'border-border text-text-muted hover:border-accent/50'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ height: 180 }}>
        {filtered.length > 1 ? (
          <Line data={chartData} options={options as Parameters<typeof Line>[0]['options']} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-text-muted">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            <span className="text-[11px]">Collecting data… refresh in 30s</span>
          </div>
        )}
      </div>
    </div>
  )
}
