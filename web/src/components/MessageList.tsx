import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../api/client'
import { MessageBubble } from './MessageBubble'

type Props = {
  messages: ChatMessage[]
  sending: boolean
}

export function MessageList({ messages, sending }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  if (messages.length === 0 && !sending) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Ask a question to start the conversation.
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} isPending={m.id.startsWith('pending-')} />
      ))}
      {sending && (
        <div className="flex justify-start mb-4">
          <div className="bg-gray-100 border border-gray-200 rounded-lg px-4 py-3">
            <span className="text-sm text-gray-400 italic" aria-live="polite">
              Thinking…
            </span>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
