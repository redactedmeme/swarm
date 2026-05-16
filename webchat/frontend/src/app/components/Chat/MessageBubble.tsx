import { useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Volume2, Copy, Check } from 'lucide-react'
import { cn, formatTime } from '@/app/lib/utils'
import type { Message } from '@/app/types'

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const [speaking, setSpeaking] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function handleTTS() {
    if (speaking) {
      speechSynthesis.cancel()
      setSpeaking(false)
      return
    }
    const utt = new SpeechSynthesisUtterance(message.content.slice(0, 2000))
    const voices = speechSynthesis.getVoices()
    const preferred = voices.find((v) => v.lang.startsWith('en') && v.name.toLowerCase().includes('female'))
      ?? voices.find((v) => v.lang.startsWith('en'))
    if (preferred) utt.voice = preferred
    utt.onend = () => setSpeaking(false)
    setSpeaking(true)
    speechSynthesis.speak(utt)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className={cn('group flex gap-2 items-end', isUser ? 'flex-row-reverse' : 'flex-row')}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-xs shrink-0 mb-0.5">
          ⬡
        </div>
      )}

      <div className={cn('flex flex-col gap-1 max-w-[75%]', isUser ? 'items-end' : 'items-start')}>
        {/* Image attachments */}
        {message.attachments?.filter((a) => a.type === 'image').map((a) => (
          <img
            key={a.name}
            src={a.data}
            alt={a.name}
            className="max-w-xs rounded-lg border border-border object-cover"
          />
        ))}

        {/* Bubble */}
        <div
          className={cn(
            'relative rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
            isUser
              ? 'bg-primary text-primary-foreground rounded-br-sm'
              : 'bg-card border border-border text-foreground rounded-bl-sm',
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Actions + timestamp */}
        <div
          className={cn(
            'flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150',
            isUser ? 'flex-row-reverse' : 'flex-row',
          )}
        >
          <span className="text-[10px] text-muted-foreground">{formatTime(message.timestamp)}</span>
          <button
            onClick={handleCopy}
            className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
            title="Copy"
          >
            {copied ? <Check size={11} /> : <Copy size={11} />}
          </button>
          {!isUser && (
            <button
              onClick={handleTTS}
              className={cn(
                'p-1 rounded text-muted-foreground hover:text-foreground transition-colors',
                speaking && 'text-primary',
              )}
              title="Read aloud"
            >
              <Volume2 size={11} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  )
}
