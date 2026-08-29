import { useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useChatStore, selectMessages } from '@/app/store/chatStore'
import { useStreamingChat } from '@/app/hooks/useStreamingChat'
import { useKeyboard } from '@/app/hooks/useKeyboard'
import MessageBubble from '@/app/components/Chat/MessageBubble'
import ChatInput from '@/app/components/Chat/ChatInput'
import TypingIndicator from '@/app/components/Chat/TypingIndicator'
import ChanHeader from '@/app/components/Chat/ChanHeader'
import type { ChatAgent } from '@/app/components/Chat/ChanHeader'
import CommandPalette from '@/app/components/CommandPalette'
import { useState } from 'react'

export default function ChatPage() {
  const messages = useChatStore(selectMessages)
  const isWaiting = useChatStore((s) => s.isWaiting)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const activeAgent = useChatStore((s) => s.activeAgent) as ChatAgent
  const setActiveAgent = useChatStore((s) => s.setActiveAgent)
  const { sendMessage, handleUpload, pendingAttachments, removeAttachment } = useStreamingChat(activeAgent)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isWaiting])

  useKeyboard([
    { key: 'k', meta: true, handler: () => setPaletteOpen((v) => !v) },
    { key: 'Escape', handler: () => setPaletteOpen(false) },
    { key: 'l', meta: true, shift: true, handler: () => clearMessages() },
  ])

  const AGENT_LABELS: Record<string, string> = { chan: 'redacted-chan', hermes: 'hermes-bot', smolting: 'smolting', builder: 'builder' }

  return (
    <div className="flex flex-col h-full min-h-0">
      <ChanHeader
        onPaletteOpen={() => setPaletteOpen(true)}
        selectedAgent={activeAgent}
        onSelectAgent={(a) => setActiveAgent(a)}
      />

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center h-full gap-4 text-center select-none"
          >
            <motion.div
              animate={{ rotate: [0, 360] }}
              transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
              className="text-4xl text-primary/30"
            >
              ⬡
            </motion.div>
            <div>
              <p className="text-muted-foreground text-sm">Start a conversation with {AGENT_LABELS[activeAgent] ?? activeAgent}.</p>
              <p className="text-muted-foreground/50 text-xs mt-1">
                Press <kbd className="px-1.5 py-0.5 rounded border border-border text-[10px] font-mono">⌘K</kbd> for commands
              </p>
            </div>
          </motion.div>
        )}

        <div className="space-y-1">
          <AnimatePresence initial={false}>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </AnimatePresence>
        </div>

        {isWaiting && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-end gap-2 mt-2 ml-9"
          >
            <TypingIndicator />
          </motion.div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput
        onSend={sendMessage}
        onUpload={handleUpload}
        disabled={isWaiting}
        attachments={pendingAttachments}
        onRemoveAttachment={removeAttachment}
      />

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}
