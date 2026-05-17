import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, Attachment } from '@/app/types'
import { nanoid } from '@/app/lib/utils'

const MAX_HISTORY = 40

type AgentId = string

interface ChatState {
  messagesByAgent: Record<AgentId, Message[]>
  activeAgent: AgentId
  pendingAttachments: Attachment[]
  isWaiting: boolean
  streamingId: string | null

  setActiveAgent: (agent: AgentId) => void
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

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messagesByAgent: { chan: [], hermes: [], smolting: [], builder: [] },
      activeAgent: 'chan',
      pendingAttachments: [],
      isWaiting: false,
      streamingId: null,

      setActiveAgent: (agent) => set({ activeAgent: agent }),

      addUserMessage: (content, attachments) => {
        const msg: Message = {
          id: nanoid(),
          role: 'user',
          content,
          timestamp: Date.now(),
          attachments,
        }
        const agent = get().activeAgent
        set((s) => ({
          messagesByAgent: {
            ...s.messagesByAgent,
            [agent]: [...(s.messagesByAgent[agent] ?? []), msg],
          },
        }))
        return msg
      },

      startStreamingMessage: () => {
        const id = nanoid()
        const msg: Message = { id, role: 'assistant', content: '', timestamp: Date.now(), isStreaming: true }
        const agent = get().activeAgent
        set((s) => ({
          messagesByAgent: {
            ...s.messagesByAgent,
            [agent]: [...(s.messagesByAgent[agent] ?? []), msg],
          },
          streamingId: id,
        }))
        return id
      },

      appendStreamingChunk: (id, chunk) => {
        const agent = get().activeAgent
        set((s) => ({
          messagesByAgent: {
            ...s.messagesByAgent,
            [agent]: (s.messagesByAgent[agent] ?? []).map((m) =>
              m.id === id ? { ...m, content: m.content + chunk } : m,
            ),
          },
        }))
      },

      finalizeStreamingMessage: (id) => {
        const agent = get().activeAgent
        set((s) => ({
          messagesByAgent: {
            ...s.messagesByAgent,
            [agent]: (s.messagesByAgent[agent] ?? []).map((m) =>
              m.id === id ? { ...m, isStreaming: false } : m,
            ),
          },
          streamingId: null,
        }))
        get().trimHistory()
      },

      addAssistantMessage: (content) => {
        const msg: Message = { id: nanoid(), role: 'assistant', content, timestamp: Date.now() }
        const agent = get().activeAgent
        set((s) => ({
          messagesByAgent: {
            ...s.messagesByAgent,
            [agent]: [...(s.messagesByAgent[agent] ?? []), msg],
          },
        }))
        get().trimHistory()
      },

      setWaiting: (v) => set({ isWaiting: v }),

      addAttachment: (a) => set((s) => ({ pendingAttachments: [...s.pendingAttachments, a] })),
      removeAttachment: (name) =>
        set((s) => ({ pendingAttachments: s.pendingAttachments.filter((a) => a.name !== name) })),
      clearAttachments: () => set({ pendingAttachments: [] }),

      clearMessages: () => {
        const agent = get().activeAgent
        set((s) => ({
          messagesByAgent: { ...s.messagesByAgent, [agent]: [] },
          streamingId: null,
        }))
      },

      trimHistory: () => {
        const agent = get().activeAgent
        const msgs = get().messagesByAgent[agent] ?? []
        if (msgs.length > MAX_HISTORY) {
          set((s) => ({
            messagesByAgent: {
              ...s.messagesByAgent,
              [agent]: msgs.slice(msgs.length - MAX_HISTORY),
            },
          }))
        }
      },
    }),
    {
      name: 'webchat-chat-store',
      partialize: (state) => ({
        messagesByAgent: state.messagesByAgent,
        activeAgent: state.activeAgent,
      }),
    },
  ),
)

export function selectMessages(s: ChatState): Message[] {
  return s.messagesByAgent[s.activeAgent] ?? []
}

export function buildApiHistory(messages: Message[]) {
  return messages
    .filter((m) => !m.isStreaming)
    .map((m) => ({ role: m.role, content: m.content }))
}
