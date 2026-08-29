'use client'
import { useState } from 'react'

interface TokenIconProps {
  url?: string
  fallback?: string
  size?: number
  className?: string
}

export function TokenIcon({ url, fallback = 'R', size = 28, className = '' }: TokenIconProps) {
  const [failed, setFailed] = useState(false)

  if (url && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={fallback}
        width={size}
        height={size}
        onError={() => setFailed(true)}
        className={`rounded-full object-cover ${className}`}
        style={{ width: size, height: size }}
      />
    )
  }

  return (
    <div
      className={`rounded-full flex items-center justify-center bg-accent/10 text-accent font-bold ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {fallback}
    </div>
  )
}
