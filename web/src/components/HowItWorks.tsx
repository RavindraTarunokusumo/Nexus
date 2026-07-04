import { useCallback, useRef, useState } from 'react'
import { api, normalizeApiError, type CapsuleProvenance } from '../api/client'
import { buildPipelineDiagram, buildProvenanceDiagram, type AnswerMeta } from '../lib/mermaid'
import { shortId } from '../lib/ids'
import { MermaidBlock } from './MermaidBlock'

type Props = {
  lastAnswerMeta: AnswerMeta | null
}

export function HowItWorks({ lastAnswerMeta }: Props) {
  const [capsuleId, setCapsuleId] = useState('')
  const [provenance, setProvenance] = useState<CapsuleProvenance | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const citationCapsuleIds = lastAnswerMeta
    ? [...new Set(lastAnswerMeta.citations.map((c) => c.capsule_id))]
    : []

  const fetchProvenance = useCallback(async (id: string) => {
    const trimmed = id.trim()
    if (!trimmed) return
    const requestId = ++requestIdRef.current
    setLoading(true)
    setError(null)
    setProvenance(null)
    try {
      const data = await api.getCapsuleProvenance(trimmed)
      if (requestId !== requestIdRef.current) return
      setProvenance(data)
      setCapsuleId(trimmed)
    } catch (err) {
      if (requestId !== requestIdRef.current) return
      const apiErr = normalizeApiError(err)
      setError(apiErr.message)
    } finally {
      if (requestId === requestIdRef.current) setLoading(false)
    }
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    void fetchProvenance(capsuleId)
  }

  return (
    <div className="how-it-works">
      <section className="how-it-works-section">
        <h2 className="how-it-works-heading">Pipeline routing</h2>
        {lastAnswerMeta ? (
          <MermaidBlock diagram={buildPipelineDiagram(lastAnswerMeta)} />
        ) : (
          <p className="how-it-works-empty">
            Ask a question in the Chat tab first — the pipeline diagram will appear here
            after your first answer.
          </p>
        )}
      </section>

      <section className="how-it-works-section">
        <h2 className="how-it-works-heading">Provenance chain</h2>
        <form className="provenance-picker" onSubmit={handleSubmit}>
          <label htmlFor="capsule-id-input" className="provenance-label">
            Capsule ID
          </label>
          <div className="provenance-input-row">
            <input
              id="capsule-id-input"
              type="text"
              value={capsuleId}
              onChange={(e) => setCapsuleId(e.target.value)}
              placeholder="Paste a capsule UUID"
              className="provenance-input"
            />
            <button
              type="submit"
              disabled={loading || !capsuleId.trim()}
              className="provenance-submit"
            >
              {loading ? 'Loading…' : 'Load'}
            </button>
          </div>
        </form>

        {citationCapsuleIds.length > 0 && (
          <div className="provenance-shortcuts">
            <span className="provenance-shortcuts-label">From last answer:</span>
            {citationCapsuleIds.map((id) => (
              <button
                key={id}
                type="button"
                className="provenance-shortcut"
                onClick={() => void fetchProvenance(id)}
                disabled={loading}
              >
                {shortId(id)}
              </button>
            ))}
          </div>
        )}

        {error && (
          <p className="provenance-error" role="alert">
            {error}
          </p>
        )}

        {provenance && !error && (
          <MermaidBlock diagram={buildProvenanceDiagram(provenance)} />
        )}
      </section>
    </div>
  )
}