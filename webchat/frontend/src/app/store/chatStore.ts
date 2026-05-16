import { create } from 'zustand'
import type { Message, Attachment } from '@/app/types'
import { nanoid } from '@/app/lib/utils'

const MAX_HISTORY = 20

interface ChatState {
  messages: Message[]
  pendingAttachments: Attachment[]
  isWaiting: boolean
  streamingId: string | null
  addUserMessage: (content: string, attachments?: Attachment[]) => Message
  startStreamingMessage: () => string
  appendStreamingChunk: (id: string, chunk: string) => void
  finalizeStreamingMessage: (id: string) => void
  addAssistantMessage: (content: string) => void
  setWaiting: (v: boolean) => void
  addAttachment: (a: Attachment) => void
  removeAttachment: (name: string) => void
  clearAttachments: () => void
  clearMessages: () => void
  trimHistory: () => void
}

export const useChatStore = create<ChatState>()((set, get) => ({
  messages: [],
  pendingAttachments: [],
  isWaiting: false,
  streamingId: null,

  addUserMessage: (content, attachments) => {
    const msg: Message = {
      id: nanoid(),
      role: 'user',
      content,
      timestamp: Date.now(),
      attachments,
    }
    set((s) => ({ messages: [...s.messages, msg] }))
    return msg
  },

  startStreamingMessage: () => {
    const id = nanoid()
    const msg: Message = { id, role: 'assistant', content: '', timestamp: Date.now(), isStreaming: true }
    set((s) => ({ messages: [...s.messages, msg], streamingId: id }))
    return id
  },

  appendStreamingChunk: (id, chunk) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + chunk } : m,
      ),
    }))
  },

  finalizeStreamingMessage: (id) => {
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, isStreaming: false } : m)),
      streamingId: null,
    }))
    get().trimHistory()
  },

  addAssistantMessage: (content) => {
    const msg: Message = { id: nanoid(), role: 'assistant', content, timestamp: Date.now() }
    set((s) => ({ messages: [...s.messages, msg] }))
    get().trimHistory()
  },

  setWaiting: (v) => set({ isWaiting: v }),

  addAttachment: (a) => set((s) => ({ pendingAttachments: [...s.pendingAttachments, a] })),
  removeAttachment: (name) =>
    set((s) => ({ pendingAttachments: s.pendingAttachments.filter((a) => a.name !== name) })),
  clearAttachments: () => set({ pendingAttachments: [] }),
  clearMessages: () => set({ messages: [], streamingId: null }),

  trimHistory: () => {
    const { messages } = get()
    if (messages.length > MAX_HISTORY) {
      set({ messages: messages.slice(messages.length - MAX_HISTORY) })
    }
  },
}))

export function buildApiHistory(messages: Message[]) {
  return messages
    .filter((m) => !m.isStreaming)
    .map((m) => ({ role: m.role, content: m.content }))
}
