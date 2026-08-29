'use client'
import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react'
import type { Pool, Snapshot, TokenData, V2Data, PoolPairData, FeeRatesMap } from '@/lib/types'
import { TOKEN, PUMP_TOKEN, MANUAL_FEE_OVERRIDES } from '@/lib/calculations'

interface DashboardState {
  poolsData: Pool[]
  serverSnapshots: Snapshot[]
  clientSnapshots: Snapshot[]
  tokenData: Partial<TokenData>
  v2Data: Partial<V2Data>
  v1v2PoolData: Partial<PoolPairData>
  meteoraPoolData: Partial<PoolPairData>
  feeRatesMap: FeeRatesMap
  loading: boolean
  lastUpdated: Date | null
  refresh: () => Promise<void>
}

const DashboardContext = createContext<DashboardState | null>(null)

export function useDashboard() {
  const ctx = useContext(DashboardContext)
  if (!ctx) throw new Error('useDashboard must be used within DashboardProvider')
  return ctx
}

async function fetchJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } })
    if (!res.ok) return null
    return await res.json() as T
  } catch { return null }
}

async function fetchV2Data(): Promise<Partial<V2Data>> {
  // Try backend cache first
  const cached = await fetchJSON<V2Data>('/api/v2')
  if (cached && cached.price) return cached
  // Fallback: DexScreener direct
  type DexResp = { pairs?: Array<{ priceUsd?: string; marketCap?: number; fdv?: number; volume?: Record<string,number>; liquidity?: { usd?: number }; priceChange?: Record<string,number>; info?: { imageUrl?: string } }> }
  const raw = await fetchJSON<DexResp>(`https://api.dexscreener.com/latest/dex/tokens/${PUMP_TOKEN}`)
  const pairs = (raw?.pairs ?? []).sort((a, b) => (b.volume?.h24 ?? 0) - (a.volume?.h24 ?? 0))
  if (!pairs.length) return {}
  const p0 = pairs[0]
  return {
    price:       parseFloat(p0.priceUsd ?? '0'),
    mcap:        p0.marketCap ?? p0.fdv ?? 0,
    vol24h:      pairs.reduce((s, p) => s + (p.volume?.h24 ?? 0), 0),
    vol6h:       pairs.reduce((s, p) => s + (p.volume?.h6  ?? 0), 0),
    vol1h:       pairs.reduce((s, p) => s + (p.volume?.h1  ?? 0), 0),
    liq:         pairs.reduce((s, p) => s + (p.liquidity?.usd ?? 0), 0),
    pools:       pairs.length,
    priceChange: p0.priceChange ?? {},
    image_url:   p0.info?.imageUrl ?? '',
  }
}

