import { useRef, useCallback } from 'react'
import { Paperclip, Send, X, FileText } from 'lucide-react'
import { cn } from '@/app/lib/utils'
import type { Attachment } from '@/app/types'

interface Props {
  onSend: (text: string) => void
  onUpload: (file: File) => void
  disabled?: boolean
  attachments: Attachment[]
  onRemoveAttachment: (name: string) => void
}

export default function ChatInput({ onSend, onUpload, disabled, attachments, onRemoveAttachment }: Props) {
  const textRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const send = useCallback(() => {
    const text = textRef.current?.value.trim() ?? ''
    if (!text && attachments.length === 0) return
    if (textRef.current) textRef.current.value = ''
    autoResize()
    onSend(text)
  }, [attachments.length, onSend])

  function autoResize() {
    const el = textRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) onUpload(file)
    e.target.value = ''
  }

  return (
    <div className="shrink-0 px-4 py-3 border-t border-border bg-card/30">
      {/* Attachment previews */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map((a) => (
            <div
              key={a.name}
              className="relative group flex items-center gap-1.5 bg-secondary border border-border rounded-lg px-2.5 py-1.5"
            >
              {a.type === 'image' ? (
                <img src={a.data} alt={a.name} className="w-8 h-8 rounded object-cover" />
              ) : (
                <FileText size={14} className="text-muted-foreground" />
              )}
              <span className="text-xs text-muted-foreground max-w-24 truncate">{a.name}</span>
              <button
                onClick={() => onRemoveAttachment(a.name)}
                className="ml-1 text-muted-foreground hover:text-foreground transition-colors"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2">
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="shrink-0 p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
          title="Attach file"
        >
          <Paperclip size={16} />
        </button>

        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept="image/*,.txt,.md,.py,.js,.ts,.json,.csv,.pdf"
          onChange={handleFileChange}
        />

        <textarea
          ref={textRef}
          rows={1}
          onInput={autoResize}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Message redacted-chan… (Shift+Enter for newline)"
          maxLength={4000}
          className={cn(
            'flex-1 bg-input border border-border rounded-xl px-3.5 py-2.5 resize-none',
            'text-sm text-foreground placeholder:text-muted-foreground/50',
            'focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'transition-all duration-150 min-h-[42px] max-h-40',
          )}
        />

        <button
          type="button"
          onClick={send}
          disabled={disabled}
          className={cn(
            'shrink-0 p-2.5 rounded-xl transition-all duration-150',
            'bg-primary text-primary-foreground',
            'hover:bg-primary/90 active:scale-95',
            'disabled:opacity-40 disabled:cursor-not-allowed',
          )}
          title="Send"
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  )
}
