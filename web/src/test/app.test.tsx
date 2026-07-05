import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('../hooks/useSessions', () => ({
  useSessions: () => ({
    sessions: [],
    loading: false,
    activeId: null,
    createSession: vi.fn(),
    selectSession: vi.fn(),
    renameSession: vi.fn(),
    archiveSession: vi.fn(),
  }),
}))

vi.mock('../hooks/useChatSession', () => ({
  useChatSession: () => ({
    detail: null,
    loading: false,
    sending: false,
    error: null,
    sendMessage: vi.fn(),
    clearError: vi.fn(),
  }),
}))

vi.mock('../components/Dashboard', () => ({
  Dashboard: () => <div data-testid="dashboard-panel">Dashboard content</div>,
}))

describe('App tab shell', () => {
  it('defaults to the Chat tab', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: 'Chat' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('+ New chat')).toBeInTheDocument()
    expect(screen.getByText(/select a session or start a new chat/i)).toBeInTheDocument()
    expect(screen.queryByTestId('dashboard-panel')).not.toBeInTheDocument()
  })

  it('switches to Dashboard when its tab is clicked', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Dashboard' }))
    expect(screen.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('dashboard-panel')).toBeInTheDocument()
    expect(screen.queryByText('+ New chat')).not.toBeInTheDocument()
  })

  it('switches to How it works placeholder', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'How it works' }))
    expect(screen.getByRole('button', { name: 'How it works' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText(/ask a question in the chat tab first/i)).toBeInTheDocument()
    expect(screen.queryByText('+ New chat')).not.toBeInTheDocument()
  })

  it('can switch back to Chat from another tab', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Dashboard' }))
    await userEvent.click(screen.getByRole('button', { name: 'Chat' }))
    expect(screen.getByRole('button', { name: 'Chat' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('+ New chat')).toBeInTheDocument()
  })
})
