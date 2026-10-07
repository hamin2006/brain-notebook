import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** What the evidence panel shows: cited pages of a source, or a concept. */
export type EvidenceTarget =
  | { kind: 'pages'; sourceId: string; start: number; end: number }
  | { kind: 'concept'; conceptId: string; name?: string }

export type LibraryTab = 'sources' | 'notes' | 'concepts'
export type WorkspaceView = 'chat' | 'graph'

interface WorkspaceState {
  libraryOpen: boolean
  libraryTab: LibraryTab
  view: WorkspaceView
  evidence: EvidenceTarget | null
  // A question queued from outside the composer (starters, concept panel)
  queuedQuestion: { text: string; nonce: number } | null
  toggleLibrary: () => void
  setLibraryTab: (tab: LibraryTab) => void
  setView: (view: WorkspaceView) => void
  openEvidence: (target: EvidenceTarget) => void
  closeEvidence: () => void
  ask: (text: string) => void
  clearQueuedQuestion: () => void
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      libraryOpen: true,
      libraryTab: 'sources',
      view: 'chat',
      evidence: null,
      queuedQuestion: null,
      toggleLibrary: () => set((state) => ({ libraryOpen: !state.libraryOpen })),
      setLibraryTab: (libraryTab) => set({ libraryTab, libraryOpen: true }),
      setView: (view) => set({ view }),
      openEvidence: (evidence) => set({ evidence }),
      closeEvidence: () => set({ evidence: null }),
      ask: (text) => set({ queuedQuestion: { text, nonce: Date.now() }, view: 'chat' }),
      clearQueuedQuestion: () => set({ queuedQuestion: null }),
    }),
    {
      name: 'brain-workspace',
      // Only layout preferences survive a reload
      partialize: (state) => ({ libraryOpen: state.libraryOpen, libraryTab: state.libraryTab }),
    }
  )
)
