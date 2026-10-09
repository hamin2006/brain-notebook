'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowLeft,
  Download,
  Loader2,
  Maximize2,
  Minimize2,
  MoreHorizontal,
  Printer,
  RefreshCw,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { InlineEdit } from '@/components/common/InlineEdit'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { PagePreviewDialog, type PageTarget } from '@/components/sources/PagePreviewDialog'
import { cheatSheetsApi, type SheetCite, type SheetLine, type SheetStatus } from '@/lib/api/cheat-sheets'
import { isBuilding, useCheatSheet, useCheatSheetActions } from '@/lib/hooks/use-cheat-sheets'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SheetPreview, type SheetFit } from './SheetPreview'
import { ReviewRail } from './ReviewRail'

// Below this share of the sheet filled, offer Add more.
const ROOM_LEFT_BELOW = 0.8

function statusText(status: SheetStatus, mode: string | undefined, t: (k: string) => string): string {
  if (status === 'queued') return t('cheatSheet.statusQueued')
  if (status === 'extracting') return t('cheatSheet.statusExtracting')
  // Revise, Shorten and Add more all revise the current version.
  if (status === 'composing') return mode && mode !== 'compose' ? t('cheatSheet.statusRevising') : t('cheatSheet.statusComposing')
  if (status === 'failed') return t('cheatSheet.statusFailed')
  return t('cheatSheet.statusDone')
}

