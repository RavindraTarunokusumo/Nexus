import { useCallback, useEffect, useRef } from 'react'
import { ChatPanel } from './components/ChatPanel'
import { SessionSidebar } from './components/SessionSidebar'
import { useChatSession } from './hooks/useChatSession'
import { useSessions } from './hooks/useSessions'

export default function App() {
  const {
    sessions,
    loading: sessionsLoading,
    activeId,
    createSession,
    selectSession,
    renameSession,
    archiveSession,
  } = useSessions()

  const activeSummary = sessions.find((s) => s.id === activeId) ?? null

  const onSessionUpdate = useCallback(
    (_id: string) => {
      // No-op: message state is already updated by useChatSession
    },
    [],
  )

  const { detail, loading, sending, error, sendMessage, clearError } = useChatSession(
    activeId,
    onSessionUpdate,
  )

  const pendingMessageRef = useRef<string | null>(null)

  useEffect(() => {
    if (activeId && pendingMessageRef.current) {
      const msg = pendingMessageRef.current
      pendingMessageRef.current = null
      void sendMessage(msg)
    }
  }, [activeId, sendMessage])

  async function handleNewChat() {
    await createSession()
  }

  async function handleSend(content: string) {
    if (!activeId) {
      pendingMessageRef.current = content
      await createSession()
      return
    }
    await sendMessage(content)
  }

  async function handleRename(title: string) {
    if (!activeId) return
    await renameSession(activeId, title)
  }

  async function handleArchive() {
    if (!activeId) return
    await archiveSession(activeId)
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        loading={sessionsLoading}
        onNewChat={handleNewChat}
        onSelect={selectSession}
      />
      <main className="flex-1 flex min-w-0">
        <ChatPanel
          detail={detail}
          activeSummary={activeSummary}
          loading={loading}
          sending={sending}
          error={error}
          onSend={handleSend}
          onRename={handleRename}
          onArchive={handleArchive}
          onClearError={clearError}
        />
      </main>
    </div>
  )
}
