import { motion } from 'framer-motion'

export default function TypingIndicator() {
  return (
    <div className="bg-card border border-border rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1.5 items-center">
      {[0, 0.15, 0.3].map((delay, i) => (
        <motion.span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-muted-foreground"
          animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 0.8, repeat: Infinity, delay, ease: 'easeInOut' }}
        />
      ))}
    </div>
  )
}
