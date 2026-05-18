'use client'
import { useWallet } from '@solana/wallet-adapter-react'
import { useWalletModal } from '@solana/wallet-adapter-react-ui'
import { truncate } from '@/lib/formatters'

export function WalletButton() {
  const { publicKey, disconnect, connecting } = useWallet()
  const { setVisible } = useWalletModal()

  if (connecting) {
    return (
      <button className="px-3 py-1 text-[10px] border border-border rounded text-text-muted">
        Connecting…
      </button>
    )
  }

  if (publicKey) {
    return (
      <button
        onClick={disconnect}
        className="px-3 py-1 text-[10px] border border-accent/40 rounded text-accent hover:border-accent transition-colors"
      >
        {truncate(publicKey.toBase58(), 4)} · disconnect
      </button>
    )
  }

  return (
    <button
      onClick={() => setVisible(true)}
      className="px-3 py-1 text-[10px] border border-border rounded text-text-secondary hover:border-accent hover:text-text-primary transition-colors"
    >
      Connect Wallet
    </button>
  )
}
