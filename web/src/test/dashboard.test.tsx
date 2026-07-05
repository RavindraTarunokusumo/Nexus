import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Dashboard } from '../components/Dashboard'
import { api } from '../api/client'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      getStatsOverview: vi.fn(),
    },
  }
})

const MOCK_OVERVIEW = {
  counts: {
    documents: 12,
    spans: 48,
    capsules: 30,
    relations: 8,
    theses: 3,
  },
  lifecycle: {
    active: 15,
    confirmed: 10,
    superseded: 5,
  },
  model_usage: [
    {
      run_type: 'chat_answer',
      model: 'gpt-4o-mini',
      calls: 42,
      prompt_tokens: 12000,
      completion_tokens: 3000,
      cost_estimate_usd: 0.045,
    },
  ],
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.mocked(api.getStatsOverview).mockReset()
  })

  it('renders count cards and lifecycle bar from fetched data', async () => {
    vi.mocked(api.getStatsOverview).mockResolvedValueOnce(MOCK_OVERVIEW)
    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByText('12')).toBeInTheDocument()
    })

    expect(screen.getByText('Documents')).toBeInTheDocument()
    expect(screen.getByText('48')).toBeInTheDocument()
    expect(screen.getByText('Spans')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('Capsules')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.getByText('Relations')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Theses')).toBeInTheDocument()

    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByText('confirmed')).toBeInTheDocument()
    expect(screen.getByText('superseded')).toBeInTheDocument()
    expect(screen.getByLabelText('Lifecycle distribution bar')).toBeInTheDocument()

    expect(screen.getByText('chat_answer')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('shows error state when fetch fails', async () => {
    vi.mocked(api.getStatsOverview).mockRejectedValueOnce(new Error('Server exploded'))
    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Server exploded')
    })
  })

  it('renders zeros gracefully for an empty database', async () => {
    vi.mocked(api.getStatsOverview).mockResolvedValueOnce({
      counts: { documents: 0, spans: 0, capsules: 0, relations: 0, theses: 0 },
      lifecycle: {},
      model_usage: [],
    })
    render(<Dashboard />)

    await waitFor(() => {
      expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(5)
    })

    expect(screen.getByText('No capsules yet')).toBeInTheDocument()
    expect(screen.getByText('No agent runs recorded yet.')).toBeInTheDocument()
  })

  it('refetches when Refresh is clicked', async () => {
    vi.mocked(api.getStatsOverview)
      .mockResolvedValueOnce(MOCK_OVERVIEW)
      .mockResolvedValueOnce({
        ...MOCK_OVERVIEW,
        counts: { ...MOCK_OVERVIEW.counts, documents: 99 },
      })

    render(<Dashboard />)
    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /refresh stats/i }))
    await waitFor(() => expect(screen.getByText('99')).toBeInTheDocument())
    expect(api.getStatsOverview).toHaveBeenCalledTimes(2)
  })
})
