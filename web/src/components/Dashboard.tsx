import { useCallback, useEffect, useRef, useState } from 'react'
import { api, normalizeApiError, type StatsOverview } from '../api/client'

const COUNT_LABELS: { key: keyof StatsOverview['counts']; label: string }[] = [
  { key: 'documents', label: 'Documents' },
  { key: 'spans', label: 'Spans' },
  { key: 'capsules', label: 'Capsules' },
  { key: 'relations', label: 'Relations' },
  { key: 'theses', label: 'Theses' },
]

function formatTokens(prompt: number, completion: number): string {
  const total = prompt + completion
  return `${total.toLocaleString()} (${prompt.toLocaleString()} + ${completion.toLocaleString()})`
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

export function Dashboard() {
  const [data, setData] = useState<StatsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestGenRef = useRef(0)

  const fetchOverview = useCallback(() => {
    const gen = ++requestGenRef.current
    return api
      .getStatsOverview()
      .then((overview) => {
        if (gen !== requestGenRef.current) return
        setData(overview)
        setError(null)
      })
      .catch((err) => {
        if (gen !== requestGenRef.current) return
        setError(normalizeApiError(err).message)
        setData(null)
      })
      .finally(() => {
        if (gen === requestGenRef.current) setLoading(false)
      })
  }, [])

  useEffect(() => {
    void fetchOverview()
    const gen = requestGenRef
    return () => {
      gen.current++
    }
  }, [fetchOverview])

  const handleRefresh = () => {
    setLoading(true)
    setError(null)
    void fetchOverview()
  }

  const lifecycle = data?.lifecycle ?? {}
  const lifecycleTotal = Object.values(lifecycle).reduce((sum, n) => sum + n, 0)
  const lifecycleSegments = Object.entries(lifecycle)
    .filter(([, count]) => count > 0)
    .sort(([a], [b]) => a.localeCompare(b))

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Memory overview</h1>
        <button
          type="button"
          className="dashboard-refresh"
          onClick={handleRefresh}
          disabled={loading}
          aria-label="Refresh stats"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="dashboard-error" role="alert">
          {error}
        </div>
      )}

      {loading && !data && !error && <p className="dashboard-loading">Loading stats…</p>}

      {(data || (!loading && !error)) && (
        <>
          <section className="count-cards" aria-label="Entity counts">
            {COUNT_LABELS.map(({ key, label }) => (
              <div key={key} className="count-card">
                <span className="count-card-value">{data?.counts[key] ?? 0}</span>
                <span className="count-card-label">{label}</span>
              </div>
            ))}
          </section>

          <section className="lifecycle-section" aria-label="Capsule lifecycle distribution">
            <h2 className="section-heading">Capsule lifecycle</h2>
            <div className="lifecycle-bar" role="img" aria-label="Lifecycle distribution bar">
              {lifecycleTotal === 0 ? (
                <div className="lifecycle-bar-empty">No capsules yet</div>
              ) : (
                lifecycleSegments.map(([state, count]) => (
                  <div
                    key={state}
                    className={`lifecycle-segment lifecycle-${state}`}
                    style={{ flexGrow: count }}
                    title={`${state}: ${count}`}
                  />
                ))
              )}
            </div>
            {lifecycleTotal > 0 && (
              <ul className="lifecycle-legend">
                {lifecycleSegments.map(([state, count]) => {
                  const pct = Math.round((count / lifecycleTotal) * 100)
                  return (
                    <li key={state} className="lifecycle-legend-item">
                      <span className={`lifecycle-swatch lifecycle-${state}`} aria-hidden="true" />
                      <span className="lifecycle-legend-label">{state}</span>
                      <span className="lifecycle-legend-count">
                        {count} ({pct}%)
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <section className="model-usage-section" aria-label="Model usage">
            <h2 className="section-heading">Model usage</h2>
            {(data?.model_usage.length ?? 0) === 0 ? (
              <p className="dashboard-empty">No agent runs recorded yet.</p>
            ) : (
              <table className="model-usage-table">
                <thead>
                  <tr>
                    <th scope="col">Run type</th>
                    <th scope="col">Model</th>
                    <th scope="col">Calls</th>
                    <th scope="col">Tokens</th>
                    <th scope="col">Est. cost</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.model_usage.map((row) => (
                    <tr key={`${row.run_type}-${row.model}`}>
                      <td>{row.run_type}</td>
                      <td>{row.model || '—'}</td>
                      <td>{row.calls.toLocaleString()}</td>
                      <td>{formatTokens(row.prompt_tokens, row.completion_tokens)}</td>
                      <td>{formatCost(row.cost_estimate_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  )
}
