import { Header } from '@/components/layout/Header'
import { LeftColumn } from '@/components/layout/LeftColumn'
import { RightColumn } from '@/components/layout/RightColumn'
import { FlywheelCard } from '@/components/cards/FlywheelCard'
import { PumpCard } from '@/components/cards/PumpCard'
import { HeroCard } from '@/components/cards/HeroCard'
import { HistoryChart } from '@/components/charts/HistoryChart'
import { VolumeChart } from '@/components/charts/VolumeChart'
import { PieChart } from '@/components/charts/PieChart'
import { PoolGrid } from '@/components/pools/PoolGrid'
import { MobileStats } from '@/components/layout/MobileStats'

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-bg-primary text-text-primary font-mono">
      <Header />

      {/* 3-column desktop layout */}
      <div className="hidden md:grid md:grid-cols-[280px_1fr_300px] md:h-[calc(100vh-48px)]">
        {/* Left sidebar */}
        <aside className="border-r border-border overflow-y-auto">
          <LeftColumn />
        </aside>

        {/* Center main */}
        <main className="overflow-y-auto px-4 py-4 space-y-4">
          <FlywheelCard />
          <PumpCard />
          <HeroCard />
          <HistoryChart />
          <VolumeChart />
          <PieChart />
          <PoolGrid />
        </main>

        {/* Right sidebar */}
        <aside className="border-l border-border overflow-y-auto">
          <RightColumn />
        </aside>
      </div>

      {/* Mobile layout */}
      <div className="md:hidden px-3 py-3 space-y-3">
        <FlywheelCard />
        <PumpCard />
        <HeroCard />
        <MobileStats />
        <HistoryChart />
        <VolumeChart />
        <PieChart />
        <PoolGrid />
      </div>
    </div>
  )
}
