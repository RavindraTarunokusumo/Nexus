import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CitationList } from '../components/CitationList'
import { Composer } from '../components/Composer'
import { MessageBubble } from '../components/MessageBubble'
import { MessageList } from '../components/MessageList'
import { SessionSidebar } from '../components/SessionSidebar'
import type { ChatCitation, ChatMessage, ChatSessionSummary } from '../api/client'

const SESSION: ChatSessionSummary = {
  id: 's1',
  title: 'Test session',
  status: 'active',
  created_at: '2026-05-25T10:00:00Z',
  updated_at: '2026-05-25T10:05:00Z',
  message_count: 2,
  last_message_preview: 'Hello',
}

const USER_MSG: ChatMessage = {
  id: 'm1',
  role: 'user',
  content: 'What changed?',
  created_at: '2026-05-25T10:01:00Z',
}

const ASSISTANT_MSG: ChatMessage = {
  id: 'm2',
  role: 'assistant',
  content: 'Here is the answer.',
  created_at: '2026-05-25T10:01:05Z',
  citations: [],
  tokens_used: 100,
}

const CITATION: ChatCitation = {
  document_id: 'doc-uuid-1234',
  capsule_id: 'cap-uuid-5678',
  document_title: 'Release article',
  url: 'https://example.com/release',
  score: 0.91,
  object_type: 'model_release',
  object_family: 'technical_objects',
  lifecycle_state: 'active',
  summary: 'GPT-5 released with 128k context window.',
  evidence: [{ span_id: 's1', span_index: 0, text: 'supporting excerpt' }],
}

describe('SessionSidebar', () => {
  it('renders new chat button', () => {
    render(
      <SessionSidebar sessions={[]} activeId={null} loading={false} onNewChat={vi.fn()} onSelect={vi.fn()} />,
    )
    expect(screen.getByText('+ New chat')).toBeInTheDocument()
  })

  it('renders session list with title and preview', () => {
    render(
      <SessionSidebar sessions={[SESSION]} activeId={null} loading={false} onNewChat={vi.fn()} onSelect={vi.fn()} />,
    )
    expect(screen.getByText('Test session')).toBeInTheDocument()
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })

  it('calls onSelect when a session is clicked', async () => {
    const onSelect = vi.fn()
    render(
      <SessionSidebar sessions={[SESSION]} activeId={null} loading={false} onNewChat={vi.fn()} onSelect={onSelect} />,
    )
    await userEvent.click(screen.getByText('Test session'))
    expect(onSelect).toHaveBeenCalledWith('s1')
  })

  it('shows loading message while loading', () => {
    render(
      <SessionSidebar sessions={[]} activeId={null} loading={true} onNewChat={vi.fn()} onSelect={vi.fn()} />,
    )
    expect(screen.getByText(/loading sessions/i)).toBeInTheDocument()
  })
})

describe('MessageBubble', () => {
  it('renders user message right-aligned', () => {
    const { container } = render(<MessageBubble message={USER_MSG} />)
    expect(container.firstChild).toHaveClass('justify-end')
    expect(screen.getByText('What changed?')).toBeInTheDocument()
  })

  it('renders assistant message with citations placeholder', () => {
    const msg: ChatMessage = { ...ASSISTANT_MSG, citations: [CITATION] }
    render(<MessageBubble message={msg} />)
    expect(screen.getByText('Here is the answer.')).toBeInTheDocument()
    expect(screen.getByText('Citations')).toBeInTheDocument()
  })

  it('shows token count in explain disclosure for assistant messages', async () => {
    render(<MessageBubble message={ASSISTANT_MSG} />)
    await userEvent.click(screen.getByText('Explain'))
    expect(screen.getByText('100')).toBeInTheDocument()
  })
})

describe('CitationList', () => {
  it('renders nothing when citations are empty', () => {
    const { container } = render(<CitationList citations={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders object-type badge, score, host, and truncated summary', () => {
    render(<CitationList citations={[CITATION]} />)
    expect(screen.getByText('Release article')).toBeInTheDocument()
    expect(screen.getByText('0.91')).toBeInTheDocument()
    expect(screen.getByText('example.com')).toBeInTheDocument()
    expect(screen.getByText('MODEL_RELEASE')).toBeInTheDocument()
    expect(screen.getByText(/GPT-5 released/)).toBeInTheDocument()
  })

  it('shows lifecycle dot color for active state', () => {
    const { container } = render(<CitationList citations={[CITATION]} />)
    const dot = container.querySelector('.lifecycle-dot')
    expect(dot).toHaveClass('bg-green-500')
  })

  it('renders evidence excerpts in the expanded panel', async () => {
    render(<CitationList citations={[CITATION]} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.getByText('Evidence')).toBeInTheDocument()
    expect(screen.getByText(/supporting excerpt/)).toBeInTheDocument()
  })

  it('omits the Evidence subsection when there is no evidence', async () => {
    render(<CitationList citations={[{ ...CITATION, evidence: [] }]} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.queryByText('Evidence')).not.toBeInTheDocument()
  })
})

describe('MessageList', () => {
  it('renders empty state when no messages', () => {
    render(<MessageList messages={[]} sending={false} />)
    expect(screen.getByText(/ask a question/i)).toBeInTheDocument()
  })

  it('renders messages in order', () => {
    render(<MessageList messages={[USER_MSG, ASSISTANT_MSG]} sending={false} />)
    expect(screen.getByText('What changed?')).toBeInTheDocument()
    expect(screen.getByText('Here is the answer.')).toBeInTheDocument()
  })

  it('shows thinking indicator while sending', () => {
    render(<MessageList messages={[USER_MSG]} sending={true} />)
    expect(screen.getByText(/thinking/i)).toBeInTheDocument()
  })
})

describe('Composer', () => {
  it('renders textarea and submit button', () => {
    render(<Composer disabled={false} sending={false} archived={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('textbox', { name: /message/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^send message$/i })).toBeInTheDocument()
  })

  it('calls onSubmit with trimmed text and clears input', async () => {
    const onSubmit = vi.fn()
    render(<Composer disabled={false} sending={false} archived={false} onSubmit={onSubmit} />)
    const input = screen.getByRole('textbox', { name: /message/i })
    await userEvent.type(input, '  Hello world  ')
    await userEvent.click(screen.getByRole('button', { name: /^send message$/i }))
    expect(onSubmit).toHaveBeenCalledWith('Hello world')
    expect(input).toHaveValue('')
  })

  it('shows archived message when session is archived', () => {
    render(<Composer disabled={false} sending={false} archived={true} onSubmit={vi.fn()} />)
    expect(screen.getByText(/archived/i)).toBeInTheDocument()
  })

  it('disables submit button while sending', () => {
    render(<Composer disabled={false} sending={true} archived={false} onSubmit={vi.fn()} />)
    expect(screen.getByRole('button', { name: /sending/i })).toBeDisabled()
  })

  it('is announced as loading during send', () => {
    render(<Composer disabled={false} sending={true} archived={false} onSubmit={vi.fn()} />)
    expect(screen.getByText(/sending/i)).toBeInTheDocument()
  })
})
