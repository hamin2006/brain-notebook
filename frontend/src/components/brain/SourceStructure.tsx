'use client'

import { useState } from 'react'
import { ChevronRight, LayoutGrid, ListOrdered, Share2, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { SourceStructure } from '@/lib/api/explore'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { PagePreviewDialog, type PageTarget } from '@/components/sources/PagePreviewDialog'
import { PageThumb } from './PageThumb'

const META_KEYS = ['doc_type', 'course', 'sequence', 'date', 'authors'] as const
type MetaKey = (typeof META_KEYS)[number]

/**
 * What ingestion built for one document: its summary, metadata, outline with
 * page ranges, concepts and every page, browsable.
 */
export function SourceStructureView({ structure, onOpenSource }: { structure: SourceStructure; onOpenSource?: (id: string) => void }) {
  const { t } = useTranslation()
  const metaLabels: Record<MetaKey, string> = {
    doc_type: t('brain.meta_doc_type'),
    course: t('brain.meta_course'),
    sequence: t('brain.meta_sequence'),
    date: t('brain.meta_date'),
    authors: t('brain.meta_authors'),
  }
  const [openSection, setOpenSection] = useState<number | null>(null)
  const [pageTarget, setPageTarget] = useState<PageTarget | null>(null)
  const [showAllPages, setShowAllPages] = useState(false)
  const meta = structure.metadata ?? {}
  const topics = Array.isArray(meta.topics) ? (meta.topics as string[]) : []
  const pages = Array.from({ length: structure.page_count }, (_, i) => i + 1)
  const shownPages = showAllPages ? pages : pages.slice(0, 24)

  const openPage = (start: number, end = start) => setPageTarget({ sourceId: structure.id, start, end })

  return (
    <div className="space-y-8">
      {/* Metadata */}
      <div className="flex flex-wrap items-center gap-1.5">
        {META_KEYS.map((key) => {
          const value = meta[key]
          if (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) return null
          return (
            <span key={key} className="rounded-full border bg-card px-2.5 py-0.5 text-[11px]">
              <span className="text-muted-foreground">{metaLabels[key]} </span>
              <span className="font-medium">{Array.isArray(value) ? value.join(', ') : String(value)}</span>
            </span>
          )
        })}
        <span className="rounded-full border bg-card px-2.5 py-0.5 text-[11px] font-medium">
          {t('brain.statPages', { count: structure.page_count })}
        </span>
        {topics.map((topic) => (
          <span key={topic} className="rounded-full bg-surface-recessed px-2.5 py-0.5 text-[11px] text-muted-foreground">
            {topic}
          </span>
        ))}
      </div>

      {/* Summary */}
      {structure.summary && (
        <section className="rounded-2xl border bg-card p-5 shadow-soft">
          <p className="mb-2 flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            <Sparkles className="h-3 w-3 text-iris" />
            {t('brain.documentSummary')}
          </p>
          <div className="answer-prose max-h-[320px] overflow-y-auto pr-2">
            <MarkdownRenderer>{structure.summary}</MarkdownRenderer>
          </div>
        </section>
      )}

      {/* Outline */}
      {structure.sections.length > 0 && (
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            <ListOrdered className="h-3.5 w-3.5" />
            {t('brain.outline', { count: structure.sections.length })}
          </h3>
          <ol className="overflow-hidden rounded-2xl border bg-card shadow-soft">
            {structure.sections.map((section) => {
              const open = openSection === section.index
              const start = section.page_start ?? 1
              const end = section.page_end ?? start
              const preview = Array.from({ length: Math.min(4, end - start + 1) }, (_, i) => start + i)
              return (
                <li key={section.index} className="border-b last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setOpenSection(open ? null : section.index)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50"
                    aria-expanded={open}
                  >
                    <span className="w-6 shrink-0 font-mono text-[11px] text-muted-foreground">{section.index + 1}</span>
                    <span className="min-w-0 flex-1 text-[13.5px] font-medium">{section.title}</span>
                    {section.page_start != null && (
                      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                        {start === end ? t('chat.citePage', { page: start }) : t('chat.citePages', { start, end })}
                      </span>
                    )}
                    <ChevronRight className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />
                  </button>
                  {open && (
                    <div className="space-y-4 px-4 pb-4 pl-[52px] animate-fade-up">
                      {section.page_start != null && (
                        <div className="grid grid-cols-4 gap-2">
                          {preview.map((p) => (
                            <button key={p} type="button" onClick={() => openPage(p, end)} className="overflow-hidden rounded-md border transition-shadow hover:shadow-lift">
                              <PageThumb sourceId={structure.id} page={p} className="aspect-[4/3]" />
                            </button>
                          ))}
                        </div>
                      )}
                      {section.summary && (
                        <div className="answer-prose text-[13.5px]">
                          <MarkdownRenderer>{section.summary}</MarkdownRenderer>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
        </section>
      )}

      {/* Concepts */}
      {structure.concepts.length > 0 && (
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            <Share2 className="h-3.5 w-3.5" />
            {t('brain.conceptsInDocument', { count: structure.concepts.length })}
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {structure.concepts.map((c) => (
              <span key={c.id} className="rounded-full border bg-card px-2.5 py-1 text-xs shadow-soft" title={t('brain.conceptSpread', { documents: c.documents, mentions: c.mentions })}>
                {c.name}
                {c.mentions > 1 && <span className="ml-1 font-mono text-[10px] text-muted-foreground">{c.mentions}</span>}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Pages */}
      {structure.page_count > 0 && (
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            <LayoutGrid className="h-3.5 w-3.5" />
            {t('brain.allPages', { count: structure.page_count })}
          </h3>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
            {shownPages.map((p) => (
              <button key={p} type="button" onClick={() => openPage(p)} className="group relative overflow-hidden rounded-md border transition-shadow hover:shadow-lift">
                <PageThumb sourceId={structure.id} page={p} className="aspect-[4/3]" lazy />
                <span className="absolute bottom-1 right-1 rounded bg-background/85 px-1 font-mono text-[9px]">{p}</span>
              </button>
            ))}
          </div>
          {!showAllPages && pages.length > shownPages.length && (
            <button type="button" onClick={() => setShowAllPages(true)} className="mt-3 text-xs font-medium text-iris hover:underline">
              {t('brain.showAllPages', { count: pages.length })}
            </button>
          )}
        </section>
      )}

      <PagePreviewDialog
        target={pageTarget}
        onClose={() => setPageTarget(null)}
        onOpenSource={(id) => {
          setPageTarget(null)
          onOpenSource?.(id)
        }}
      />
    </div>
  )
}
