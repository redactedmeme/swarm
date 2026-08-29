export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`rounded-lg ${className}`}
      style={{
        background: 'linear-gradient(90deg, #121218 0%, #1a1a22 50%, #121218 100%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 2s linear infinite',
      }}
    />
  )
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 space-y-3 animate-fadeIn">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-36" />
      {Array.from({ length: lines - 1 }).map((_, i) => (
        <Skeleton key={i} className="h-2.5 w-full" />
      ))}
    </div>
  )
}
