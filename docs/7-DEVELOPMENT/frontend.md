# Frontend Architecture

How the Next.js app is layered and how data flows through it. Normative rules (commands, i18n, gotchas) live in [`frontend/AGENTS.md`](../../frontend/AGENTS.md); this page is the mental model.

## Layers

```
Pages (src/app/, App Router) → Feature components (src/components/) → Hooks (src/lib/hooks/)
                                                                          ↓
                              Stores (src/lib/stores/) → API modules (src/lib/api/) → Backend
```

- **Pages** — route endpoints. Router groups `(auth)` / `(dashboard)` organize routes without affecting URLs. Pages call hooks and render components.
- **Components** — feature folders (`source/`, `notebooks/`, `podcasts/`, …) own page-level state (loading, error); `components/ui/` are stateless Radix UI wrappers styled with Tailwind + CVA.
- **Hooks** (`src/lib/hooks/`) — TanStack Query wrappers. Query hooks return `{ data, isLoading, error, refetch }`; mutation hooks invalidate caches and toast. Complex hooks (`useNotebookChat`, `useAsk`) add session management, context building, SSE streaming.
- **Stores** (`src/lib/stores/`) — Zustand for auth and modal state; `persist` middleware syncs to localStorage (auth token under `auth-storage`).
- **API modules** (`src/lib/api/`) — namespaced typed clients (`sourcesApi.list()`, …) over a single axios instance with auth/FormData/401 interceptors.

Provider tree in `app/layout.tsx` (outermost → innermost): ErrorBoundary → ThemeProvider → QueryProvider → I18nProvider → ConnectionGuard → Toaster.

## The notebook workspace

`notebooks/[id]/page.tsx` lays out the workspace ([ADR-018](decisions/ADR-018-research-workspace-ui.md)):
`NotebookHeader` (name, description, stats from `useNotebookOverview`, the grounding switch), a library pane with
`SourcesColumn` / `NotesColumn` / `ConceptsPanel` tabs, `ChatColumn` in the middle and `EvidencePanel` on the right.
Shared state (library open and tab, the Chat/Graph view, the evidence target, questions queued from outside the composer) is the
`useWorkspaceStore` zustand store (`lib/stores/workspace-store.ts`; only layout preferences persist). Phones get tabs
and a full-screen evidence overlay.

Reusable research UI lives in `components/brain/`:

| Component | What it does |
|---|---|
| `PageThumb` | A rendered page via `usePageImage` (auth fetch → object URL, cached for the session; `lazy` waits until visible) |
| `Citations` | `CitationChip` (numbered chip, hover preview of the page), `CitedSources` (thumbnails under an answer), href/locator helpers |
| `Answer` | `AnswerContent`: markdown with citation chips plus cited sources; fetches titles it isn't given (Ask) |
| `ResearchTimeline` | `LiveResearch` (live steps, elapsed time) and `ResearchTrace` (folded trace of a saved answer), `traceStats` |
| `ChatWelcome` | Empty conversation: notebook stats, starter questions from top concepts, key concepts |
| `EvidencePanel`, `ConceptsPanel` | The evidence pane (pages or concept) and the library's concept list |
| `ConceptGraphView` | The Graph view's Map / 3D switch; `ConceptGraph3D` (3d-force-graph + three.js, CSS2D labels, bloom in dark) is loaded with `next/dynamic` only when 3D is opened |
| `ConceptGraph` | `ConceptGraph2D`, the map: d3-force layout on a canvas (columns per document, relation and co-occurrence links, hover focus, search, zoom, legend filter) from `GET /notebooks/{id}/graph` |
| `SourceStructure` | The source view's Structure tab |
| `AskBar` | The home page's ask-everywhere box (opens `/search?mode=ask&q=…`) |

Data for these comes from `lib/api/explore.ts` / `lib/hooks/use-explore.ts` (overview, concept, structure, page images).

## Flow walkthrough: notebook chat (research agent)

1. `ChatColumn` reads the notebook, builds citation titles from the sources and notes, sends questions queued in the
   workspace store, and renders `ChatPanel` with `allowImages`, the overview and `onOpenPages` (→ evidence panel).
2. `useNotebookChat()` (`lib/hooks/use-notebook-chat.ts`) manages sessions (including `startNewChat`), messages,
   `effort` and the live `activity`. `scope()` turns the selections into `source_ids` / `note_ids` (anything not
   "not included").
3. On send it adds the user message optimistically (with attached image previews), then calls
   `chatApi.streamMessage()` (`POST /api/chat/execute/stream`, proxied by `app/api/chat/execute/stream/route.ts`) and
   reads the SSE stream. `applyAgentEvent()` (pure, tested) folds `step` / `step_result` / `text_delta` into
   `{steps, text}`, shown by `LiveResearch` and the streaming answer. `ai_message` replaces the live view with the
   saved answer (with `trace`), rendered by `ResearchTrace` and `AnswerContent`.
4. `ChatComposer` (in `ChatPanel.tsx`) holds image attachments (`ImageAttachments.tsx`: paste, pick or drop, scaled
   to ≤1600 px JPEG data URLs, max 4), the effort toggle, the scope label and the model. Enter sends.
5. References: `lib/utils/source-references.tsx` parses addresses with locators (`[source:abc#p94]`) and numbers each
   location (`collectReferences` gives the same numbering for the thumbnails). A page citation calls `onOpenPages`
   (notebook) or opens `PagePreviewDialog` (Ask, source chat).

Settings → Research agent is `app/(dashboard)/settings/components/AgentSettingsCard.tsx` with hooks in
`lib/hooks/use-agent.ts`. App-wide links to the repository come from `lib/project.ts`.

## Flow walkthrough: file upload

1. `SourceDialog` collects the file; `useFileUpload` builds FormData — nested JSON fields are stringified.
2. The client interceptor deletes the Content-Type header so the browser sets the multipart boundary.
3. On success, `queryClient.invalidateQueries(['sources'])` refetches lists; `useSourceStatus` polls every 2s while the source is processing.

## Caching strategy

Query keys are hierarchical (`QUERY_KEYS.sources(notebookId)`), but invalidation is deliberately **broad** (`['sources']` catches everything) — a precision/simplicity trade-off. Frequently changing data uses `refetchOnWindowFocus: true`.

## Auth

The token is validated by an actual API call (`/notebooks`), not JWT decoding, with a 30-second cache in the auth store. The response interceptor clears auth and redirects to `/login` on 401. Logout is client-side only.

## Error handling

`getApiErrorMessage()` (`lib/utils/error-handler.ts`) tries an i18n mapping first, then falls back to the backend's descriptive message — which the backend error-classification system already makes user-friendly (see [architecture.md](architecture.md#models)). Mutations surface errors as toasts; an app-level ErrorBoundary catches render errors.
