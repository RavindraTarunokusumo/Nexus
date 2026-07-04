import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CitationList } from '../components/CitationList'
import { HowItWorks } from '../components/HowItWorks'
import { MermaidBlock } from '../components/MermaidBlock'
import {
  buildPipelineDiagram,
  buildProvenanceDiagram,
  sanitizeLabel,
  type AnswerMeta,
  type ProvenanceData,
} from '../lib/mermaid'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockRejectedValue(new Error('render failed')),
  },
}))

const SAMPLE_META: AnswerMeta = {
  question: 'What changed in GPT-5?',
  question_shape: 'factoid',
  query_intent: 'what_changed',
  tokens_used: 150,
  citations: [
    { document_id: 'd1', capsule_id: 'c1', document_title: 'A', url: null, score: 0.9, object_type: null, object_family: null, lifecycle_state: 'active', summary: 's', evidence: [], role: 'primary' },
    { document_id: 'd2', capsule_id: 'c2', document_title: 'B', url: null, score: 0.8, object_type: null, object_family: null, lifecycle_state: 'active', summary: 's', evidence: [], role: 'counter_evidence' },
  ],
}

const SAMPLE_PROVENANCE: ProvenanceData = {
  capsule: { id: 'cap-1', text: 'GPT-5 released', lifecycle_state: 'active' },
  document: { id: 'doc-1', title: 'Release notes' },
  spans: [{ id: 'span-1', span_index: 0, text_excerpt: 'On July 1…' }],
  relations: [
    {
      id: 'rel-1',
      direction: 'out',
      relation_type: 'supersedes',
      other_capsule: { id: 'cap-2', text_excerpt: 'GPT-4 context', lifecycle_state: 'superseded' },
    },
  ],
  theses: [{ id: 'thesis-1', statement_excerpt: 'GPT-5 is faster' }],
}

describe('buildPipelineDiagram', () => {
  it('includes shape node and role counts', () => {
    const diagram = buildPipelineDiagram(SAMPLE_META)
    expect(diagram).toContain('flowchart LR')
    expect(diagram).toContain('factoid')
    expect(diagram).toContain('what_changed')
    expect(diagram).toContain('primary: 1')
    expect(diagram).toContain('counter: 1')
    expect(diagram).toContain('150 tokens')
  })

  it('sanitizes mermaid-significant characters in labels', () => {
    const diagram = buildPipelineDiagram({
      ...SAMPLE_META,
      question: 'What about ["brackets"] and |pipes|?',
    })
    expect(diagram).not.toContain('["brackets"]')
    expect(diagram).toContain('brackets')
  })
})

describe('sanitizeLabel', () => {
  it('caps label length at 60 characters', () => {
    const long = 'a'.repeat(80)
    expect(sanitizeLabel(long).length).toBe(60)
    expect(sanitizeLabel(long).endsWith('…')).toBe(true)
  })
})

describe('buildProvenanceDiagram', () => {
  it('includes relation labels and lifecycle classDefs', () => {
    const diagram = buildProvenanceDiagram(SAMPLE_PROVENANCE)
    expect(diagram).toContain('Document: Release notes')
    expect(diagram).toContain('Span #0')
    expect(diagram).toContain('-->|supersedes|')
    expect(diagram).toContain('Thesis: GPT-5 is faster')
    expect(diagram).toContain('classDef active')
    expect(diagram).toContain('class cap active')
  })

  it('handles empty spans, relations, and theses', () => {
    const diagram = buildProvenanceDiagram({
      capsule: { id: 'c', text: 'solo', lifecycle_state: 'candidate' },
      document: { id: 'd', title: null },
      spans: [],
      relations: [],
      theses: [],
    })
    expect(diagram).toContain('doc --> cap')
    expect(diagram).not.toContain('thesis')
    expect(diagram).not.toContain('-->|')
  })
})

describe('CitationList role badges', () => {
  const base = {
    document_id: 'd1',
    capsule_id: 'c1',
    document_title: 'Doc',
    url: null,
    score: 0.9,
    object_type: null,
    object_family: null,
    lifecycle_state: 'active',
    summary: 'summary text',
    evidence: [],
  }

  it('renders primary badge', () => {
    render(<CitationList citations={[{ ...base, role: 'primary' }]} />)
    expect(screen.getByText('primary')).toBeInTheDocument()
  })

  it('renders counter_evidence badge as counter', () => {
    render(<CitationList citations={[{ ...base, role: 'counter_evidence' }]} />)
    expect(screen.getByText('counter')).toBeInTheDocument()
  })

  it('omits role badge when role is null', () => {
    render(<CitationList citations={[{ ...base, role: null }]} />)
    expect(screen.queryByText('primary')).not.toBeInTheDocument()
    expect(screen.queryByText('counter')).not.toBeInTheDocument()
    expect(screen.queryByText('supersession')).not.toBeInTheDocument()
  })

  it('sets epistemic_note as title tooltip', () => {
    render(
      <CitationList
        citations={[{ ...base, role: 'primary', epistemic_note: 'High confidence' }]}
      />,
    )
    expect(screen.getByRole('button')).toHaveAttribute('title', 'High confidence')
  })
})

describe('HowItWorks', () => {
  it('shows empty state when lastAnswerMeta is null', () => {
    render(<HowItWorks lastAnswerMeta={null} />)
    expect(screen.getByText(/ask a question in the chat tab first/i)).toBeInTheDocument()
    expect(screen.getByText('Pipeline routing')).toBeInTheDocument()
    expect(screen.getByText('Provenance chain')).toBeInTheDocument()
  })
})

describe('MermaidBlock error boundary', () => {
  it('falls back to raw diagram text when mermaid render fails', async () => {
    const diagram = 'flowchart LR\n  A --> B'
    render(<MermaidBlock diagram={diagram} />)
    await waitFor(() => {
      expect(screen.getByText(/flowchart LR/)).toBeInTheDocument()
    })
    expect(screen.getByText(/A --> B/)).toBeInTheDocument()
  })
})