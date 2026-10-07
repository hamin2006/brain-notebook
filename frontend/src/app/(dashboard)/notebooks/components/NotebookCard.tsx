'use client'

import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { NotebookResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { MoreHorizontal, Archive, ArchiveRestore, Trash2, FileText, StickyNote, Globe2, ShieldCheck } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useUpdateNotebook } from '@/lib/hooks/use-notebooks'
import { NotebookDeleteDialog } from './NotebookDeleteDialog'
import { useState } from 'react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getDateLocale } from '@/lib/utils/date-locale'
import { sourcesApi } from '@/lib/api/sources'
import { PageThumb } from '@/components/brain/PageThumb'
import { notebookDot } from '@/components/layout/AppSidebar'
import { cn } from '@/lib/utils'

interface NotebookCardProps {
  notebook: NotebookResponse
}

/** First pages of the notebook's first documents, fanned like a stack of decks. */
function NotebookCover({ notebookId, count }: { notebookId: string; count: number }) {
  const { data: sources } = useQuery({
    queryKey: ['sources', 'cover', notebookId],
    queryFn: () => sourcesApi.list({ notebook_id: notebookId, limit: 3, sort_by: 'created', sort_order: 'asc' }),
    enabled: count > 0,
    staleTime: 5 * 60_000,
  })
  const paged = (sources ?? []).filter((s) => s.asset?.file_path)
  return (
    <div className="relative h-40 overflow-hidden rounded-t-xl border-b bg-surface-recessed paper-dots">
      {paged.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn('size-3 rounded-full', notebookDot(notebookId))} />
        </div>
      ) : (
        <div className="absolute inset-x-0 bottom-0 top-5 flex justify-center">
          {paged.slice(0, 3).map((source, i) => {
            const offsets = paged.length === 1 ? [0] : paged.length === 2 ? [-1, 1] : [-1, 0, 1]
            const o = offsets[i]
            return (
              <div
                key={source.id}
                className="absolute bottom-[-18px] w-[58%] transition-transform duration-300 group-hover:-translate-y-1.5"
                style={{
                  transform: `translateX(${o * 34}%) rotate(${o * 4}deg)`,
                  zIndex: o === 0 ? 3 : 2 - i,
                }}
              >
                <PageThumb
                  sourceId={source.id}
                  page={1}
                  className="aspect-[16/10] rounded-md border shadow-lift"
                />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function NotebookCard({ notebook }: NotebookCardProps) {
  const { t, language } = useTranslation()
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const router = useRouter()
  const updateNotebook = useUpdateNotebook()

  const handleArchiveToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    updateNotebook.mutate({
      id: notebook.id,
      data: { archived: !notebook.archived }
    })
  }

  const handleCardClick = () => {
    router.push(`/notebooks/${encodeURIComponent(notebook.id)}`)
  }

  const general = notebook.grounding === 'general'

  return (
    <>
      <div
        role="link"
        tabIndex={0}
        className="group card-hover flex cursor-pointer flex-col rounded-xl border bg-card shadow-soft"
        onClick={handleCardClick}
        onKeyDown={(e) => e.key === 'Enter' && handleCardClick()}
      >
        <NotebookCover notebookId={notebook.id} count={notebook.source_count} />

        <div className="flex flex-1 flex-col p-5">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-display text-[23px] leading-tight tracking-tight line-clamp-2">
              {notebook.name}
            </h3>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="-mr-2 -mt-1 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                  aria-label={t('common.actions')}
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
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
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    setShowDeleteDialog(true)
                  }}
                  className="text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('common.delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
            {notebook.description || t('chat.noDescription')}
          </p>

          <div className="mt-auto flex items-center gap-3 pt-5 text-xs text-muted-foreground">
            <span className="flex items-center gap-1" title={t('navigation.sources')}>
              <FileText className="h-3.5 w-3.5" />
              {notebook.source_count}
            </span>
            <span className="flex items-center gap-1" title={t('common.notes')}>
              <StickyNote className="h-3.5 w-3.5" />
              {notebook.note_count}
            </span>
            <span className="truncate">
              {formatDistanceToNow(new Date(notebook.updated), {
                addSuffix: true,
                locale: getDateLocale(language)
              })}
            </span>
            <span className="flex-1" />
            {notebook.archived ? (
              <Badge variant="secondary">{t('notebooks.archived')}</Badge>
            ) : (
              <Badge variant="secondary" className="gap-1">
                {general ? <Globe2 className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                {general ? t('brain.groundingGeneralShort') : t('brain.groundingStrictShort')}
              </Badge>
            )}
          </div>
        </div>
      </div>

      <NotebookDeleteDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
      />
    </>
  )
}
