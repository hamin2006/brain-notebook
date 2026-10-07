'use client'

import { useState } from 'react'
import { NoteResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Plus, StickyNote, Bot, User, MoreVertical, Trash2, ListChecks } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { NoteEditorDialog } from './NoteEditorDialog'
import { getDateLocale } from '@/lib/utils/date-locale'
import { formatDistanceToNow } from 'date-fns'
import { ContextToggle } from '@/components/common/ContextToggle'
import type { NoteContextMode } from '../[id]/page'
import type { NoteContextDefault } from '@/lib/utils/source-context'
import { useDeleteNote } from '@/lib/hooks/use-notes'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotesColumnProps {
  notes?: NoteResponse[]
  isLoading: boolean
  notebookId: string
  contextSelections?: Record<string, NoteContextMode>
  onContextModeChange?: (noteId: string, mode: NoteContextMode) => void
  onBulkContextModeChange?: (action: NoteContextDefault) => void
}

export function NotesColumn({
  notes,
  isLoading,
  notebookId,
  contextSelections,
  onContextModeChange,
  onBulkContextModeChange
}: NotesColumnProps) {
  const { t, language } = useTranslation()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingNote, setEditingNote] = useState<NoteResponse | undefined>()
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [noteToDelete, setNoteToDelete] = useState<string | null>(null)

  const deleteNote = useDeleteNote()

  const handleDeleteClick = (noteId: string) => {
    setNoteToDelete(noteId)
    setDeleteDialogOpen(true)
  }

  const handleOpenEditor = (note?: NoteResponse) => {
    setEditingNote(note)
    setEditorOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!noteToDelete) return

    try {
      await deleteNote.mutateAsync(noteToDelete)
      setDeleteDialogOpen(false)
      setNoteToDelete(null)
    } catch (error) {
      console.error('Failed to delete note:', error)
    }
  }

  return (
    <>
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-shrink-0 items-center gap-1.5 px-3 pb-2">
          <Button size="sm" variant="outline" className="h-8 flex-1 justify-start" onClick={() => handleOpenEditor()}>
            <Plus className="h-4 w-4" />
            {t('common.writeNote')}
          </Button>
          {onBulkContextModeChange && notes && notes.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" className="text-muted-foreground" title={t('sources.bulkContext')} aria-label={t('sources.bulkContext')}>
                  <ListChecks className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onBulkContextModeChange('include')}>
                  {t('sources.includeAllInContext')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onBulkContextModeChange('exclude')}>
                  {t('sources.excludeAllFromContext')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : !notes || notes.length === 0 ? (
            <EmptyState
              icon={StickyNote}
              title={t('notebooks.noNotesYet')}
              description={t('sources.createFirstNote')}
            />
          ) : (
            <div className="space-y-2">
              {notes.map((note) => (
                <div
                  key={note.id}
                  className={cn(
                    'group relative cursor-pointer rounded-xl border bg-card p-3 shadow-soft card-hover',
                    contextSelections?.[note.id] === 'off' && 'opacity-55'
                  )}
                  onClick={() => handleOpenEditor(note)}
                >
                  <div className="mb-1.5 flex items-center gap-1.5 pr-14 text-[11px] text-muted-foreground">
                    {note.note_type === 'ai' ? (
                      <Bot className="h-3.5 w-3.5 text-iris" />
                    ) : (
                      <User className="h-3.5 w-3.5" />
                    )}
                    <span>{note.note_type === 'ai' ? t('common.aiGenerated') : t('common.human')}</span>
                    <span aria-hidden>·</span>
                    <span className="truncate">
                      {formatDistanceToNow(new Date(note.updated), {
                        addSuffix: true,
                        locale: getDateLocale(language)
                      })}
                    </span>
                  </div>

                  <div className="absolute right-1.5 top-1.5 flex items-center">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 opacity-0 transition-opacity group-hover:opacity-100 data-[state=open]:opacity-100"
                          onClick={(e) => e.stopPropagation()}
                          aria-label={t('common.actions')}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDeleteClick(note.id)
                          }}
                          className="text-destructive focus:text-destructive"
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          {t('notebooks.deleteNote')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                    {onContextModeChange && contextSelections?.[note.id] && (
                      <div onClick={(event) => event.stopPropagation()}>
                        <ContextToggle
                          mode={contextSelections[note.id]}
                          hasInsights={false}
                          onChange={(mode) => onContextModeChange(note.id, mode)}
                          className="h-7 w-7"
                        />
                      </div>
                    )}
                  </div>

                  {note.title && (
                    <h4 className="mb-1 text-[13px] font-medium leading-snug break-words">{note.title}</h4>
                  )}

                  {note.content && (
                    <p className="text-xs leading-relaxed text-muted-foreground line-clamp-3 break-words">
                      {note.content}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <NoteEditorDialog
        open={editorOpen}
        onOpenChange={(open) => {
          setEditorOpen(open)
          if (!open) {
            setEditingNote(undefined)
          }
        }}
        notebookId={notebookId}
        note={editingNote}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title={t('notebooks.deleteNote')}
        description={t('notebooks.deleteNoteConfirm')}
        confirmText={t('common.delete')}
        onConfirm={handleDeleteConfirm}
        isLoading={deleteNote.isPending}
        confirmVariant="destructive"
      />
    </>
  )
}
