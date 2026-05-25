import { useCallback, useEffect, useState } from 'react'
import { api, type ApiError, type ChatSessionSummary, normalizeApiError } from '../api/client'

export type SessionsState = {
  sessions: ChatSessionSummary[]
  loading: boolean
  error: ApiError | null
  activeId: string | null
  createSession: () => Promise<void>
  selectSession: (id: string) => void
  renameSession: (id: string, title: string) => Promise<void>
  archiveSession: (id: string) => Promise<void>
}

export function useSessions(): SessionsState {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api.listSessions('active')
      setSessions(list)
    } catch (err) {
      setError(normalizeApiError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const createSession = useCallback(async () => {
    try {
      const session = await api.createSession()
      setSessions((prev) => [session, ...prev])
      setActiveId(session.id)
    } catch (err) {
      setError(normalizeApiError(err))
    }
  }, [])

  const selectSession = useCallback((id: string) => {
    setActiveId(id)
  }, [])

  const renameSession = useCallback(async (id: string, title: string) => {
    try {
      const updated = await api.patchSession(id, { title })
      setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)))
    } catch (err) {
      setError(normalizeApiError(err))
    }
  }, [])

  const archiveSession = useCallback(async (id: string) => {
    try {
      await api.patchSession(id, { status: 'archived' })
      setSessions((prev) => prev.filter((s) => s.id !== id))
      setActiveId((prev) => (prev === id ? null : prev))
    } catch (err) {
      setError(normalizeApiError(err))
    }
  }, [])

  return { sessions, loading, error, activeId, createSession, selectSession, renameSession, archiveSession }
}
