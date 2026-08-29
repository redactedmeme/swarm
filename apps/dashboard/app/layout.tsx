import type { Metadata } from 'next'
import { Providers } from './providers'
import './globals.css'

export const metadata: Metadata = {
  title: 'REDACTED SWARM TRACKER',
  description: 'REDACTED ecosystem dashboard',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="bg-bg-primary">
      <body className="bg-bg-primary text-text-primary font-mono min-h-screen overflow-x-hidden">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
