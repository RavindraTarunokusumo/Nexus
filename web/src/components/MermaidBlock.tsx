import { useEffect, useId, useRef, useState } from 'react'
import mermaid from 'mermaid'

let mermaidInitialized = false

function initMermaid(): void {
  if (mermaidInitialized) return
  mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    securityLevel: 'strict',
    flowchart: { htmlLabels: false },
  })
  mermaidInitialized = true
}

type MermaidBlockProps = {
  diagram: string
}

export function MermaidBlock({ diagram }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)
  const reactId = useId()
  const renderId = `mermaid-${reactId.replace(/:/g, '')}`

  useEffect(() => {
    initMermaid()
    const el = containerRef.current
    if (!el) return

    let cancelled = false
    setFailed(false)
    el.innerHTML = ''

    void mermaid
      .render(renderId, diagram)
      .then(({ svg }) => {
        if (!cancelled) el.innerHTML = svg
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
    }
  }, [diagram, renderId])

  if (failed) {
    return <pre className="mermaid-fallback">{diagram}</pre>
  }

  return <div ref={containerRef} className="mermaid-block" />
}