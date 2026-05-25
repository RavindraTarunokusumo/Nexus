import { useState } from 'react'
import type { ApiError, ChatSessionDetail, ChatSessionSummary } from '../api/client'
import { Composer } from './Composer'
import { MessageList } from './MessageList'

type Props = {
  detail: ChatSessionDetail | null
  activeSummary: ChatSessionSummary | null
  loading: boolean
  sending: boolean
  error: ApiError | null
  onSend: (content: string) => void
  onRename: (title: string) => void
  onArchive: () => void
  onClearError: () => void
}

export function ChatPanel({
  detail,
  activeSummary,
  loading,
  sending,
  error,
  onSend,
  onRename,
  onArchive,
  onClearError,
}: Props) {
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')

  const session = detail ?? (activeSummary as ChatSessionDetail | null)
  const isArchived = session?.status === 'archived'

  function startRename() {
    setRenameValue(session?.title ?? '')
    setRenaming(true)
  }

  function commitRename() {
    const v = renameValue.trim()
    if (v) onRename(v)
    setRenaming(false)
  }

  if (!session && !loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Select a session or start a new chat.
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="border-b border-gray-200 px-4 py-3 flex items-center gap-2 bg-white flex-shrink-0">
        {renaming ? (
          <input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setRenaming(false)
            }}
            aria-label="Session title"
            className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        ) : (
          <h1 className="flex-1 text-sm font-semibold text-gray-800 truncate">
            {session?.title ?? 'Untitled chat'}
            {isArchived && <span className="ml-2 text-xs text-gray-400 font-normal">(archived)</span>}
          </h1>
        )}
        {!isArchived && (
          <button
            onClick={startRename}
            aria-label="Rename session"
            className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100"
          >
            Rename
          </button>
        )}
        {!isArchived && (
          <button
            onClick={onArchive}
            aria-label="Archive session"
            className="text-xs text-gray-400 hover:text-red-500 px-2 py-1 rounded hover:bg-gray-100"
          >
            Archive
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="bg-red-50 border-b border-red-200 px-4 py-2 flex items-center justify-between text-sm text-red-700"
        >
          <span>{error.message}</span>
          <button
            onClick={onClearError}
            aria-label="Dismiss error"
            className="ml-4 text-red-500 hover:text-red-700 font-medium"
          >
            ×
          </button>
        </div>
      )}

      {/* Messages */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
          Loading…
        </div>
      ) : (
        <MessageList messages={detail?.messages ?? []} sending={sending} />
      )}

      {/* Composer */}
      <Composer
        disabled={!session || loading || !detail}
        sending={sending}
        archived={isArchived ?? false}
        onSubmit={onSend}
      />
    </div>
  )
}
