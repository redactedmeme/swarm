export interface Token {
  address: string
  symbol: string
  name: string
}

export interface Pool {
  pairAddress: string
  baseToken: Token
  quoteToken: Token
  priceUsd: string
  priceNative: string
  marketCap: number
  fdv: number
  volume: { h24: number; h6: number; h1: number }
  liquidity: { usd: number; base?: number; quote?: number }
  txns: { h24: { buys: number; sells: number } }
  priceChange?: { h1?: number; h6?: number; h24?: number }
  dexId: string
  info?: { imageUrl?: string }
}

export interface Snapshot {
  ts: number
  vol24h: number
  vol6h: number
  vol1h: number
  liq: number
  price: number
  mcap: number
  pools: number
  image_url: string
  buys?: number
  sells?: number
}

export interface TokenData {
  supply_ui: number
  decimals: number
  supply?: number
  top10_pct: number
  holder_count: number
  holder_count_capped: boolean
  top_holders: { address: string; pct: number }[]
  mint_authority_revoked: boolean
  freeze_authority_revoked: boolean
  image_url: string
}

export interface V2Data {
  price: number
  mcap: number
  vol24h: number
  vol6h: number
  vol1h: number
  liq: number
  pools: number
  priceChange: { h1?: number; h6?: number; h24?: number }
  image_url: string
}

export interface PoolPairData {
  ts: number
  price: number
  price_usd: number
  tvl: number
  vol24h: number
  vol7d?: number
  buys24h: number
  sells24h: number
  fee_rate: number
  base_reserve?: number
  quote_reserve?: number
}

export type FeeRatesMap = Record<string, number>

export type HistoryRange = '24h' | '1w'
export type ChartMetric = 'volume24h' | 'volume6h' | 'volume1h' | 'liquidity' | 'fees24h'