async function fetchFeeRates(pools: Pool[]): Promise<FeeRatesMap> {
  const map: FeeRatesMap = { ...MANUAL_FEE_OVERRIDES }
  const byDex: Record<string, Pool[]> = {}
  for (const p of pools) {
    ;(byDex[p.dexId] ??= []).push(p)
  }

  await Promise.all([
    // Raydium
    byDex.raydium?.length ? (async () => {
      type RaydiumResp = { data?: Array<{ id?: string; feeRate?: number }> }
      const ids = byDex.raydium.map(p => p.pairAddress).join(',')
      const d = await fetchJSON<RaydiumResp>(`https://api-v3.raydium.io/pools/info/ids?ids=${ids}`)
      for (const pool of d?.data ?? []) {
        if (pool.id && pool.feeRate != null) map[pool.id] = pool.feeRate
      }
    })() : Promise.resolve(),

    // Orca
    byDex.orca?.length ? (async () => {
      type OrcaResp = { whirlpools?: Array<{ address?: string; lpFeeRate?: number }> }
      const addrs = new Set(byDex.orca.map(p => p.pairAddress))
      const d = await fetchJSON<OrcaResp>('https://api.mainnet.orca.so/v1/whirlpool/list')
      for (const w of d?.whirlpools ?? []) {
        if (w.address && addrs.has(w.address) && w.lpFeeRate != null) map[w.address] = w.lpFeeRate
      }
    })() : Promise.resolve(),

    // Meteora
    byDex.meteora?.length ? Promise.all(
      byDex.meteora.map(async p => {
        type MeteoraResp = Array<{ pool_address?: string; trading_fee?: number }>
        const d = await fetchJSON<MeteoraResp>(`https://amm-v2.meteora.ag/pools?address=${p.pairAddress}`)
        const pool = d?.[0]
        if (pool?.pool_address && pool.trading_fee != null) map[pool.pool_address] = pool.trading_fee / 100
      })
    ) : Promise.resolve(),
  ])

  return map
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [poolsData, setPoolsData] = useState<Pool[]>([])
  const [serverSnapshots, setServerSnapshots] = useState<Snapshot[]>([])
  const [clientSnapshots, setClientSnapshots] = useState<Snapshot[]>([])
  const [tokenData, setTokenData] = useState<Partial<TokenData>>({})
  const [v2Data, setV2Data] = useState<Partial<V2Data>>({})
  const [v1v2PoolData, setV1v2PoolData] = useState<Partial<PoolPairData>>({})
  const [meteoraPoolData, setMeteoraPoolData] = useState<Partial<PoolPairData>>({})
  const [feeRatesMap, setFeeRatesMap] = useState<FeeRatesMap>({ ...MANUAL_FEE_OVERRIDES })
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  const refresh = useCallback(async () => {
    try {
      type DexResp = { pairs?: Pool[] }
      const raw = await fetchJSON<DexResp>(`https://api.dexscreener.com/latest/dex/tokens/${TOKEN}`)
      const sorted = (raw?.pairs ?? []).sort((a, b) => (b.volume?.h24 ?? 0) - (a.volume?.h24 ?? 0))
      setPoolsData(sorted)

      const rates = await fetchFeeRates(sorted)
      setFeeRatesMap(rates)

      // Push client snapshot
      if (sorted.length > 0) {
        const snap: Snapshot = {
          ts:     Date.now() / 1000,
          vol24h: sorted.reduce((s, p) => s + (p.volume?.h24 ?? 0), 0),
          vol6h:  sorted.reduce((s, p) => s + (p.volume?.h6  ?? 0), 0),
          vol1h:  sorted.reduce((s, p) => s + (p.volume?.h1  ?? 0), 0),
          liq:    sorted.reduce((s, p) => s + (p.liquidity?.usd ?? 0), 0),
          price:  parseFloat(sorted[0].priceUsd ?? '0'),
          mcap:   sorted[0].marketCap ?? sorted[0].fdv ?? 0,
          pools:  sorted.length,
          image_url: sorted[0].info?.imageUrl ?? '',
        }
        setClientSnapshots(prev => [...prev.slice(-335), snap])
      }

      await Promise.all([
        fetchJSON<Snapshot[]>('/api/snapshots').then(d => { if (d?.length) setServerSnapshots(d) }),
        fetchJSON<TokenData>('/api/token').then(d => { if (d) setTokenData(d) }),
        fetchV2Data().then(d => { if (d.price) setV2Data(d) }),
        fetchJSON<PoolPairData>('/api/v1v2pool').then(d => { if (d?.tvl) setV1v2PoolData(d) }),
        fetchJSON<PoolPairData>('/api/meteorapool').then(d => { if (d?.tvl) setMeteoraPoolData(d) }),
      ])

      setLastUpdated(new Date())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    intervalRef.current = setInterval(refresh, 30000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [refresh])

  return (
    <DashboardContext.Provider value={{
      poolsData, serverSnapshots, clientSnapshots,
      tokenData, v2Data, v1v2PoolData, meteoraPoolData,
      feeRatesMap, loading, lastUpdated, refresh,
    }}>
      {children}
    </DashboardContext.Provider>
  )
}
