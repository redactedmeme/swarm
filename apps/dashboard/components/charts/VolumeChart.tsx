'use client'
import { useState } from 'react'
import { Bar } from 'react-chartjs-2'
import { Chart, BarElement, CategoryScale, LinearScale, Tooltip } from 'chart.js'
import { useDashboard } from '@/context/DashboardContext'
import { getMetricValue, poolLabel, PIE_COLORS } from '@/lib/calculations'
import type { ChartMetric } from '@/lib/types'

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip)

const METRICS: { key: ChartMetric; label: string }[] = [
  { key: 'volume24h', label: '24h Vol' },
  { key: 'volume6h',  label: '6h Vol' },
  { key: 'volume1h',  label: '1h Vol' },
  { key: 'liquidity', label: 'Liquidity' },
  { key: 'fees24h',   label: '24h Fees' },
]

export function VolumeChart() {
  const { poolsData, feeRatesMap } = useDashboard()
  const [metric, setMetric] = useState<ChartMetric>('volume24h')

  const top10 = [...poolsData]
    .sort((a, b) => getMetricValue(b, metric, feeRatesMap) - getMetricValue(a, metric, feeRatesMap))
    .slice(0, 10)

  const data = {
    labels: top10.map(p => poolLabel(p)),
    datasets: [{
      data: top10.map(p => getMetricValue(p, metric, feeRatesMap)),
      backgroundColor: PIE_COLORS.slice(0, top10.length),
      borderWidth: 0,
      borderRadius: 4,
    }],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0f0f0f',
        borderColor: '#1c1c1c',
        borderWidth: 1,
        titleColor: '#888',
        bodyColor: '#ececec',
        callbacks: {
          label: (ctx: { parsed: { y: number } }) => '$' + (ctx.parsed.y / 1000).toFixed(1) + 'K',
        },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#444', font: { size: 8 }, maxRotation: 30 } },
      y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#444', font: { size: 9 }, callback: (v: number | string) => '$' + (Number(v) / 1000).toFixed(0) + 'K' } },
    },
  }

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 mb-3">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <span className="text-[10px] text-text-muted uppercase tracking-widest">Volume by Pool</span>
        <div className="flex gap-1 flex-wrap">
          {METRICS.map(m => (
            <button key={m.key}
              onClick={() => setMetric(m.key)}
              className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${metric === m.key ? 'border-accent text-accent' : 'border-border text-text-muted hover:border-accent/50'}`}
            >{m.label}</button>
          ))}
        </div>
      </div>
      <div style={{ height: 200 }}>
        {top10.length > 0 ? (
          <Bar data={data} options={options as Parameters<typeof Bar>[0]['options']} />
        ) : (
          <div className="h-full flex items-center justify-center text-[11px] text-text-muted">Loading pools…</div>
        )}
      </div>
    </div>
  )
}
