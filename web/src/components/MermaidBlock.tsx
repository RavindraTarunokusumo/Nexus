import {
  Component,
  type ErrorInfo,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react'
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

type MermaidErrorBoundaryProps = {
  diagram: string
  children: ReactNode
}

type MermaidErrorBoundaryState = {
  hasError: boolean
}

class MermaidErrorBoundary extends Component<
  MermaidErrorBoundaryProps,
  MermaidErrorBoundaryState
> {
  state: MermaidErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): MermaidErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn('Mermaid render failed:', error, info)
  }

  componentDidUpdate(prevProps: MermaidErrorBoundaryProps): void {
    if (prevProps.diagram !== this.props.diagram && this.state.hasError) {
      this.setState({ hasError: false })
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <pre className="mermaid-fallback">{this.props.diagram}</pre>
    }
    return this.props.children
  }
}

type MermaidBlockProps = {
  diagram: string
}

function MermaidRenderer({ diagram }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)
  const reactId = useId()
  const renderId = `mermaid-${reactId.replace(/:/g, '')}`

  useEffect(() => {
    initMermaid()
    const el = containerRef.current
    if (!el) return

    let cancelled = false
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

export function MermaidBlock({ diagram }: MermaidBlockProps) {
  return (
    <MermaidErrorBoundary diagram={diagram}>
      <MermaidRenderer key={diagram} diagram={diagram} />
    </MermaidErrorBoundary>
  )
}