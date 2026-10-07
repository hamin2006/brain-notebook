'use client'

import { useState } from 'react'
import { NotebookResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import Link from 'next/link'
import { Archive, ArchiveRestore, Trash2, PanelLeft, Globe2, ShieldCheck, ChevronDown, MoreHorizontal, MessagesSquare, Waypoints } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { useWorkspaceStore } from '@/lib/stores/workspace-store'
import type { NotebookOverview } from '@/lib/api/explore'
import { useUpdateNotebook } from '@/lib/hooks/use-notebooks'
import { NotebookDeleteDialog } from './NotebookDeleteDialog'
import { formatDistanceToNow } from 'date-fns'
import { getDateLocale } from '@/lib/utils/date-locale'
import { InlineEdit } from '@/components/common/InlineEdit'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotebookHeaderProps {
  notebook: NotebookResponse
  overview?: NotebookOverview
}

export function NotebookHeader({ notebook, overview }: NotebookHeaderProps) {
  const libraryOpen = useWorkspaceStore((s) => s.libraryOpen)
  const toggleLibrary = useWorkspaceStore((s) => s.toggleLibrary)
  const setLibraryTab = useWorkspaceStore((s) => s.setLibraryTab)
  const view = useWorkspaceStore((s) => s.view)
  const setView = useWorkspaceStore((s) => s.setView)
  const { t, language } = useTranslation()
  const dfLocale = getDateLocale(language)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  
  const updateNotebook = useUpdateNotebook()

  const handleUpdateName = async (name: string) => {
    if (!name || name === notebook.name) return
    
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: { name }
    })
  }

  const handleUpdateDescription = async (description: string) => {
    if (description === notebook.description) return
    
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: { description }
    })
  }

  const handleArchiveToggle = () => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { archived: !notebook.archived }
    })
  }

  const general = notebook.grounding === 'general'

  return (
    <>
      <header className="flex flex-shrink-0 items-center gap-4 border-b bg-background/80 px-4 py-2.5 backdrop-blur md:px-5">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={toggleLibrary}
          className={cn('hidden text-muted-foreground lg:inline-flex', libraryOpen && 'bg-accent text-foreground')}
          aria-label={t('brain.toggleLibrary')}
          aria-pressed={libraryOpen}
          title={t('brain.toggleLibrary')}
        >
          <PanelLeft className="h-4 w-4" />
        </Button>

        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <Link href="/notebooks" className="hidden shrink-0 text-xs text-muted-foreground hover:text-foreground sm:inline">
              {t('navigation.notebooks')}
            </Link>
            <span className="hidden text-xs text-muted-foreground/50 sm:inline">/</span>
            <InlineEdit
              id="notebook-name"
              name="notebook-name"
              value={notebook.name}
              onSave={handleUpdateName}
              className="min-w-0 truncate font-display text-[22px] leading-tight tracking-tight"
              inputClassName="font-display text-[22px] tracking-tight"
              placeholder={t('notebooks.namePlaceholder')}
            />
            {notebook.archived && (
              <Badge variant="secondary">{t('notebooks.archived')}</Badge>
            )}
          </div>
          <InlineEdit
            id="notebook-description"
            name="notebook-description"
            value={notebook.description || ''}
            onSave={handleUpdateDescription}
            className="truncate text-xs text-muted-foreground"
            inputClassName="text-xs text-muted-foreground"
            placeholder={t('notebooks.addDescription')}
            multiline
            emptyText={t('notebooks.addDescription')}
          />
        </div>

        {overview && (
          <div className="hidden items-center gap-3 font-mono text-[11px] text-muted-foreground xl:flex">
            <span title={t('navigation.sources')}>{t('brain.statDocuments', { count: overview.documents })}</span>
            <span aria-hidden className="text-muted-foreground/40">·</span>
            <span>{t('brain.statPages', { count: overview.pages })}</span>
            {overview.concepts > 0 && (
              <>
                <span aria-hidden className="text-muted-foreground/40">·</span>
                <button type="button" className="hover:text-foreground" onClick={() => setLibraryTab('concepts')}>
                  {t('brain.statConcepts', { count: overview.concepts })}
                </button>
              </>
            )}
          </div>
        )}

        <div className="flex shrink-0 items-center rounded-lg bg-surface-recessed p-0.5" role="tablist" aria-label={t('brain.workspaceView')}>
          {([
            { value: 'chat', icon: MessagesSquare, label: t('common.chat') },
            { value: 'graph', icon: Waypoints, label: t('brain.graph') },
          ] as const).map(({ value, icon: Icon, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={view === value}
              onClick={() => setView(value)}
              className={cn(
                'flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors',
                view === value ? 'bg-card text-foreground shadow-soft' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className={cn('h-3.5 w-3.5', view === value && value === 'graph' && 'text-iris')} />
              <span className="hidden md:inline">{label}</span>
            </button>
          ))}
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(
                'flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium shadow-soft transition-colors',
                general ? 'border-iris/30 bg-iris-tint text-iris-deep' : 'bg-card text-foreground hover:bg-accent'
              )}
              aria-label={t('chat.grounding')}
            >
              {general ? <Globe2 className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5 text-fern" />}
              <span className="hidden sm:inline">{general ? t('brain.groundingGeneralShort') : t('brain.groundingStrictShort')}</span>
              <ChevronDown className="h-3 w-3 opacity-60" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 p-1.5">
            {(['strict', 'general'] as const).map((value) => (
              <DropdownMenuItem
                key={value}
                onClick={() => updateNotebook.mutate({ id: notebook.id, data: { grounding: value } })}
                className={cn('items-start gap-3 rounded-lg p-2.5', (notebook.grounding ?? 'strict') === value && 'bg-accent')}
              >
                {value === 'strict' ? <ShieldCheck className="mt-0.5 h-4 w-4 text-fern" /> : <Globe2 className="mt-0.5 h-4 w-4 text-iris" />}
                <div>
                  <p className="text-[13px] font-medium">{value === 'strict' ? t('chat.groundingStrict') : t('chat.groundingGeneral')}</p>
                  <p className="text-xs text-muted-foreground">
                    {value === 'strict' ? t('brain.groundingStrictDesc') : t('brain.groundingGeneralDesc')}
                  </p>
                </div>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="text-muted-foreground" aria-label={t('common.actions')}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={handleArchiveToggle}>
              {notebook.archived ? (
                <>
                  <ArchiveRestore className="h-4 w-4 mr-2" />
                  {t('notebooks.unarchive')}
                </>
              ) : (
                <>
                  <Archive className="h-4 w-4 mr-2" />
                  {t('notebooks.archive')}
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setShowDeleteDialog(true)} className="text-destructive focus:text-destructive">
              <Trash2 className="h-4 w-4 mr-2" />
              {t('common.delete')}
            </DropdownMenuItem>
            <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
              {t('common.created', { time: formatDistanceToNow(new Date(notebook.created), { addSuffix: true, locale: dfLocale }) })}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <NotebookDeleteDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
        redirectAfterDelete
      />
    </>
  )
}