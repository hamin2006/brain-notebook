'use client'

import { useMemo, useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import { NotebookList } from './components/NotebookList'
import { RecentlyViewed } from './components/RecentlyViewed'
import { Button } from '@/components/ui/button'
import { Plus, RefreshCw, LayoutGrid, List, Search, Quote, ScanEye, Share2, Brain } from 'lucide-react'
import { AskBar } from '@/components/brain/AskBar'
import { cn } from '@/lib/utils'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { CreateNotebookDialog } from '@/components/notebooks/CreateNotebookDialog'
import { Input } from '@/components/ui/input'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebookViewStore } from '@/lib/stores/notebook-view-store'

export default function NotebooksPage() {
  const { t } = useTranslation()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const viewMode = useNotebookViewStore((state) => state.viewMode)
  const setViewMode = useNotebookViewStore((state) => state.setViewMode)
  const { data: notebooks, isLoading, refetch } = useNotebooks(false)
  const { data: archivedNotebooks } = useNotebooks(true)

  const normalizedQuery = searchTerm.trim().toLowerCase()

  const filteredActive = useMemo(() => {
    if (!notebooks) {
      return undefined
    }
    if (!normalizedQuery) {
      return notebooks
    }
    return notebooks.filter((notebook) =>
      notebook.name.toLowerCase().includes(normalizedQuery)
    )
  }, [notebooks, normalizedQuery])

  const filteredArchived = useMemo(() => {
    if (!archivedNotebooks) {
      return undefined
    }
    if (!normalizedQuery) {
      return archivedNotebooks
    }
    return archivedNotebooks.filter((notebook) =>
      notebook.name.toLowerCase().includes(normalizedQuery)
    )
  }, [archivedNotebooks, normalizedQuery])

  const hasArchived = (archivedNotebooks?.length ?? 0) > 0
  const isSearching = normalizedQuery.length > 0

  const totalSources = (notebooks ?? []).reduce((sum, n) => sum + n.source_count, 0)

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        {/* Hero: greeting and a question for every notebook */}
        <section className="relative border-b paper-dots">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-background/40 to-background" />
          <div className="relative mx-auto max-w-5xl px-6 pb-10 pt-14 md:px-10">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {t('common.appName')}
            </p>
            <h1 className="mt-2 font-display text-[44px] leading-[1.05] tracking-tight md:text-[56px]">
              {t(greetingKey())}
            </h1>
            <p className="mt-3 max-w-xl text-[15px] text-muted-foreground">
              {t('brain.homeSubtitle', { notebooks: notebooks?.length ?? 0, documents: totalSources })}
            </p>
            <AskBar className="mt-7 max-w-2xl" />
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><Quote className="h-3.5 w-3.5 text-amber" />{t('brain.featureCited')}</span>
              <span className="flex items-center gap-1.5"><ScanEye className="h-3.5 w-3.5 text-iris" />{t('brain.featureVisual')}</span>
              <span className="flex items-center gap-1.5"><Share2 className="h-3.5 w-3.5 text-fern" />{t('brain.featureGraph')}</span>
              <span className="flex items-center gap-1.5"><Brain className="h-3.5 w-3.5 text-plum" />{t('brain.featureMemory')}</span>
            </div>
          </div>
        </section>

        <div className="mx-auto max-w-6xl space-y-10 px-6 py-8 md:px-10">
          <RecentlyViewed />

          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-display text-[28px] tracking-tight">{t('notebooks.title')}</h2>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="notebook-search"
                    name="notebook-search"
                    value={searchTerm}
                    onChange={(event) => setSearchTerm(event.target.value)}
                    placeholder={t('notebooks.searchPlaceholder')}
                    autoComplete="off"
                    aria-label={t('common.accessibility.searchNotebooks') || "Search notebooks"}
                    className="h-8 w-48 pl-8 text-[13px] sm:w-56"
                  />
                </div>
                <div className="flex items-center rounded-lg border bg-card p-0.5 shadow-soft">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className={cn('size-7', viewMode === 'tile' && 'bg-accent')}
                    onClick={() => setViewMode('tile')}
                    aria-label={t('notebooks.tileView')}
                    aria-pressed={viewMode === 'tile'}
                    title={t('notebooks.tileView')}
                  >
                    <LayoutGrid className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className={cn('size-7', viewMode === 'list' && 'bg-accent')}
                    onClick={() => setViewMode('list')}
                    aria-label={t('notebooks.listView')}
                    aria-pressed={viewMode === 'list'}
                    title={t('notebooks.listView')}
                  >
                    <List className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <Button variant="ghost" size="icon-sm" onClick={() => refetch()} aria-label={t('common.refresh')} title={t('common.refresh')}>
                  <RefreshCw className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" onClick={() => setCreateDialogOpen(true)}>
                  <Plus className="h-4 w-4" />
                  {t('notebooks.newNotebook')}
                </Button>
              </div>
            </div>

            <NotebookList
              notebooks={filteredActive}
              isLoading={isLoading}
              title={t('notebooks.activeNotebooks')}
              hideTitle
              emptyTitle={isSearching ? t('common.noMatches') : undefined}
              emptyDescription={isSearching ? t('common.tryDifferentSearch') : undefined}
              onAction={!isSearching ? () => setCreateDialogOpen(true) : undefined}
              actionLabel={!isSearching ? t('notebooks.newNotebook') : undefined}
            />
          </section>

          {hasArchived && (
            <NotebookList
              notebooks={filteredArchived}
              isLoading={false}
              title={t('notebooks.archivedNotebooks')}
              collapsible
              emptyTitle={isSearching ? t('common.noMatches') : undefined}
              emptyDescription={isSearching ? t('common.tryDifferentSearch') : undefined}
            />
          )}
        </div>
      </div>

      <CreateNotebookDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
    </AppShell>
  )
}

/** Locale key for a greeting that fits the time of day. */
function greetingKey(): string {
  const hour = new Date().getHours()
  if (hour < 5) return 'brain.greetingNight'
  if (hour < 12) return 'brain.greetingMorning'
  if (hour < 18) return 'brain.greetingAfternoon'
  return 'brain.greetingEvening'
}
