# Frontend Rules (frontend/)

Normative rules for working on the Next.js frontend. Architecture and flow walkthroughs live in [docs/7-DEVELOPMENT/frontend.md](../docs/7-DEVELOPMENT/frontend.md) — this file is only what you must know before changing code. Project-wide rules are in the root [AGENTS.md](../AGENTS.md).

## Commands (run inside `frontend/`)

- Dev server: `npm run dev` (port 3000; API must be up at 5055 first). Against a remote install: `INTERNAL_API_URL=http://<host>:3000 API_URL=relative npx next dev -p 3100`
- Add a dependency with npm 10 (`npx -y npm@10.9.2 install <pkg>`): the deploy host's `npm ci` rejects lockfiles written by npm 11
- Lint: `npm run lint` (`eslint src/`)
- Tests: `npm run test` (`vitest run`) · coverage: `npm run test:coverage`
- Build: `npm run build`

## Hard rules

- **i18n is mandatory**: every UI string goes through `t('section.key')` and the key must exist in **all locales** under `src/lib/locales/` (currently 14; en-US is the reference). Missing keys fall back to en-US silently — keep locales in sync. The unused-key test (same file) fails on keys no source file references **literally**, so never build keys from templates (``t(`x.${k}`)``); map to literal `t('x.a')` calls instead, and delete keys from all locales when their last use goes. Each non-en-US locale ends with `satisfies TranslationShape` (type derived from en-US), so a missing/extra key fails `tsc`; the parity test (`src/lib/locales/index.test.ts`) checks the same at runtime. Adding a whole language also touches `src/lib/utils/date-locale.ts`; `src/components/common/LanguageToggle.tsx` renders the `languages` list, so it needs no edit (see the [i18n playbook](../docs/7-DEVELOPMENT/change-playbooks.md#adding-a-new-language)).
- **Styling goes through design tokens** ([ADR-011](../docs/7-DEVELOPMENT/decisions/ADR-011-design-token-system.md)): use semantic utilities (`text-destructive`, `bg-warn-tint`, `text-teal`, `text-type-video`, …) defined in `src/app/globals.css` — never raw Tailwind palette classes (`text-red-600`, `bg-amber-50`) and never hand-written `dark:` color twins (tokens re-resolve per theme). The laws ([ADR-018](../docs/7-DEVELOPMENT/decisions/ADR-018-research-workspace-ui.md)): ink acts (primary buttons), iris (`text-iris`, legacy `teal`) is the agent's voice, amber (`amber`, legacy `gold`) is evidence, emerald (`fern`) confirms, red only destroys. `/dev/design` (dev-only route) renders every token and primitive in both themes — it's the visual reference, and screen-level PRs must not change it.
- **The notebook page is a workspace** ([ADR-018](../docs/7-DEVELOPMENT/decisions/ADR-018-research-workspace-ui.md)): library (Sources · Notes · Concepts) · Chat or Graph · evidence panel. Cross-pane state (library open/tab, Chat/Graph view, evidence target, questions queued from outside the composer via `ask()`) lives in `useWorkspaceStore` (`lib/stores/workspace-store.ts`); only layout preferences persist. Open evidence with `openEvidence({kind: 'pages' | 'concept', …})` rather than dialogs in the notebook; other screens (Ask, source chat) use `PagePreviewDialog`.
- **Reuse `src/components/brain/`** instead of re-implementing: `PageThumb` / `usePageImage` (page images need the auth header, so they're fetched as blobs and cached for the session; thumbnails use `format=jpeg`), `AnswerContent` and `Citations` (citation chips, cited-page strip, `collectReferences` numbering), `ResearchTimeline` (`LiveResearch`, `ResearchTrace`), `EvidencePanel`, `ConceptsPanel`, `ChatWelcome`, `SourceStructureView`, `ConceptGraph` (2D canvas, d3-force), `ConceptGraph3D` and `IngestionProgress` (`IngestionStrip`, `IngestionTimeline`, `stageLabel`). Read-only ingestion data comes from `lib/api/explore.ts` / `lib/hooks/use-explore.ts`; ingestion progress from `lib/hooks/use-ingestion.ts` (polls only while unfinished; don't add another poller for the same data).
- **Research-trace text never shows record ids**: render a step with `describeStep(tool, args, t, step.subject)` and result lines through `withoutRecordIds` (`components/sources/AgentActivity.tsx`); the server's `subject` is readable, and the fallback replaces any `source:…` left over.
- **Heavy visual libraries load on demand**: three.js / 3d-force-graph only through `next/dynamic` (`ConceptGraphView`), never imported at module level by a page.
- All requests go through `apiClient` (`src/lib/api/client.ts`); never create a second axios instance. Auth token is auto-added from localStorage key `auth-storage`.
- Data fetching uses TanStack Query hooks in `src/lib/hooks/` with `QUERY_KEYS`; mutations invalidate caches and show toasts (sonner). Follow the existing hook shape.
- FormData requests: nested objects/arrays must be `JSON.stringify`-ed before appending; the interceptor strips Content-Type so the browser sets the multipart boundary — don't re-add it.
- No automatic request retry — handle failures in the consuming code (podcast retry is an explicit endpoint/hook, not a client retry).

## Gotchas

- Zustand stores with `persist`: check `hasHydrated` before rendering persisted state (SSR hydration mismatch), and keep each store's `name` key unique (localStorage collision).
- `NEXT_PUBLIC_API_TIMEOUT_MS`: default 600000 (10 min) for slow LLM calls; `0` disables the timeout.
- SSE (`useAsk`): incomplete lines stay in the buffer between reads; incomplete JSON is silently skipped — don't "simplify" the buffer handling.
- `useSourceStatus` polls every 2s while status is `running`/`queued`/`new`.
- Cache invalidation is deliberately broad (e.g. `['sources']` hits all source queries) — a simplicity/perf trade-off, be precise only when it matters.
- Dark mode requires the `dark` class on the document root, not just `prefers-color-scheme`. It's hand-rolled: the zustand `theme-store` (persisted as `theme-storage`) sets the class via `ThemeProvider` — no next-themes.
- Dialogs don't auto-reset form state (parent clears it) and auto-focus the first input (layout shift risk with conditional inputs). Fixed overlays use `z-50`.
- Provider nesting order in `app/layout.tsx` matters: ErrorBoundary → ThemeProvider → QueryProvider → I18nProvider → ConnectionGuard → Toaster. ErrorBoundary is a class component and uses the raw `enUS` locale object (no hooks).
- `i18n` runs with `useSuspense: false` (no SSR for translations).
- Canvas and WebGL can't use CSS classes: read colours from the CSS custom properties (and fonts from `document.body`), and re-read them when the root `class` changes (theme switch) with a `MutationObserver`, as the graph components do. Document colours in the graph are evenly spaced hues (`documentHues`) so neighbouring documents never match.
- CSS2D labels in the 3D graph: `CSS2DRenderer` leaves an element in the DOM when its object is replaced, so the component removes old label elements itself on every refresh.
- `useAuth().isLoading` stays true until the store knows whether a password is required (unless a saved session says signed in); without that, deep links in a fresh browser bounced through `/login`.
- The runtime `/config` returns `apiUrl: ''` for `API_URL=relative`: the browser then calls its own origin and Next proxies `/api` (needed when the API port isn't reachable from browsers).
- The chat composer sends on **Enter** (Shift+Enter = new line, Cmd/Ctrl+Enter also sends) and uses container queries (`@container`, `@md:`) because its width depends on which panes are open, not on the viewport.
- Components that use `useNotebooks` (e.g. the sidebar's notebook list) need it mocked in tests that render without a `QueryClientProvider`.

## Deep dives

[frontend architecture](../docs/7-DEVELOPMENT/frontend.md) · [credentials system](../docs/7-DEVELOPMENT/credentials.md) · [change playbooks](../docs/7-DEVELOPMENT/change-playbooks.md) (i18n / frontend-only changes) · [code standards](../docs/7-DEVELOPMENT/code-standards.md)

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
