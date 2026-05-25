import type { ChatSessionSummary } from '../api/client'

type Props = {
  sessions: ChatSessionSummary[]
  activeId: string | null
  loading: boolean
  onNewChat: () => void
  onSelect: (id: string) => void
}

export function SessionSidebar({ sessions, activeId, loading, onNewChat, onSelect }: Props) {
  return (
    <aside className="w-64 border-r border-gray-200 bg-white flex flex-col flex-shrink-0 h-full">
      <div className="p-3 border-b border-gray-200">
        <button
          onClick={onNewChat}
          className="w-full text-left px-3 py-2 rounded text-sm font-medium text-blue-600 hover:bg-blue-50 transition-colors"
        >
          + New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && (
          <p className="text-xs text-gray-400 px-4 py-3">Loading sessions…</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="text-xs text-gray-400 px-4 py-3">No sessions yet</p>
        )}
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors ${
              s.id === activeId ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
            }`}
          >
            <p className="text-sm font-medium text-gray-800 truncate">
              {s.title ?? 'Untitled chat'}
            </p>
            {s.last_message_preview && (
              <p className="text-xs text-gray-400 truncate mt-0.5">{s.last_message_preview}</p>
            )}
            <p className="text-xs text-gray-300 mt-0.5">
              {s.message_count} {s.message_count === 1 ? 'message' : 'messages'}
            </p>
          </button>
        ))}
      </div>
    </aside>
  )
}
