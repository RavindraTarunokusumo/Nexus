# Chat Web UI Design

## Goal

Build a simple React and Tailwind CSS web UI for Nexus chat sessions. Users should be able to create a session, ask grounded questions, continue a conversation, review prior sessions, and inspect citations returned by the backend.

This spec pairs with [Chat Session Memory Design](2026-05-24-chat-session-memory-design.md). The backend memory spec defines the API and persistence contracts this UI consumes.

## Current State

Nexus currently has a FastAPI backend and a Typer CLI. It does not have a frontend project. The existing chat feature is single-turn through `POST /chat/answer` and `nexus chat`.

The web UI should target the new session endpoints from the paired memory spec, not the single-turn endpoint.

## Scope

Included:

- A new React app using Tailwind CSS.
- Session list sidebar.
- Chat transcript panel.
- Message composer with submit/loading/error states.
- Citation display for assistant messages.
- Session rename and archive controls.
- Empty states for no sessions and new sessions.

Not included:

- Authentication.
- Streaming token output.
- Rich markdown editing.
- Source ingestion, claim review, run inspection, or admin dashboards.
- Complex settings pages.
- Mobile app packaging.

## Frontend Stack

Create a new `web/` workspace using:

- React
- TypeScript
- Vite
- Tailwind CSS
- Vitest and React Testing Library for component/unit tests
- Playwright or the available browser verification tooling for an end-to-end smoke check

The app should be served separately from FastAPI during development and call the FastAPI API base URL from configuration.

## Information Architecture

Use a two-pane application layout:

```text
-------------------------------------------------
| Sessions sidebar | Chat header                |
|                  |----------------------------|
| New chat         | Message transcript         |
| Session list     |                            |
|                  | Citation rows in messages |
|                  |----------------------------|
|                  | Composer                  |
-------------------------------------------------
```

On small screens, the session list can stack above the chat panel or collapse behind a simple button. The first implementation only needs to be usable and readable on desktop and mobile widths; it does not need advanced animations.

## Screens

### Empty App State

When no active sessions exist:

- Show a left sidebar with a `New chat` button.
- Show an empty chat panel with the composer disabled until a session exists, or create a session automatically when the user submits the first message.

Recommended behavior: allow the user to type immediately in an empty app. On submit, call `POST /chat/sessions`, then call `POST /chat/sessions/{id}/messages`.

### Active Session

The chat panel shows:

- Header with session title.
- Rename button.
- Archive button.
- Ordered transcript.
- Composer pinned to the bottom of the panel.

User messages should be right-aligned or visually distinct. Assistant messages should show answer text and, when present, a citation section below the answer.

### Citation Display

For each assistant message, show citations as compact rows:

- document title, falling back to short document ID
- score rounded to two decimals
- source URL host or full URL if space allows
- span ID short form
- claim count

Clicking a citation can expand inline details in the first version. It does not need to navigate to a document page because that page does not exist in the web UI yet.

### Loading And Error States

While a message is pending:

- Disable the composer submit button.
- Show the user message optimistically only if the backend is expected to persist partial turns. The paired backend spec says partial turns are not persisted on failure, so the first UI should show a local pending bubble and replace it with persisted rows when the response succeeds.
- Show a concise error banner if the request fails.

If the API returns `503`, show a recoverable error and keep the composer content available for retry.

## API Usage

The UI uses only the session API from the paired memory spec.

### Types

```ts
type ChatSessionSummary = {
  id: string
  title: string | null
  status: 'active' | 'archived'
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview: string | null
}

type ChatCitation = {
  document_id: string
  span_id: string
  document_title: string | null
  url: string | null
  score: number
  claim_ids: string[]
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  run_id?: string
  citations?: ChatCitation[]
  retrieved_context_count?: number
  tokens_used?: number
  cost_estimate_usd?: number
}

type ChatSessionDetail = ChatSessionSummary & {
  messages: ChatMessage[]
}
```

### Calls

- On app load: `GET /chat/sessions?status=active&limit=30`
- On session click: `GET /chat/sessions/{session_id}`
- On new chat: `POST /chat/sessions`
- On message submit: `POST /chat/sessions/{session_id}/messages`
- On rename/archive: `PATCH /chat/sessions/{session_id}`

## Component Plan

Place frontend code under `web/src/`.

Suggested file responsibilities:

- `src/main.tsx`: React bootstrap.
- `src/App.tsx`: top-level layout and selected-session state.
- `src/api/client.ts`: typed fetch helpers and API error handling.
- `src/hooks/useSessions.ts`: load, create, rename, archive, and select sessions.
- `src/hooks/useChatSession.ts`: load detail and send messages for one session.
- `src/components/SessionSidebar.tsx`: new chat button and session list.
- `src/components/ChatPanel.tsx`: header, message list, composer.
- `src/components/MessageList.tsx`: transcript rendering.
- `src/components/MessageBubble.tsx`: user/assistant message display.
- `src/components/CitationList.tsx`: citation rows and inline expansion.
- `src/components/Composer.tsx`: textarea and submit button.

Keep components small and data flow predictable. The first version can use React state and custom hooks; it does not need Redux, Zustand, React Query, or routing.

## Visual Design

Keep the interface quiet and functional:

- White or near-white main background.
- Dark neutral text.
- Simple borders between sidebar, header, transcript, and composer.
- One accent color for selected session and primary submit button.
- 8px or smaller border radius on panels and repeated rows.
- No marketing hero, decorative gradients, or large illustrative elements.

Controls should be recognizable:

- `New chat` as a text button.
- Rename and archive as icon buttons if an icon library is added.
- Composer submit as a clear button adjacent to the textarea.

## Configuration

The frontend should read an API base URL from Vite environment configuration:

```text
VITE_API_BASE_URL=http://localhost:8000
```

In development, Vite runs on its own port and sends API requests to FastAPI. CORS must be enabled in FastAPI for the Vite dev origin if it is not already.

## Error Handling

The API client should normalize failures into:

```ts
type ApiError = {
  status: number | null
  message: string
}
```

UI behavior:

- `404` while opening a session: remove it from local list and show a small banner.
- `409` while sending to archived session: reload the session list and disable composer for that session.
- `422`: show validation copy near the composer.
- `503` or network failure: keep the typed message available and show retry guidance.

## Accessibility

Minimum requirements:

- Composer textarea has a visible label or `aria-label`.
- Buttons have accessible names.
- Loading state is announced through button text or an `aria-live` region.
- Keyboard users can create a session, select a session, type, submit, rename, and archive.
- Color is not the only indicator for selected sessions or errors.

## Testing

Add tests before implementation:

- API client builds the expected URLs and surfaces backend errors.
- Empty app submit creates a session and sends the first message.
- Session list renders summaries newest first using backend order.
- Selecting a session loads and renders transcript messages.
- Sending a message shows a pending state and then renders persisted user and assistant rows.
- Assistant citations render title, score, URL, span ID, and claim count.
- Archived sessions disable the composer.
- A browser smoke test opens the app, sends a mocked message, and verifies the transcript is visible.

## Acceptance Criteria

- A user can open the web UI, type a first question, and receive a grounded assistant answer in a persisted session.
- Reloading the page shows the session list and prior transcript from the backend.
- A follow-up question is sent to the same backend session ID.
- Citations from assistant messages are visible without opening developer tools.
- The UI remains simple, responsive, and usable without implementing unrelated Nexus workflows.
