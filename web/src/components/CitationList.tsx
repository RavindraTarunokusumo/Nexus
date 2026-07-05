import { useState } from 'react'
import type { ChatCitation } from '../api/client'
import { shortId } from '../lib/ids'

type Props = {
  citations: ChatCitation[]
}

function urlHost(url: string | null): string {
  if (!url) return '—'
  try {
    return new URL(url).hostname
  } catch {
    return url.slice(0, 40)
  }
}

function lifecycleDotClass(state: string | null): string {
  if (state === 'active' || state === 'confirmed') return 'bg-green-500'
  if (state === 'candidate') return 'bg-amber-400'
  return 'bg-gray-400'
}

function roleBadgeClass(role: string): string {
  if (role === 'primary') return 'citation-role-primary'
  if (role === 'counter_evidence') return 'citation-role-counter'
  if (role === 'supersession') return 'citation-role-supersession'
  return 'citation-role-default'
}

function roleLabel(role: string): string {
  if (role === 'counter_evidence') return 'counter'
  return role.replace(/_/g, ' ')
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
        <div key={c.capsule_id} className="border-b border-gray-100 last:border-0">
          <button
            onClick={() => setExpanded(expanded === c.capsule_id ? null : c.capsule_id)}
            title={c.epistemic_note ?? undefined}
            className="w-full text-left px-3 py-1.5 hover:bg-gray-50 flex items-center gap-2"
          >
            <span
              className={`lifecycle-dot inline-block w-2 h-2 rounded-full flex-shrink-0 ${lifecycleDotClass(c.lifecycle_state)}`}
            />
            {c.role && (
              <span
                className={`citation-role-badge rounded px-1 py-0.5 uppercase tracking-wide text-[10px] flex-shrink-0 ${roleBadgeClass(c.role)}`}
              >
                {roleLabel(c.role)}
              </span>
            )}
            {c.object_type && (
              <span className="bg-blue-100 text-blue-700 rounded px-1 py-0.5 uppercase tracking-wide text-[10px] flex-shrink-0">
                {c.object_type.toUpperCase()}
              </span>
            )}
            <span className="font-medium text-gray-700 truncate flex-1">
              {c.document_title ?? shortId(c.document_id)}
            </span>
            <span className="text-gray-500 tabular-nums">{c.score.toFixed(2)}</span>
            <span className="text-gray-400 truncate max-w-32">{urlHost(c.url)}</span>
            <span className="text-gray-500 truncate max-w-48 italic">{c.summary}</span>
          </button>

          {expanded === c.capsule_id && (
            <div className="px-3 py-2 bg-gray-50 text-gray-600 space-y-1">
              <p className="line-clamp-3">{c.summary}</p>
              {c.url && (
                <p>
                  URL:{' '}
                  <a href={c.url} className="text-blue-600 underline break-all" target="_blank" rel="noreferrer">
                    {c.url}
                  </a>
                </p>
              )}
              <p>Capsule: <span className="font-mono">{c.capsule_id}</span></p>
              <p>Document: <span className="font-mono">{c.document_id}</span></p>
              {c.evidence && c.evidence.length > 0 && (
                <div className="pt-1 border-t border-gray-200">
                  <p className="font-medium text-gray-500">Evidence</p>
                  <ul className="space-y-0.5">
                    {c.evidence.map((e) => (
                      <li key={e.span_id} className="text-gray-600">
                        <span className="text-gray-400 font-mono mr-1">#{e.span_index}</span>
                        {e.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
