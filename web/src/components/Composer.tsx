import { type FormEvent, useRef, useState } from 'react'

type Props = {
  disabled: boolean
  sending: boolean
  archived: boolean
  onSubmit: (content: string) => void
}

export function Composer({ disabled, sending, archived, onSubmit }: Props) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || disabled || sending || archived) return
    onSubmit(trimmed)
    setText('')
    textareaRef.current?.focus()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as FormEvent)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-t border-gray-200 px-4 py-3 bg-white flex items-end gap-2"
    >
      {archived ? (
        <p className="flex-1 text-sm text-gray-400 py-2">
          This session is archived. Start a new chat to continue.
        </p>
      ) : (
        <>
          <label htmlFor="composer-input" className="sr-only">
            Message
          </label>
          <textarea
            id="composer-input"
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
            className="flex-1 resize-none border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            disabled={sending}
          />
          <button
            type="submit"
            disabled={!text.trim() || sending || disabled}
            aria-label={sending ? 'Sending…' : 'Send message'}
            className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors"
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </>
      )}
    </form>
  )
}
