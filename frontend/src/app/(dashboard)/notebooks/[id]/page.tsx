'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { NotebookHeader } from '../components/NotebookHeader'
import { SourcesColumn } from '../components/SourcesColumn'
import { NotesColumn } from '../components/NotesColumn'
import { ChatColumn } from '../components/ChatColumn'
import { useNotebook } from '@/lib/hooks/use-notebooks'
import { useNotebookSources } from '@/lib/hooks/use-sources'
import { useNotes } from '@/lib/hooks/use-notes'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useWorkspaceStore, type LibraryTab } from '@/lib/stores/workspace-store'
import { useNotebookOverview } from '@/lib/hooks/use-explore'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { ConceptsPanel } from '@/components/brain/ConceptsPanel'
import { EvidencePanel } from '@/components/brain/EvidencePanel'
import { ConceptGraph } from '@/components/brain/ConceptGraph'
import { useIsDesktop, useMediaQuery } from '@/lib/hooks/use-media-query'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import { FileText, StickyNote, Share2 } from 'lucide-react'
import {
  applyBulkSourceContext,
  applyBulkNoteContext,
  computeSourceSelections,
  computeNoteSelections,
  type SourceContextDefault,
  type SourceBulkAction,
  type NoteContextDefault,
} from '@/lib/utils/source-context'

// Re-exported from the shared types module for backward compatibility; several
// components historically import these from this route file.
import type { ContextMode, ContextSelections, NoteContextMode } from '@/lib/types/notebook-context'
export type { ContextMode, ContextSelections, NoteContextMode }

