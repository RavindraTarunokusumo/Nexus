const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type ApiError = {
  status: number | null
  message: string
}

export type ChatSessionSummary = {
  id: string
  title: string | null
  status: 'active' | 'archived'
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview: string | null
}

export type ChatCitation = {
  document_id: string
  capsule_id: string
  document_title: string | null
  url: string | null
  score: number
  object_type: string | null
  object_family: string | null
  lifecycle_state: string | null
  summary: string
  evidence: { span_id: string; span_index: number; text: string }[]
  role?: string | null
  epistemic_note?: string | null
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  run_id?: string
  citations?: ChatCitation[]
  retrieved_context_count?: number
  tokens_used?: number
  cost_estimate_usd?: number
  question_shape?: string | null
  query_intent?: string | null
}

export type ChatSessionDetail = ChatSessionSummary & {
  messages: ChatMessage[]
}

export type SendMessageResponse = {
  session: ChatSessionSummary
  user_message: ChatMessage
  assistant_message: ChatMessage
}

export type StatsCounts = {
  documents: number
  spans: number
  capsules: number
  relations: number
  theses: number
}

export type ModelUsageRow = {
  run_type: string
  model: string
  calls: number
  prompt_tokens: number
  completion_tokens: number
  cost_estimate_usd: number
}

export type StatsOverview = {
  counts: StatsCounts
  lifecycle: Record<string, number>
  model_usage: ModelUsageRow[]
}

export type CapsuleProvenance = {
  capsule: {
    id: string
    text: string
    object_family: string
    domain_object_type: string
    core_type: string
    lifecycle_state: string
    salience: number
    confidence: number
    created_at: string
  }
  document: {
    id: string
    title: string | null
    url: string | null
    published_at: string | null
  }
  spans: { id: string; span_index: number; text_excerpt: string }[]
  relations: {
    id: string
    direction: string
    relation_type: string
    polarity: string | null
    strength: number
    other_capsule: { id: string; text_excerpt: string; lifecycle_state: string }
  }[]
  theses: { id: string; statement_excerpt: string }[]
}

class ApiCallError extends Error {
  readonly apiError: ApiError
  constructor(apiError: ApiError, message: string) {
    super(message)
    this.apiError = apiError
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
  } catch {
    throw new ApiCallError({ status: null, message: 'Network error — is the server running?' }, 'Network error')
  }

  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // ignore parse errors
    }
    throw new ApiCallError({ status: response.status, message }, message)
  }

  return response.json() as Promise<T>
}

export function normalizeApiError(err: unknown): ApiError {
  if (err instanceof ApiCallError) return err.apiError
  if (err instanceof Error) return { status: null, message: err.message }
  return { status: null, message: 'Unknown error' }
}

export const api = {
  listSessions(status: 'active' | 'archived' = 'active', limit = 30): Promise<ChatSessionSummary[]> {
    return request(`/chat/sessions?status=${status}&limit=${limit}`)
  },

  getSession(id: string): Promise<ChatSessionDetail> {
    return request(`/chat/sessions/${id}`)
  },

  createSession(title?: string): Promise<ChatSessionSummary> {
    return request('/chat/sessions', {
      method: 'POST',
      body: JSON.stringify({ title: title ?? null }),
    })
  },

  sendMessage(sessionId: string, content: string, topK = 8): Promise<SendMessageResponse> {
    return request(`/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, top_k: topK }),
    })
  },

  patchSession(
    id: string,
    patch: { title?: string; status?: 'active' | 'archived' },
  ): Promise<ChatSessionSummary> {
    return request(`/chat/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  },

  getStatsOverview(): Promise<StatsOverview> {
    return request('/stats/overview')
  },

  getCapsuleProvenance(capsuleId: string): Promise<CapsuleProvenance> {
    return request(`/capsules/${capsuleId}/provenance`)
  },
}
