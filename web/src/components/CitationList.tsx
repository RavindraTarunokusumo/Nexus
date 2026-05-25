import { useState } from 'react'
import type { ChatCitation } from '../api/client'

type Props = {
  citations: ChatCitation[]
}

function shortId(id: string): string {
  return id.slice(0, 8)
}

function urlHost(url: string | null): string {
  if (!url) return '—'
  try {
    return new URL(url).hostname
  } catch {
    return url.slice(0, 40)
  }
}

export function CitationList({ citations }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (citations.length === 0) return null

  return (
    <div className="mt-2 border border-gray-200 rounded text-xs">
      <p className="px-3 py-1.5 text-gray-500 font-medium border-b border-gray-200">
        Citations
      </p>
      {citations.map((c) => (
        <div key={c.span_id} className="border-b border-gray-100 last:border-0">
          <button
            onClick={() => setExpanded(expanded === c.span_id ? null : c.span_id)}
            className="w-full text-left px-3 py-1.5 hover:bg-gray-50 flex items-center gap-3"
          >
            <span className="font-medium text-gray-700 truncate flex-1">
              {c.document_title ?? shortId(c.document_id)}
            </span>
            <span className="text-gray-500 tabular-nums">{c.score.toFixed(2)}</span>
            <span className="text-gray-400 truncate max-w-32">{urlHost(c.url)}</span>
            <span className="text-gray-300 font-mono">{shortId(c.span_id)}</span>
            <span className="text-gray-400">{c.claim_ids.length} claims</span>
          </button>

          {expanded === c.span_id && (
            <div className="px-3 py-2 bg-gray-50 text-gray-600 space-y-1">
              {c.url && (
                <p>
                  URL:{' '}
                  <a href={c.url} className="text-blue-600 underline break-all" target="_blank" rel="noreferrer">
                    {c.url}
                  </a>
                </p>
              )}
              <p>Span: <span className="font-mono">{c.span_id}</span></p>
              <p>Document: <span className="font-mono">{c.document_id}</span></p>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
