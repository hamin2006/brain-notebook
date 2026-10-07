'use client'

import { useMemo, useState } from 'react'
import { Search, Share2, Waypoints } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebookOverview } from '@/lib/hooks/use-explore'
import { useWorkspaceStore } from '@/lib/stores/workspace-store'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'

/** The notebook's concept graph as a ranked, filterable list. */
export function ConceptsPanel({ notebookId }: { notebookId: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useNotebookOverview(notebookId, 200)
  const [filter, setFilter] = useState('')
  const evidence = useWorkspaceStore((s) => s.evidence)
  const openEvidence = useWorkspaceStore((s) => s.openEvidence)
  const view = useWorkspaceStore((s) => s.view)
  const setView = useWorkspaceStore((s) => s.setView)

  const concepts = useMemo(() => {
    const q = filter.trim().toLowerCase()
    const all = data?.top_concepts ?? []
    return q ? all.filter((c) => c.name.toLowerCase().includes(q)) : all
  }, [data, filter])

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  if (!data || data.concepts === 0) {
    return <EmptyState icon={Share2} title={t('brain.noConcepts')} description={t('brain.noConceptsDesc')} />
  }

  const docs = Math.max(data.documents, 1)
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 px-3 pb-2">
        {view !== 'graph' && (
          <button
            type="button"
            onClick={() => setView('graph')}
            className="group flex w-full items-center gap-2.5 rounded-xl border bg-card p-2.5 text-left shadow-soft transition-colors hover:border-iris/40"
          >
            <span className="flex size-8 items-center justify-center rounded-lg bg-iris-tint text-iris">
              <Waypoints className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-medium">{t('brain.openGraph')}</span>
              <span className="block text-[11px] text-muted-foreground">{t('brain.openGraphDesc')}</span>
            </span>
          </button>
        )}
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t('brain.filterConcepts', { count: data.concepts })}
            aria-label={t('brain.filterConcepts', { count: data.concepts })}
            className="h-8 w-full rounded-lg border bg-card pl-8 pr-2 text-[13px] shadow-soft outline-none focus:border-iris/50"
          />
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
        {concepts.map((c) => {
          const active = evidence?.kind === 'concept' && evidence.conceptId === c.id
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => openEvidence({ kind: 'concept', conceptId: c.id, name: c.name })}
              className={cn(
                'group flex w-full items-center gap-3 rounded-lg px-2.5 py-1.5 text-left transition-colors hover:bg-card',
                active && 'bg-card shadow-soft ring-1 ring-inset ring-border'
              )}
            >
              <span className="min-w-0 flex-1 truncate text-[13px]">{c.name}</span>
              <span className="flex w-16 shrink-0 items-center gap-1.5" title={t('brain.conceptSpread', { documents: c.documents, mentions: c.mentions })}>
                <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                  <span className="block h-full rounded-full bg-fern" style={{ width: `${(c.documents / docs) * 100}%` }} />
                </span>
                <span className="w-4 text-right font-mono text-[10px] text-muted-foreground">{c.documents}</span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