export default function NotebookPage() {
  const { t } = useTranslation()
  const params = useParams()

  // Ensure the notebook ID is properly decoded from URL
  const notebookId = params?.id ? decodeURIComponent(params.id as string) : ''

  const { data: notebook, isLoading: notebookLoading } = useNotebook(notebookId)
  const {
    sources,
    isLoading: sourcesLoading,
    refetch: refetchSources,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useNotebookSources(notebookId)
  const { data: notes, isLoading: notesLoading } = useNotes(notebookId)

  const { data: overview } = useNotebookOverview(notebookId)
  const { openModal } = useModalManager()
  const libraryOpen = useWorkspaceStore((s) => s.libraryOpen)
  const libraryTab = useWorkspaceStore((s) => s.libraryTab)
  const setLibraryTab = useWorkspaceStore((s) => s.setLibraryTab)
  const evidence = useWorkspaceStore((s) => s.evidence)
  const view = useWorkspaceStore((s) => s.view)
  const closeEvidence = useWorkspaceStore((s) => s.closeEvidence)

  // The evidence panel belongs to one notebook; close it when switching.
  useEffect(() => {
    closeEvidence()
  }, [notebookId, closeEvidence])

  const sourceTitles = useMemo(
    () => Object.fromEntries((sources ?? []).map((s) => [s.id, s.title || t('sources.untitledSource')])),
    [sources, t]
  )
  const openSource = useCallback(
    (sourceId: string) => openModal('source', sourceId.replace(/^source:/, '')),
    [openModal]
  )

  // Detect desktop to avoid double-mounting ChatColumn
  const isDesktop = useIsDesktop()
  // Room for library, conversation and evidence side by side
  const isWide = useMediaQuery('(min-width: 1600px)')

  // Mobile tab state (Sources, Notes, or Chat)
  const [mobileActiveTab, setMobileActiveTab] = useState<'sources' | 'notes' | 'chat' | 'concepts' | 'graph'>('chat')

  // Context selection state
  const [contextSelections, setContextSelections] = useState<ContextSelections>({
    sources: {},
    notes: {}
  })

  // The default context mode applied to sources as they load. A bulk
  // include/exclude updates this so sources loaded later via pagination follow
  // the same intent instead of reverting to "included" (#223/#915).
  const [sourceContextDefault, setSourceContextDefault] = useState<SourceContextDefault>('include')

  // Same idea for notes loaded later (notes are binary: included/off).
  const [noteContextDefault, setNoteContextDefault] = useState<NoteContextDefault>('include')

  // Initialize and update selections when sources load or change
  useEffect(() => {
    if (sources && sources.length > 0) {
      setContextSelections(prev => ({
        ...prev,
        sources: computeSourceSelections(prev.sources, sources, sourceContextDefault),
      }))
    }
  }, [sources, sourceContextDefault])

  useEffect(() => {
    if (notes && notes.length > 0) {
      setContextSelections(prev => ({
        ...prev,
        notes: computeNoteSelections(prev.notes, notes, noteContextDefault),
      }))
    }
  }, [notes, noteContextDefault])

  const handleSourceContextModeChange = (sourceId: string, mode: ContextMode) => {
    setContextSelections(prev => ({
      ...prev,
      sources: {
        ...prev.sources,
        [sourceId]: mode
      }
    }))
  }

  const handleNoteContextModeChange = (noteId: string, mode: NoteContextMode) => {
    setContextSelections(prev => ({
      ...prev,
      notes: {
        ...prev.notes,
        [noteId]: mode
      }
    }))
  }

  // Bulk-apply a context action (insights-only / full / exclude) to every
  // source at once (#223). Also records the action as the default for sources
  // loaded later (#915).
  const handleBulkSourceContext = (action: SourceBulkAction) => {
    setSourceContextDefault(action)
    setContextSelections(prev => ({
      ...prev,
      sources: applyBulkSourceContext(prev.sources, sources ?? [], action),
    }))
  }

  // Bulk include/exclude every note from the chat context at once (#223).
  const handleBulkNoteContext = (action: NoteContextDefault) => {
    setNoteContextDefault(action)
    setContextSelections(prev => ({
      ...prev,
      notes: applyBulkNoteContext(prev.notes, notes ?? [], action),
    }))
  }

  if (notebookLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!notebook) {
    return (
      <AppShell>
        <div className="p-6">
          <h1 className="text-2xl font-bold mb-4">{t('notebooks.notFound')}</h1>
          <p className="text-muted-foreground">{t('notebooks.notFoundDesc')}</p>
        </div>
      </AppShell>
    )
  }

  const sourcesPanel = (
    <SourcesColumn
      sources={sources}
      isLoading={sourcesLoading}
      notebookId={notebookId}
      notebookName={notebook?.name}
      onRefresh={refetchSources}
      contextSelections={contextSelections.sources}
      onContextModeChange={handleSourceContextModeChange}
      onBulkContextModeChange={handleBulkSourceContext}
      hasNextPage={hasNextPage}
      isFetchingNextPage={isFetchingNextPage}
      fetchNextPage={fetchNextPage}
    />
  )
  const notesPanel = (
    <NotesColumn
      notes={notes}
      isLoading={notesLoading}
      notebookId={notebookId}
      contextSelections={contextSelections.notes}
      onContextModeChange={handleNoteContextModeChange}
      onBulkContextModeChange={handleBulkNoteContext}
    />
  )
  const chat = (
    <ChatColumn
      notebookId={notebookId}
      contextSelections={contextSelections}
      sources={sources}
      sourcesLoading={sourcesLoading}
      overview={overview}
    />
  )
  const libraryTabs: { value: LibraryTab; label: string; icon: typeof FileText; count?: number }[] = [
    { value: 'sources', label: t('navigation.sources'), icon: FileText, count: notebook.source_count },
    { value: 'notes', label: t('common.notes'), icon: StickyNote, count: notes?.length },
    { value: 'concepts', label: t('brain.concepts'), icon: Share2, count: overview?.concepts },
  ]

  return (
    <AppShell>
      <div className="flex min-h-0 flex-1 flex-col">
        <NotebookHeader notebook={notebook} overview={overview} />

        {/* Mobile: one panel at a time - only render on mobile to avoid double-mounting */}
        {!isDesktop && (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex gap-1 border-b px-3 py-2">
              {(['chat', 'graph', 'sources', 'notes', 'concepts'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setMobileActiveTab(tab)}
                  className={cn(
                    'flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors',
                    mobileActiveTab === tab ? 'bg-card text-foreground shadow-soft ring-1 ring-inset ring-border' : 'text-muted-foreground'
                  )}
                >
                  {tab === 'chat' ? t('common.chat') : tab === 'graph' ? t('brain.graph') : tab === 'concepts' ? t('brain.concepts') : tab === 'sources' ? t('navigation.sources') : t('common.notes')}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-hidden pt-3">
              {mobileActiveTab === 'sources' && sourcesPanel}
              {mobileActiveTab === 'notes' && notesPanel}
              {mobileActiveTab === 'concepts' && <ConceptsPanel notebookId={notebookId} />}
              {mobileActiveTab === 'chat' && chat}
              {mobileActiveTab === 'graph' && <ConceptGraph notebookId={notebookId} />}
            </div>
            {evidence && (
              <div className="fixed inset-0 z-40 flex flex-col bg-background">
                <EvidencePanel notebookId={notebookId} sourceTitles={sourceTitles} onOpenSource={openSource} />
              </div>
            )}
          </div>
        )}

        {/* Desktop: library | conversation | evidence */}
        {isDesktop && (
          <div className="flex min-h-0 flex-1">
            {libraryOpen && (!evidence || isWide) && (
              <aside className="flex w-[300px] shrink-0 flex-col border-r bg-sidebar/60 xl:w-[320px]">
                <div className="flex gap-1 p-3">
                  {libraryTabs.map((tab) => (
                    <button
                      key={tab.value}
                      type="button"
                      onClick={() => setLibraryTab(tab.value)}
                      className={cn(
                        'flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors',
                        libraryTab === tab.value
                          ? 'bg-card text-foreground shadow-soft ring-1 ring-inset ring-border'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                    >
                      <tab.icon className="h-3.5 w-3.5" />
                      {tab.label}
                      {tab.count !== undefined && (
                        <span className="font-mono text-[10px] text-muted-foreground">{tab.count}</span>
                      )}
                    </button>
                  ))}
                </div>
                <div className="min-h-0 flex-1">
                  {libraryTab === 'sources' && sourcesPanel}
                  {libraryTab === 'notes' && notesPanel}
                  {libraryTab === 'concepts' && <ConceptsPanel notebookId={notebookId} />}
                </div>
              </aside>
            )}

            <main className="flex min-w-0 flex-1 flex-col">
              {view === 'graph' ? <ConceptGraph notebookId={notebookId} /> : chat}
            </main>

            {evidence && (
              <aside className="flex w-[400px] shrink-0 flex-col border-l bg-sidebar/60 2xl:w-[460px]">
                <EvidencePanel notebookId={notebookId} sourceTitles={sourceTitles} onOpenSource={openSource} />
              </aside>
            )}
          </div>
        )}
      </div>
    </AppShell>
  )
}
