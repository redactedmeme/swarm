'use client'
import { useState, useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { Chart, LineElement, PointElement, LinearScale, TimeScale, Tooltip, Filler, CategoryScale } from 'chart.js'
import { useDashboard } from '@/context/DashboardContext'
import { getEstimatedFees } from '@/lib/calculations'
import type { HistoryRange } from '@/lib/types'

Chart.register(LineElement, PointElement, LinearScale, TimeScale, Tooltip, Filler, CategoryScale)

export function HistoryChart() {
  const { serverSnapshots, clientSnapshots, poolsData, feeRatesMap } = useDashboard()
  const [range, setRange] = useState<HistoryRange>('24h')

  const snaps = serverSnapshots.length >= 2 ? serverSnapshots : clientSnapshots
  const now = Date.now() / 1000
  const cutoff = range === '24h' ? now - 86400 : now - 604800
  const filtered = snaps.filter(s => s.ts >= cutoff)

  const fees24h = useMemo(() => {
    const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
    return knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  }, [poolsData, feeRatesMap])

  const labels  = filtered.map(s => new Date(s.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
  const vol     = filtered.map(s => s.vol24h)
  const liq     = filtered.map(s => s.liq)
  const fees    = filtered.map(s => (s.vol24h > 0 ? fees24h * (s.vol24h / (filtered[filtered.length-1]?.vol24h || 1)) : 0) * 10)

  const data = {
    labels,
    datasets: [
      {
        label: '24h Vol',
        data: vol,
        borderColor: '#b8934a',
        backgroundColor: 'rgba(184,147,74,0.08)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1.5,
      },
      {
        label: 'Liquidity',
        data: liq,
        borderColor: '#4a9e6b',
        backgroundColor: 'rgba(74,158,107,0.05)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1.5,
      },
      {
        label: 'Fees ×10',
        data: fees,
        borderColor: '#6b6b6b',
        backgroundColor: 'rgba(107,107,107,0.05)',
        fill: false,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1,
        borderDash: [4, 4],
      },
    ],
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
          label: (ctx: { dataset: { label?: string }; parsed: { y: number } }) =>
            `${ctx.dataset.label}: $${(ctx.parsed.y / 1000).toFixed(1)}K`,
        },
      },
    },
    scales: {
      x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#444', font: { size: 9 }, maxTicksLimit: 6 } },
      y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#444', font: { size: 9 }, callback: (v: number | string) => '$' + (Number(v) / 1000).toFixed(0) + 'K' } },
    },
  }

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 mb-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] text-text-muted uppercase tracking-widest">Volume History</span>
        <div className="flex gap-1">
          {(['24h', '1w'] as HistoryRange[]).map(r => (
            <button key={r}
              onClick={() => setRange(r)}
              className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${range === r ? 'border-accent text-accent' : 'border-border text-text-muted hover:border-accent/50'}`}
            >{r}</button>
          ))}
        </div>
      </div>
      <div style={{ height: 160 }}>
        {filtered.length > 1 ? (
          <Line data={data} options={options as Parameters<typeof Line>[0]['options']} />
        ) : (
          <div className="h-full flex items-center justify-center text-[11px] text-text-muted">
            Collecting data… refresh in 30s
          </div>
        )}
      </div>
    </div>
  )
}
