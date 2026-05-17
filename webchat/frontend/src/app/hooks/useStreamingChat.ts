import { useCallback } from 'react'
import { toast } from 'sonner'
import { useAuthStore } from '@/app/store/authStore'
import { useChatStore, buildApiHistory } from '@/app/store/chatStore'
import { apiUpload } from '@/app/lib/api'
import type { Attachment } from '@/app/types'
import type { ChatAgent } from '@/app/components/Chat/ChanHeader'

export function useStreamingChat(agent: ChatAgent = 'chan') {
  const sessionId = useAuthStore((s) => s.sessionId)
  const setSessionId = useAuthStore((s) => s.setAuth)
  const token = useAuthStore((s) => s.token)
  const {
    messages,
    pendingAttachments,
    isWaiting,
    addUserMessage,
    startStreamingMessage,
    appendStreamingChunk,
    finalizeStreamingMessage,
    setWaiting,
    addAttachment,
    removeAttachment,
    clearAttachments,
  } = useChatStore()

  const handleUpload = useCallback(
    async (file: File) => {
      try {
        const result = await apiUpload(file)
        const attachment: Attachment = {
          type: result.type === 'image' ? 'image' : 'file',
          name: result.name,
          data: result.data,
        }
        addAttachment(attachment)
      } catch {
        toast.error('Upload failed')
      }
    },
    [addAttachment],
  )

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() && pendingAttachments.length === 0) return
      if (isWaiting) return

      const attachments = [...pendingAttachments]
      clearAttachments()

      const imageAttachment = attachments.find((a) => a.type === 'image')
      const fileAttachments = attachments.filter((a) => a.type === 'file')

      let content = text
      for (const f of fileAttachments) {
        content = `[Attached file: ${f.name}]\n${f.data}\n\n${content}`
      }

      addUserMessage(content, attachments)
      setWaiting(true)

      // ── Hermes: non-streaming POST, poll up to 70s ────────────────────────
      if (agent === 'hermes') {
        const msgId = startStreamingMessage()
        try {
          const res = await fetch('/hermes/chat', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              message: content,
              session_id: sessionId ?? '',
              history: buildApiHistory(messages),
            }),
            signal: AbortSignal.timeout(75_000),
          })
          const data = await res.json() as { response?: string; error?: string; timeout?: boolean }
          const reply = data.response ?? data.error ?? 'No response'
          appendStreamingChunk(msgId, reply)
          if (data.timeout) {
            toast.info('Hermes is still working — check the swarm feed for updates')
          }
        } catch (err) {
          appendStreamingChunk(msgId, 'Hermes is unavailable right now.')
          toast.error(err instanceof Error ? err.message : 'Hermes error')
        } finally {
          finalizeStreamingMessage(msgId)
          setWaiting(false)
        }
        return
      }

      // ── Chan (default): SSE streaming ─────────────────────────────────────
      const history = buildApiHistory(messages)
      const payload = {
        message: content,
        session_id: sessionId ?? '',
        history,
        ...(imageAttachment ? { image_data: imageAttachment.data } : {}),
      }

      const msgId = startStreamingMessage()

      try {
        const res = await fetch('/chat/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(100_000),
        })

        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6)
            try {
              const evt = JSON.parse(raw) as {
                delta?: string
                done?: boolean
                session_id?: string
                error?: string
              }
              if (evt.error) { toast.error(evt.error); break }
              if (evt.session_id && evt.session_id !== sessionId) {
                setSessionId(token ?? '', evt.session_id)
              }
              if (evt.delta) appendStreamingChunk(msgId, evt.delta)
              if (evt.done) break
            } catch { /* malformed SSE */ }
          }
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Connection error')
      } finally {
        finalizeStreamingMessage(msgId)
        setWaiting(false)
      }
    },
    [
      agent, messages, pendingAttachments, isWaiting, sessionId, token,
      addUserMessage, startStreamingMessage, appendStreamingChunk,
      finalizeStreamingMessage, setWaiting, clearAttachments, setSessionId,
    ],
  )

  return { sendMessage, handleUpload, pendingAttachments, isWaiting, removeAttachment }
}
