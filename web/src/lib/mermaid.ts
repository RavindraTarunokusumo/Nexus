import type { CapsuleProvenance, ChatCitation } from '../api/client'

// Source of truth: app/intelligence/router.py STRATEGIES
export const SHAPE_STRATEGIES: Record<string, string> = {
  factoid: 'semantic_similarity boost, fetch_k×6 — verbatim dates/numbers',
  multi_doc: 'top_k+3, fetch_k×4 — synthesize across blocks',
  current_state: 'supersession aux blocks — prefer most recent fact',
  conflict: 'source_authority + evidence_quality boost — distinguish verified sources',
  general: 'default hybrid scoring',
}

export type AnswerMeta = {
  question: string
  question_shape: string
  query_intent: string
  tokens_used: number
  citations: ChatCitation[]
}

const MERMAID_SPECIAL = /[[\](){}|"#;:<>\\]/g

export function sanitizeLabel(text: string, maxLen = 60): string {
  const cleaned = text.replace(MERMAID_SPECIAL, '').replace(/\s+/g, ' ').trim()
  if (cleaned.length <= maxLen) return cleaned
  return `${cleaned.slice(0, maxLen - 1)}…`
}

function countCitationRoles(citations: ChatCitation[]): {
  primary: number
  counter: number
  supersession: number
} {
  let primary = 0
  let counter = 0
  let supersession = 0
  for (const c of citations) {
    if (c.role === 'primary') primary++
    else if (c.role === 'counter_evidence') counter++
    else if (c.role === 'supersession') supersession++
  }
  return { primary, counter, supersession }
}

export function buildPipelineDiagram(meta: AnswerMeta): string {
  const question = sanitizeLabel(meta.question)
  const shape = sanitizeLabel(meta.question_shape)
  const intent = sanitizeLabel(meta.query_intent)
  const strategy =
    SHAPE_STRATEGIES[meta.question_shape] ?? SHAPE_STRATEGIES.general
  const strategyLabel = sanitizeLabel(strategy)
  const { primary, counter, supersession } = countCitationRoles(meta.citations)
  const tokens = meta.tokens_used

  return [
    'flowchart LR',
    `  Q["Question: ${question}"]`,
    `  C["Classify T2\\n${intent} / ${shape}"]`,
    `  R["Retrieval: ${shape}\\n${strategyLabel}"]`,
    `  CB["Context blocks\\nprimary: ${primary}\\ncounter: ${counter}\\nsupersession: ${supersession}"]`,
    `  A["Answer T2\\n${tokens} tokens"]`,
    '  Q --> C',
    '  C --> R',
    '  R --> CB',
    '  CB --> A',
  ].join('\n')
}

const LIFECYCLE_CLASS_DEFS = [
  'classDef active fill:#d1fae5,stroke:#059669',
  'classDef confirmed fill:#d1fae5,stroke:#059669',
  'classDef candidate fill:#fef3c7,stroke:#d97706',
  'classDef superseded fill:#f3f4f6,stroke:#9ca3af',
  'classDef default_lc fill:#e5e7eb,stroke:#6b7280',
]

function lifecycleClass(state: string | null | undefined): string {
  if (state === 'active' || state === 'confirmed') return 'active'
  if (state === 'candidate') return 'candidate'
  if (state === 'superseded') return 'superseded'
  return 'default_lc'
}

export function buildProvenanceDiagram(prov: CapsuleProvenance): string {
  const lines: string[] = ['flowchart LR']
  const classAssignments: string[] = []

  const docTitle = sanitizeLabel(prov.document.title ?? prov.document.id.slice(0, 8))
  lines.push(`  doc["Document: ${docTitle}"]`)

  const capExcerpt = sanitizeLabel(prov.capsule.text)
  const capState = prov.capsule.lifecycle_state
  lines.push(`  cap["Capsule: ${capExcerpt}\\n(${capState})"]`)
  classAssignments.push(`class cap ${lifecycleClass(capState)}`)

  if (prov.spans.length === 0) {
    lines.push('  doc --> cap')
  } else {
    prov.spans.forEach((span, i) => {
      const nodeId = `span${i}`
      const excerpt = sanitizeLabel(span.text_excerpt)
      lines.push(`  ${nodeId}["Span #${span.span_index}: ${excerpt}"]`)
      lines.push(`  doc --> ${nodeId}`)
      lines.push(`  ${nodeId} --> cap`)
    })
  }

  prov.relations.forEach((rel, i) => {
    const otherId = `other${i}`
    const label = sanitizeLabel(rel.relation_type)
    const excerpt = sanitizeLabel(rel.other_capsule.text_excerpt)
    const state = rel.other_capsule.lifecycle_state
    lines.push(`  ${otherId}["${excerpt}\\n(${state})"]`)
    lines.push(`  cap -->|${label}| ${otherId}`)
    classAssignments.push(`class ${otherId} ${lifecycleClass(state)}`)
  })

  prov.theses.forEach((thesis, i) => {
    const nodeId = `thesis${i}`
    const excerpt = sanitizeLabel(thesis.statement_excerpt)
    lines.push(`  ${nodeId}["Thesis: ${excerpt}"]`)
    lines.push(`  cap --> ${nodeId}`)
  })

  lines.push(...LIFECYCLE_CLASS_DEFS)
  lines.push(...classAssignments)

  return lines.join('\n')
}