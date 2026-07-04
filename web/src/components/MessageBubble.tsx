import type { ChatMessage } from '../api/client'
import { CitationList } from './CitationList'

type Props = {
  message: ChatMessage
  isPending?: boolean
}

export function MessageBubble({ message, isPending = false }: Props) {
  const isUser = message.role === 'user'
  const shape = message.question_shape ?? 'general'
  const intent = message.query_intent ?? 'general'
  const showExplain =
    !isUser &&
    !(shape === 'general' && intent === 'general') &&
    (message.question_shape || message.query_intent || message.tokens_used)

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
        {showExplain && (
            <details className="message-explain mt-2 text-xs text-gray-500">
              <summary className="cursor-pointer hover:text-gray-700">Explain</summary>
              <dl className="mt-1 space-y-0.5 pl-1">
                {message.question_shape && (
                  <>
                    <dt className="inline font-medium">Shape:</dt>
                    <dd className="inline ml-1">{message.question_shape}</dd>
                    <br />
                  </>
                )}
                {message.query_intent && (
                  <>
                    <dt className="inline font-medium">Intent:</dt>
                    <dd className="inline ml-1">{message.query_intent}</dd>
                    <br />
                  </>
                )}
                {message.tokens_used !== undefined && message.tokens_used > 0 && (
                  <>
                    <dt className="inline font-medium">Tokens:</dt>
                    <dd className="inline ml-1">
                      {message.tokens_used}
                      {message.cost_estimate_usd !== undefined &&
                      message.cost_estimate_usd > 0
                        ? ` ($${message.cost_estimate_usd.toFixed(6)})`
                        : ''}
                    </dd>
                  </>
                )}
              </dl>
            </details>
          )}
      </div>
    </div>
  )
}
