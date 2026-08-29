import type { ReactNode } from 'react'

interface TooltipProps {
  content: string
  children: ReactNode
  side?: 'top' | 'bottom'
}

export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  return (
    <span className="relative group inline-flex items-center">
      {children}
      <span
        className={`
          pointer-events-none absolute left-1/2 -translate-x-1/2 z-50
          px-2 py-1 text-[9px] leading-tight bg-bg-hover border border-border rounded
          text-text-secondary whitespace-nowrap
          opacity-0 group-hover:opacity-100 transition-opacity duration-150
          ${side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5'}
        `}
        style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.6)' }}
      >
        {content}
      </span>
    </span>
  )
}

export function InfoIcon({ tooltip }: { tooltip: string }) {
  return (
    <Tooltip content={tooltip}>
      <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-text-muted text-text-muted text-[8px] cursor-default hover:border-accent hover:text-accent transition-colors ml-1">
        ?
      </span>
    </Tooltip>
  )
}
