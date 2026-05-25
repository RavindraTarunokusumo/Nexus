import type { ChatMessage } from '../api/client'
import { CitationList } from './CitationList'

type Props = {
  message: ChatMessage
  isPending?: boolean
}

export function MessageBubble({ message, isPending = false }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-2xl rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-white border border-gray-200 text-gray-800'
        } ${isPending ? 'opacity-60' : ''}`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        {!isUser && message.citations && message.citations.length > 0 && (
          <CitationList citations={message.citations} />
        )}
        {!isUser && message.tokens_used !== undefined && message.tokens_used > 0 && (
          <p className="text-xs text-gray-400 mt-2">
            {message.tokens_used} tokens
            {message.cost_estimate_usd !== undefined && message.cost_estimate_usd > 0
              ? ` · $${message.cost_estimate_usd.toFixed(6)}`
              : ''}
          </p>
        )}
      </div>
    </div>
  )
}
