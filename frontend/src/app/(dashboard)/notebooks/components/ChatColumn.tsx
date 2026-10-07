'use client'

import { useEffect, useMemo } from 'react'
import { useNotebookChat } from '@/lib/hooks/use-notebook-chat'
import { useNotes } from '@/lib/hooks/use-notes'
import { useNotebook, useUpdateNotebook } from '@/lib/hooks/use-notebooks'
import { ChatPanel } from '@/components/sources/ChatPanel'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { AlertCircle } from 'lucide-react'
import { ContextSelections } from '../[id]/page'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SourceListResponse } from '@/lib/types/api'
import type { NotebookOverview } from '@/lib/api/explore'
import { useWorkspaceStore } from '@/lib/stores/workspace-store'

interface ChatColumnProps {
  notebookId: string
  contextSelections: ContextSelections
  sources: SourceListResponse[]
  sourcesLoading: boolean
  overview?: NotebookOverview
}

export function ChatColumn({ notebookId, contextSelections, sources, sourcesLoading, overview }: ChatColumnProps) {
  const { t } = useTranslation()

  // Fetch notes for this notebook
  const { data: notes = [], isLoading: notesLoading } = useNotes(notebookId)

  const { data: notebook } = useNotebook(notebookId)
  const updateNotebook = useUpdateNotebook()
  const openEvidence = useWorkspaceStore((s) => s.openEvidence)
  const queuedQuestion = useWorkspaceStore((s) => s.queuedQuestion)
  const clearQueuedQuestion = useWorkspaceStore((s) => s.clearQueuedQuestion)

  // Initialize notebook chat hook
  const chat = useNotebookChat({
    notebookId,
    sources,
    notes,
    contextSelections
  })

  // A question asked from outside the composer (concept panel, starters)
  const { sendMessage, isSending } = chat
  useEffect(() => {
    if (queuedQuestion && !isSending) {
      clearQueuedQuestion()
      void sendMessage(queuedQuestion.text)
    }
  }, [queuedQuestion, isSending, sendMessage, clearQueuedQuestion])

  // Citation titles: "source:abc" -> document title, "note:xyz" -> note title
  const referenceTitles = useMemo(() => {
    const titles: Record<string, string> = {}
    for (const source of sources) titles[source.id] = source.title || t('sources.untitledSource')
    for (const note of notes) if (note.title) titles[note.id] = note.title
    return titles
  }, [sources, notes, t])

  // Calculate context stats for indicator
  const contextStats = useMemo(() => {
    let sourcesInsights = 0
    let sourcesFull = 0
    let notesCount = 0

    // Count sources by mode
    sources.forEach(source => {
      const mode = contextSelections.sources[source.id]
      if (mode === 'insights') {
        sourcesInsights++
      } else if (mode === 'full') {
        sourcesFull++
      }
    })

    // Count notes that are included (not 'off')
    notes.forEach(note => {
      const mode = contextSelections.notes[note.id]
      if (mode === 'full') {
        notesCount++
      }
    })

    // No token count: the agent searches the selection instead of pasting it.
    return {
      sourcesInsights,
      sourcesFull,
      notesCount
    }
  }, [sources, notes, contextSelections])

  // Show loading state while sources/notes are being fetched
  if (sourcesLoading || notesLoading) {
    return (
      <div className="flex h-full flex-1 items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  // Show error state if data fetch failed (unlikely but good to handle)
  if (!sources && !notes) {
    return (
      <div className="flex h-full flex-1 items-center justify-center">
        <div className="text-center text-muted-foreground">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p className="text-sm">{t('chat.unableToLoadChat')}</p>
          <p className="text-xs mt-2">{t('common.refreshPage') || 'Please try refreshing the page'}</p>
        </div>
      </div>
    )
  }

  return (
    <ChatPanel
      title={t('chat.chatWithNotebook')}
      contextType="notebook"
      messages={chat.messages}
      isStreaming={chat.isSending}
      contextIndicators={null}
      onSendMessage={(message, modelOverride, images) => chat.sendMessage(message, modelOverride, images)}
      allowImages
      modelOverride={chat.currentSession?.model_override ?? chat.pendingModelOverride ?? undefined}
      onModelChange={(model) => chat.setModelOverride(model ?? null)}
      sessions={chat.sessions}
      currentSessionId={chat.currentSessionId}
      onCreateSession={(title) => chat.createSession(title)}
      onSelectSession={chat.switchSession}
      onUpdateSession={(sessionId, title) => chat.updateSession(sessionId, { title })}
      onDeleteSession={chat.deleteSession}
      loadingSessions={chat.loadingSessions}
      notebookContextStats={contextStats}
      notebookId={notebookId}
      notebookName={notebook?.name}
      overview={overview}
      referenceTitles={referenceTitles}
      onOpenPages={(target) => openEvidence({ kind: 'pages', ...target })}
      onNewChat={chat.startNewChat}
      agentActivity={chat.activity}
      effort={chat.effort}
      onEffortChange={chat.setEffort}
      grounding={notebook?.grounding ?? 'strict'}
      onGroundingChange={(grounding) => updateNotebook.mutate({ id: notebookId, data: { grounding } })}
    />
  )
}
