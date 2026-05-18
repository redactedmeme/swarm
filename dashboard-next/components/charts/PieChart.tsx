'use client'
import { Doughnut } from 'react-chartjs-2'
import { Chart, ArcElement, Tooltip, Legend } from 'chart.js'
import { useDashboard } from '@/context/DashboardContext'
import { getEstimatedFees, poolLabel, PIE_COLORS } from '@/lib/calculations'
import { fmt } from '@/lib/formatters'

Chart.register(ArcElement, Tooltip, Legend)

export function PieChart() {
  const { poolsData, feeRatesMap } = useDashboard()

  const withFees = poolsData
    .map(p => ({ p, fees: getEstimatedFees(p, 'h24', feeRatesMap) ?? 0 }))
    .filter(x => x.fees > 0)
    .sort((a, b) => b.fees - a.fees)
    .slice(0, 15)

  if (withFees.length === 0) return null

  const data = {
    labels: withFees.map(x => poolLabel(x.p)),
    datasets: [{
      data: withFees.map(x => x.fees),
      backgroundColor: PIE_COLORS.slice(0, withFees.length),
      borderWidth: 1,
      borderColor: '#080808',
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
          label: (ctx: { label?: string; parsed: number }) =>
            `${ctx.label}: ${fmt(ctx.parsed)}`,
        },
      },
    },
    cutout: '65%',
  }

  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 mb-3">
      <div className="text-[10px] text-text-muted uppercase tracking-widest mb-3">Fee Distribution</div>
      <div style={{ height: 220 }}>
        <Doughnut data={data} options={options as Parameters<typeof Doughnut>[0]['options']} />
      </div>
    </div>
  )
}
