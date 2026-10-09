'use client'

import { useEffect, useState } from 'react'
import { Check, MessageSquarePlus, Pencil, Pin, PinOff, RotateCcw, Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { CheatSheet, SheetLine } from '@/lib/api/cheat-sheets'
import { useCheatSheetActions } from '@/lib/hooks/use-cheat-sheets'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ReviewRailProps {
  sheet: CheatSheet
  line: SheetLine | null
  /** Viewing an older version: review is read-only. */
  readOnly: boolean
  building: boolean
  onClearLine: () => void
}

/** Comments, hand edits and pins; Revise applies the open comments. */
export function ReviewRail({ sheet, line, readOnly, building, onClearLine }: ReviewRailProps) {
  const { t } = useTranslation()
  const actions = useCheatSheetActions(sheet.id)
  const [comment, setComment] = useState('')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  useEffect(() => {
    setEditing(false)
    setComment('')
  }, [line?.id])

  const locked = readOnly || building
  const open = sheet.comments.filter((c) => c.status === 'open')
  const addressed = sheet.comments.filter((c) => c.status === 'addressed').reverse()

  const submitComment = async () => {
    if (!comment.trim()) return
    await actions.addComment.mutateAsync({ text: comment.trim(), line: line?.id ?? null })
    setComment('')
  }

  const lineLabel = (lineId?: string | null) => (lineId ? t('cheatSheet.onLine', { line: lineId }) : t('cheatSheet.onSheet'))

  return (
    <aside className="flex w-full flex-col gap-4 overflow-y-auto border-l bg-background p-4 lg:w-80 lg:shrink-0">
      {line ? (
        <div className="space-y-2 rounded-lg border bg-card p-3 shadow-soft">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">
              {t('cheatSheet.lineHeading', { line: line.id })}
              {line.edited && ` · ${t('cheatSheet.edited')}`}
            </span>
            <Button variant="ghost" size="icon-sm" onClick={onClearLine} aria-label={t('common.close')}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
          {editing ? (
            <>
              <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={5} className="font-mono text-xs" />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  {t('common.cancel')}
                </Button>
                <Button
                  size="sm"
                  disabled={!draft.trim() || actions.updateLine.isPending}
                  onClick={async () => {
                    await actions.updateLine.mutateAsync({ lineId: line.id, text: draft })
                    setEditing(false)
                  }}
                >
                  {t('common.save')}
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">{t('cheatSheet.editHint')}</p>
            </>
          ) : (
            !locked && (
              <div className="flex flex-wrap gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setDraft(line.text)
                    setEditing(true)
                  }}
                >
                  <Pencil className="mr-1.5 h-3.5 w-3.5" />
                  {t('common.edit')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => actions.updateLine.mutate({ lineId: line.id, pinned: !line.pinned })}
                  title={t('cheatSheet.pinHint')}
                >
                  {line.pinned ? <PinOff className="mr-1.5 h-3.5 w-3.5" /> : <Pin className="mr-1.5 h-3.5 w-3.5" />}
                  {line.pinned ? t('cheatSheet.unpin') : t('cheatSheet.pin')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={async () => {
                    await actions.deleteLine.mutateAsync(line.id)
                    onClearLine()
                  }}
                >
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                  {t('cheatSheet.removeLine')}
                </Button>
              </div>
            )
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t('cheatSheet.selectLineHint')}</p>
      )}

      {!locked && (
        <div className="space-y-2">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitComment()
            }}
            placeholder={line ? t('cheatSheet.commentLinePlaceholder') : t('cheatSheet.commentSheetPlaceholder')}
            rows={2}
            className="text-sm"
          />
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">{lineLabel(line?.id)}</span>
            <Button size="sm" variant="outline" disabled={!comment.trim() || actions.addComment.isPending} onClick={submitComment}>
              <MessageSquarePlus className="mr-1.5 h-3.5 w-3.5" />
              {t('cheatSheet.addComment')}
            </Button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t('cheatSheet.openComments', { count: open.length })}
        </h4>
        {open.length === 0 && <p className="text-xs text-muted-foreground">{t('cheatSheet.noOpenComments')}</p>}
        {open.map((c) => (
          <div key={c.id} className="group rounded-md border bg-card p-2.5 text-sm">
            <div className="mb-1 flex items-center justify-between font-mono text-[11px] text-muted-foreground">
              <span>{lineLabel(c.line)}</span>
              {!locked && (
                <span className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button type="button" title={t('cheatSheet.resolve')} onClick={() => actions.resolveComment.mutate({ commentId: c.id, status: 'addressed' })}>
                    <Check className="h-3.5 w-3.5 hover:text-fern" />
                  </button>
                  <button type="button" title={t('common.delete')} onClick={() => actions.deleteComment.mutate(c.id)}>
                    <Trash2 className="h-3.5 w-3.5 hover:text-destructive" />
                  </button>
                </span>
              )}
            </div>
            {c.text}
          </div>
        ))}
      </div>

      {addressed.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('cheatSheet.addressedComments')}</h4>
          {addressed.map((c) => (
            <div key={c.id} className={cn('rounded-md border border-dashed p-2.5 text-xs text-muted-foreground')}>
              <div className="mb-1 flex items-center justify-between font-mono text-[11px]">
                <span>
                  {lineLabel(c.line)} · v{c.version}
                </span>
                {!locked && (
                  <button type="button" title={t('cheatSheet.reopen')} onClick={() => actions.resolveComment.mutate({ commentId: c.id, status: 'open' })}>
                    <RotateCcw className="h-3 w-3 hover:text-foreground" />
                  </button>
                )}
              </div>
              <p className="line-through decoration-muted-foreground/40">{c.text}</p>
              {c.note && <p className="mt-1 text-iris">{c.note}</p>}
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
