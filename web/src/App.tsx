import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import { ChatPanel } from './components/ChatPanel'
import { Dashboard } from './components/Dashboard'
import { HowItWorks } from './components/HowItWorks'
import { SessionSidebar } from './components/SessionSidebar'
import { useChatSession } from './hooks/useChatSession'
import { useSessions } from './hooks/useSessions'
import type { AnswerMeta } from './lib/mermaid'

type Tab = 'dashboard' | 'chat' | 'how-it-works'

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [lastAnswerMeta, setLastAnswerMeta] = useState<AnswerMeta | null>(null)

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

  const handleAnswerReceived = useCallback((meta: AnswerMeta) => {
    setLastAnswerMeta(meta)
  }, [])

  const { detail, loading, sending, error, sendMessage, clearError } = useChatSession(
    activeId,
    undefined,
    handleAnswerReceived,
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
    <div className="app-shell">
      <nav className="tab-bar" aria-label="Main navigation">
        <button
          type="button"
          className={`tab-button${activeTab === 'dashboard' ? ' tab-button-active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
          aria-current={activeTab === 'dashboard' ? 'page' : undefined}
        >
          Dashboard
        </button>
        <button
          type="button"
          className={`tab-button${activeTab === 'chat' ? ' tab-button-active' : ''}`}
          onClick={() => setActiveTab('chat')}
          aria-current={activeTab === 'chat' ? 'page' : undefined}
        >
          Chat
        </button>
        <button
          type="button"
          className={`tab-button${activeTab === 'how-it-works' ? ' tab-button-active' : ''}`}
          onClick={() => setActiveTab('how-it-works')}
          aria-current={activeTab === 'how-it-works' ? 'page' : undefined}
        >
          How it works
        </button>
      </nav>

      {activeTab === 'chat' && (
        <div className="chat-layout flex h-[calc(100vh-41px)] bg-gray-50 overflow-hidden">
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
      )}

      {activeTab === 'dashboard' && (
        <main className="tab-panel">
          <Dashboard />
        </main>
      )}

      {activeTab === 'how-it-works' && (
        <main className="tab-panel">
          <HowItWorks lastAnswerMeta={lastAnswerMeta} />
        </main>
      )}
    </div>
  )
}
