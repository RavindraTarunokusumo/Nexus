import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, normalizeApiError } from '../api/client'

const fetchMock = vi.fn()
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  vi.unstubAllGlobals()
})

function mockResponse(body: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
}

describe('api.listSessions', () => {
  it('calls GET /chat/sessions with status=active', async () => {
    mockResponse([])
    await api.listSessions('active')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/chat/sessions?status=active'),
      expect.any(Object),
    )
  })
})

describe('api.createSession', () => {
  it('calls POST /chat/sessions', async () => {
    const session = { id: 'abc', title: null, status: 'active', created_at: '', updated_at: '', message_count: 0, last_message_preview: null }
    mockResponse(session, 201)
    const result = await api.createSession()
    expect(result.id).toBe('abc')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/chat/sessions'),
      expect.objectContaining({ method: 'POST' }),
    )
  })
})

describe('api error handling', () => {
  it('throws ApiError with status and message on 404', async () => {
    mockResponse({ detail: 'Session not found.' }, 404)
    await expect(api.getSession('missing')).rejects.toMatchObject({
      apiError: { status: 404, message: 'Session not found.' },
    })
  })

  it('returns status null on network failure', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api.listSessions()).rejects.toMatchObject({
      apiError: { status: null },
    })
  })
})

describe('normalizeApiError', () => {
  it('normalizes plain Error', () => {
    const err = normalizeApiError(new Error('oops'))
    expect(err).toEqual({ status: null, message: 'oops' })
  })

  it('normalizes unknown value', () => {
    const err = normalizeApiError('wat')
    expect(err).toEqual({ status: null, message: 'Unknown error' })
  })
})
