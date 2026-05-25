import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ApiError, type ChatMessage, type ChatSessionDetail, normalizeApiError } from '../api/client'

export type ChatSessionState = {
  detail: ChatSessionDetail | null
  messages: ChatMessage[]
  loading: boolean
  sending: boolean
  error: ApiError | null
  sendMessage: (content: string, topK?: number) => Promise<void>
  clearError: () => void
}

export function useChatSession(
  sessionId: string | null,
  onSessionUpdate?: (id: string) => void,
): ChatSessionState {
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const pendingRef = useRef<ChatMessage | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setDetail(null)
      return
    }
    setLoading(true)
    setError(null)
    api
      .getSession(sessionId)
      .then((d) => setDetail(d))
      .catch((err) => {
        setError(normalizeApiError(err))
      })
      .finally(() => setLoading(false))
  }, [sessionId])

  const sendMessage = useCallback(
    async (content: string, topK = 8) => {
      if (!sessionId) return

      const pending: ChatMessage = {
        id: `pending-${Date.now()}`,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      }
      pendingRef.current = pending
      setDetail((prev) =>
        prev ? { ...prev, messages: [...prev.messages, pending] } : prev,
      )
      setSending(true)
      setError(null)

      try {
        const resp = await api.sendMessage(sessionId, content, topK)
        onSessionUpdate?.(sessionId)
        setDetail((prev) => {
          if (!prev) return prev
          const withoutPending = prev.messages.filter((m) => m.id !== pending.id)
          return {
            ...prev,
            ...resp.session,
            messages: [...withoutPending, resp.user_message, resp.assistant_message],
          }
        })
      } catch (err) {
        // Remove optimistic pending bubble on failure
        setDetail((prev) =>
          prev ? { ...prev, messages: prev.messages.filter((m) => m.id !== pending.id) } : prev,
        )
        setError(normalizeApiError(err))
      } finally {
        pendingRef.current = null
        setSending(false)
      }
    },
    [sessionId, onSessionUpdate],
  )

  const clearError = useCallback(() => setError(null), [])

  return {
    detail,
    messages: detail?.messages ?? [],
    loading,
    sending,
    error,
    sendMessage,
    clearError,
  }
}
