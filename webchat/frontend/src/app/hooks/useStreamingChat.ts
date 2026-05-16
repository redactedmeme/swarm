import { useCallback } from 'react'
import { toast } from 'sonner'
import { useAuthStore } from '@/app/store/authStore'
import { useChatStore, buildApiHistory } from '@/app/store/chatStore'
import { apiUpload } from '@/app/lib/api'
import type { Attachment } from '@/app/types'

export function useStreamingChat() {
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
        const attachment: Attachment = { type: result.type, name: result.name, data: result.data }
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

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`)
        }

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
              if (evt.error) {
                toast.error(evt.error)
                break
              }
              if (evt.session_id && evt.session_id !== sessionId) {
                // persist new session id without clearing token
                const currentToken = token ?? ''
                setSessionId(currentToken, evt.session_id)
              }
              if (evt.delta) {
                appendStreamingChunk(msgId, evt.delta)
              }
              if (evt.done) break
            } catch {
              // malformed SSE line — skip
            }
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
      messages,
      pendingAttachments,
      isWaiting,
      sessionId,
      token,
      addUserMessage,
      startStreamingMessage,
      appendStreamingChunk,
      finalizeStreamingMessage,
      setWaiting,
      clearAttachments,
      setSessionId,
    ],
  )

  return { sendMessage, handleUpload, pendingAttachments, isWaiting, removeAttachment }
}
