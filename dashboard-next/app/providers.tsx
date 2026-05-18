'use client'
import { useMemo, type ReactNode } from 'react'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { ConnectionProvider, WalletProvider } = require('@solana/wallet-adapter-react') as any
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { WalletModalProvider } = require('@solana/wallet-adapter-react-ui') as any
import { PhantomWalletAdapter, SolflareWalletAdapter } from '@solana/wallet-adapter-wallets'
import { DashboardProvider } from '@/context/DashboardContext'
import '@solana/wallet-adapter-react-ui/styles.css'

const RPC = 'https://api.mainnet-beta.solana.com'

export function Providers({ children }: { children: ReactNode }) {
  const wallets = useMemo(() => [
    new PhantomWalletAdapter(),
    new SolflareWalletAdapter(),
  ], [])

  return (
    <ConnectionProvider endpoint={RPC}>
      <WalletProvider wallets={wallets} autoConnect>
        <WalletModalProvider>
          <DashboardProvider>
            {children}
          </DashboardProvider>
        </WalletModalProvider>
      </WalletProvider>
    </ConnectionProvider>
  )
}