export function CheatSheetWorkspace({ notebookId, sheetId }: { notebookId: string; sheetId: string }) {
  const { t } = useTranslation()
  const router = useRouter()
  const { openModal } = useModalManager()
  const [version, setVersion] = useState<number | null>(null)
  const { data: sheet, isLoading, error } = useCheatSheet(sheetId, version)
  const actions = useCheatSheetActions(sheetId)
  const [selected, setSelected] = useState<string | null>(null)
  const [fit, setFit] = useState<SheetFit | null>(null)
  const [showCites, setShowCites] = useState(true)
  const [printCites, setPrintCites] = useState(false)
  const [pageTarget, setPageTarget] = useState<PageTarget | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const building = isBuilding(sheet?.status)
  const readOnly = !!version && version !== sheet?.current_version
  const layout = sheet?.layout
  const options = sheet?.options

  // A new version replaces the one on screen; an old one is picked explicitly.
  useEffect(() => {
    if (sheet && version && version === sheet.current_version) setVersion(null)
  }, [sheet, version])

  const line: SheetLine | null = useMemo(() => {
    if (!layout || !selected) return null
    for (const topic of layout.topics) {
      const found = topic.lines.find((l) => l.id === selected)
      if (found) return found
    }
    return null
  }, [layout, selected])

  const commentCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const c of sheet?.comments ?? []) if (c.status === 'open' && c.line) counts[c.line] = (counts[c.line] ?? 0) + 1
    return counts
  }, [sheet?.comments])
  const openComments = sheet?.comments.filter((c) => c.status === 'open').length ?? 0

  const onMeasure = useCallback((next: SheetFit) => setFit(next), [])
  const onCiteClick = useCallback((cite: SheetCite) => setPageTarget({ sourceId: cite.source, start: cite.page_start, end: cite.page_end }), [])

  const downloadTex = async () => {
    const blob = await cheatSheetsApi.tex(sheetId, version, printCites)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(sheet?.title || 'cheat-sheet').replace(/[^\w-]+/g, '-')}.tex`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading) return <LoadingSpinner />
  if (error || !sheet || !options) {
    return <div className="p-8 text-sm text-muted-foreground">{t('cheatSheet.notFound')}</div>
  }

  const detail = sheet.detail ?? {}
  const failedSections = detail.failed_sections?.length ?? 0
  const cost = detail.usage?.cost

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-shrink-0 flex-wrap items-center gap-3 border-b bg-background/80 px-4 py-2.5 backdrop-blur md:px-5">
        <Button variant="ghost" size="icon-sm" asChild aria-label={t('cheatSheet.backToNotebook')}>
          <Link href={`/notebooks/${encodeURIComponent(notebookId)}`}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="min-w-0 flex-1">
          <InlineEdit
            value={sheet.title}
            onSave={(title) => {
              if (title.trim() && title !== sheet.title) actions.rename.mutate(title.trim())
            }}
            className="truncate font-display text-[20px] leading-tight tracking-tight"
            inputClassName="font-display text-[20px] tracking-tight"
          />
          <p className="font-mono text-[11px] text-muted-foreground">
            {t('cheatSheet.summaryLine', { documents: sheet.sources.length, pages: options.pages, columns: options.columns })}
            {detail.items ? ` · ${t('cheatSheet.itemsCount', { count: detail.items })}` : ''}
            {typeof cost === 'number' && cost > 0 ? ` · $${cost.toFixed(3)}` : ''}
          </p>
        </div>

        {sheet.versions.length > 1 && (
          <Select value={String(version ?? sheet.current_version ?? '')} onValueChange={(v) => setVersion(Number(v))}>
            <SelectTrigger className="h-8 w-36 text-xs" aria-label={t('cheatSheet.version')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[...sheet.versions].reverse().map((v) => (
                <SelectItem key={v.number} value={String(v.number)} className="text-xs">
                  {v.number === sheet.current_version ? t('cheatSheet.versionCurrent', { number: v.number }) : t('cheatSheet.versionNumber', { number: v.number })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <Button
          size="sm"
          disabled={building || readOnly || openComments === 0 || actions.revise.isPending}
          onClick={() => actions.revise.mutate(undefined)}
          title={openComments === 0 ? t('cheatSheet.reviseHint') : undefined}
        >
          <Sparkles className="mr-1.5 h-3.5 w-3.5" />
          {t('cheatSheet.revise', { count: openComments })}
        </Button>
        <Button variant="outline" size="sm" disabled={!layout} onClick={() => window.print()}>
          <Printer className="mr-1.5 h-3.5 w-3.5" />
          {t('cheatSheet.print')}
        </Button>
        <Button variant="outline" size="sm" disabled={!layout} onClick={downloadTex}>
          <Download className="mr-1.5 h-3.5 w-3.5" />
          .tex
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={t('common.actions')}>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuCheckboxItem checked={showCites} onCheckedChange={setShowCites}>
              {t('cheatSheet.showCitations')}
            </DropdownMenuCheckboxItem>
            <DropdownMenuCheckboxItem checked={printCites} onCheckedChange={setPrintCites}>
              {t('cheatSheet.printCitations')}
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={building} onClick={() => actions.rebuild.mutate(undefined)}>
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('cheatSheet.rebuild')}
            </DropdownMenuItem>
            <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="mr-2 h-4 w-4" />
              {t('common.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="min-h-0 flex-1 overflow-auto bg-muted/50 p-4 md:p-6">
          {building && (
            <div className="mx-auto mb-4 flex max-w-xl items-center gap-3 rounded-lg border bg-card p-3 text-sm shadow-soft">
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-iris" />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{statusText(sheet.status, detail.mode, t)}</p>
                {sheet.status === 'extracting' && !!detail.sections_total && (
                  <>
                    <p className="text-xs text-muted-foreground">
                      {t('cheatSheet.sectionsProgress', { done: detail.sections_done ?? 0, total: detail.sections_total })}
                    </p>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted">
                      <div className="h-full bg-iris transition-all" style={{ width: `${(100 * (detail.sections_done ?? 0)) / detail.sections_total}%` }} />
                    </div>
                  </>
                )}
                {sheet.status === 'extracting' && !detail.sections_total && (
                  <p className="text-xs text-muted-foreground">{t('cheatSheet.extractingHint')}</p>
                )}
              </div>
            </div>
          )}

          {sheet.status === 'failed' && (
            <div className="mx-auto mb-4 flex max-w-xl items-start gap-3 rounded-lg border border-destructive/30 bg-card p-3 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t('cheatSheet.statusFailed')}</p>
                {sheet.error && <p className="text-xs text-muted-foreground">{sheet.error}</p>}
              </div>
              <Button size="sm" variant="outline" onClick={() => actions.rebuild.mutate(undefined)}>
                {t('common.retry')}
              </Button>
            </div>
          )}

          {!building && layout && failedSections > 0 && (
            <p className="mx-auto mb-3 max-w-xl text-center text-xs text-muted-foreground">
              {t('cheatSheet.sectionsFailed', { count: failedSections })}
            </p>
          )}

          {!building && !readOnly && layout && fit && (fit.overflow || fit.fill < ROOM_LEFT_BELOW) && (
            <div className="mx-auto mb-4 flex max-w-xl items-center gap-3 rounded-lg border border-amber/40 bg-amber-tint p-3 text-sm">
              {fit.overflow ? <Minimize2 className="h-4 w-4 shrink-0 text-amber-deep" /> : <Maximize2 className="h-4 w-4 shrink-0 text-amber-deep" />}
              <p className="flex-1">
                {fit.overflow
                  ? t('cheatSheet.overflow', { count: options.pages })
                  : t('cheatSheet.roomLeft', { percent: Math.round((1 - fit.fill) * 100) })}
              </p>
              <Button
                size="sm"
                variant="outline"
                disabled={actions.resize.isPending}
                onClick={() => actions.resize.mutate(fit.overflow ? 'shorten' : 'more')}
              >
                {fit.overflow ? t('cheatSheet.shorten') : t('cheatSheet.addMore')}
              </Button>
            </div>
          )}

          {readOnly && (
            <p className="mx-auto mb-3 max-w-xl text-center text-xs text-muted-foreground">
              {t('cheatSheet.oldVersion', { number: version })}{' '}
              <button type="button" className="underline" onClick={() => setVersion(null)}>
                {t('cheatSheet.showCurrent')}
              </button>
            </p>
          )}

          {layout ? (
            <SheetPreview
              layout={layout}
              options={options}
              names={sheet.source_names}
              selectedLine={selected}
              onSelectLine={readOnly ? () => undefined : setSelected}
              commentCounts={commentCounts}
              showCites={showCites}
              printCites={printCites}
              onCiteClick={onCiteClick}
              onMeasure={onMeasure}
            />
          ) : (
            !building &&
            sheet.status !== 'failed' && <p className="text-center text-sm text-muted-foreground">{t('cheatSheet.empty')}</p>
          )}
        </div>

        {layout && (
          <ReviewRail sheet={sheet} line={line} readOnly={readOnly} building={building} onClearLine={() => setSelected(null)} />
        )}
      </div>

      {mounted &&
        layout &&
        createPortal(
          <div className="cheat-print-portal">
            <style>{`@page { size: ${options.paper === 'a4' ? 'A4' : 'letter'}; margin: 0; }`}</style>
            <SheetPreview
              layout={layout}
              options={options}
              names={sheet.source_names}
              selectedLine={null}
              onSelectLine={() => undefined}
              commentCounts={{}}
              showCites={printCites}
              printCites={printCites}
              onCiteClick={() => undefined}
              onMeasure={() => undefined}
            />
          </div>,
          document.body
        )}

      <PagePreviewDialog
        target={pageTarget}
        onClose={() => setPageTarget(null)}
        onOpenSource={(sourceId) => {
          setPageTarget(null)
          openModal('source', sourceId.replace(/^source:/, ''))
        }}
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('cheatSheet.deleteTitle')}
        description={t('cheatSheet.deleteDescription')}
        confirmText={t('common.delete')}
        confirmVariant="destructive"
        isLoading={actions.remove.isPending}
        onConfirm={async () => {
          await actions.remove.mutateAsync(undefined)
          router.push(`/notebooks/${encodeURIComponent(notebookId)}`)
        }}
      />
    </div>
  )
}
