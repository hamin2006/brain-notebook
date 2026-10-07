'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, ArrowUpRight, ChevronLeft, ChevronRight, FileText, Loader2, Share2, Sparkles, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useConcept, useSourceStructure } from '@/lib/hooks/use-explore'
import { useWorkspaceStore, type EvidenceTarget } from '@/lib/stores/workspace-store'
import { PageThumb } from './PageThumb'

/**
 * The right-hand panel of the notebook workspace: the exact pages an answer
 * cites (rendered, browsable) or a concept from the graph with its mentions.
 */
export function EvidencePanel({
  notebookId,
  sourceTitles,
  onOpenSource,
}: {
  notebookId: string
  sourceTitles: Record<string, string>
  onOpenSource: (sourceId: string) => void
}) {
  const evidence = useWorkspaceStore((s) => s.evidence)
  const close = useWorkspaceStore((s) => s.closeEvidence)
  if (!evidence) return null
  return (
    <div className="flex h-full min-h-0 flex-col animate-fade-up">
      {evidence.kind === 'pages' ? (
        <PagesView target={evidence} title={sourceTitles[normalizeId(evidence.sourceId)]} onClose={close} onOpenSource={onOpenSource} />
      ) : (
        <ConceptView notebookId={notebookId} target={evidence} sourceTitles={sourceTitles} onClose={close} />
      )}
    </div>
  )
}

const normalizeId = (id: string) => (id.startsWith('source:') ? id : `source:${id}`)

function PanelHeader({ eyebrow, title, onClose, icon }: { eyebrow: string; title: string; onClose: () => void; icon: React.ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-start gap-3 border-b px-4 py-3">
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-surface-recessed">{icon}</div>
      <div className="min-w-0 flex-1">
        <p className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{eyebrow}</p>
        <h2 className="truncate text-[13px] font-semibold" title={title}>{title}</h2>
      </div>
      <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t('common.close')}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

function PagesView({
  target,
  title,
  onClose,
  onOpenSource,
}: {
  target: Extract<EvidenceTarget, { kind: 'pages' }>
  title?: string
  onClose: () => void
  onOpenSource: (sourceId: string) => void
}) {
  const { t } = useTranslation()
  const [page, setPage] = useState(target.start)
  const { data: structure } = useSourceStructure(normalizeId(target.sourceId))
  const pageCount = structure?.page_count || target.end

  useEffect(() => setPage(target.start), [target])

  const cited = page >= target.start && page <= target.end
  const section = structure?.sections.find(
    (s) => s.page_start != null && s.page_end != null && page >= s.page_start && page <= s.page_end
  )
  const range = useMemo(() => {
    const pages: number[] = []
    for (let p = target.start; p <= Math.min(target.end, target.start + 11); p++) pages.push(p)
    return pages
  }, [target])

  return (
    <>
      <PanelHeader
        eyebrow={t('brain.evidence')}
        title={title || structure?.metadata?.title as string || t('common.source')}
        onClose={onClose}
        icon={<FileText className="h-3.5 w-3.5 text-amber" />}
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className={cn('overflow-hidden rounded-xl border bg-white shadow-lift', cited && 'ring-2 ring-amber/50')}>
          <PageThumb
            sourceId={target.sourceId}
            page={page}
            size="full"
            className="min-h-[220px]"
            imgClassName="object-contain h-auto"
            alt={t('chat.pagePreviewTitle', { page })}
          />
        </div>

        <div className="mt-3 flex items-center gap-2">
          <Button variant="outline" size="icon-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label={t('chat.previousPage')}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1 text-center text-xs text-muted-foreground">
            <span className="font-mono text-foreground">{t('chat.citePage', { page })}</span>
            {structure?.page_count ? <span> / {pageCount}</span> : null}
            {cited && (
              <span className="ml-2 rounded-full bg-amber-tint px-1.5 py-0.5 text-[10px] font-medium text-amber-deep">
                {t('brain.cited')}
              </span>
            )}
          </div>
          <Button variant="outline" size="icon-sm" disabled={!!structure?.page_count && page >= pageCount} onClick={() => setPage((p) => p + 1)} aria-label={t('chat.nextPage')}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        {section && (
          <div className="mt-4 rounded-xl border bg-card p-3">
            <p className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{t('brain.inSection')}</p>
            <p className="mt-0.5 text-[13px] font-medium">{section.title}</p>
            <p className="font-mono text-[11px] text-muted-foreground">
              {t('chat.citePages', { start: section.page_start, end: section.page_end })}
            </p>
          </div>
        )}

        {range.length > 1 && (
          <div className="mt-4">
            <p className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{t('brain.citedPages')}</p>
            <div className="grid grid-cols-4 gap-2">
              {range.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  className={cn(
                    'group relative overflow-hidden rounded-md border transition-shadow hover:shadow-lift',
                    p === page && 'ring-2 ring-amber'
                  )}
                >
                  <PageThumb sourceId={target.sourceId} page={p} className="aspect-[4/3]" />
                  <span className="absolute bottom-0.5 right-0.5 rounded bg-background/85 px-1 font-mono text-[9px]">{p}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="border-t p-3">
        <Button variant="outline" size="sm" className="w-full" onClick={() => onOpenSource(target.sourceId)}>
          {t('chat.openSource')}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </>
  )
}

function ConceptView({
  notebookId,
  target,
  sourceTitles,
  onClose,
}: {
  notebookId: string
  target: Extract<EvidenceTarget, { kind: 'concept' }>
  sourceTitles: Record<string, string>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { data, isLoading } = useConcept(notebookId, target.conceptId)
  const openEvidence = useWorkspaceStore((s) => s.openEvidence)
  const ask = useWorkspaceStore((s) => s.ask)
  const name = data?.name ?? target.name ?? ''

  const bySource = useMemo(() => {
    const groups = new Map<string, { title: string; mentions: NonNullable<typeof data>['mentions'] }>()
    for (const m of data?.mentions ?? []) {
      const group = groups.get(m.source_id) ?? { title: sourceTitles[m.source_id] ?? m.source_title, mentions: [] }
      group.mentions.push(m)
      groups.set(m.source_id, group)
    }
    return [...groups.entries()]
  }, [data, sourceTitles])

  return (
    <>
      <PanelHeader eyebrow={t('brain.concept')} title={name} onClose={onClose} icon={<Share2 className="h-3.5 w-3.5 text-fern" />} />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <h3 className="font-display text-[30px] leading-tight tracking-tight">{name}</h3>
        {data && (
          <p className="mt-1 text-xs text-muted-foreground">
            {t('brain.conceptStats', { documents: bySource.length, mentions: data.mentions.length, relations: data.relations.length })}
          </p>
        )}
        <Button
          variant="agent"
          size="sm"
          className="mt-4"
          onClick={() => ask(t('brain.explainConceptPrompt', { name }))}
          disabled={!name}
        >
          <Sparkles className="h-3.5 w-3.5" />
          {t('brain.askAboutThis')}
        </Button>

        {isLoading && (
          <div className="flex justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {data && data.relations.length > 0 && (
          <section className="mt-6">
            <p className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{t('brain.relations')}</p>
            <div className="space-y-1.5">
              {data.relations.slice(0, 16).map((r, i) => (
                <button
                  key={`${r.concept_id}-${i}`}
                  type="button"
                  onClick={() => openEvidence({ kind: 'concept', conceptId: r.concept_id, name: r.name })}
                  className="flex w-full items-center gap-2 rounded-lg border bg-card px-3 py-2 text-left text-[13px] transition-colors hover:border-foreground/20"
                >
                  {r.outgoing ? (
                    <>
                      <span className="shrink-0 text-muted-foreground">{name}</span>
                      <span className="shrink-0 rounded-full bg-fern-tint px-1.5 py-0.5 text-[10.5px] text-fern">{r.relation}</span>
                      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="truncate font-medium">{r.name}</span>
                    </>
                  ) : (
                    <>
                      <span className="truncate font-medium">{r.name}</span>
                      <span className="shrink-0 rounded-full bg-fern-tint px-1.5 py-0.5 text-[10.5px] text-fern">{r.relation}</span>
                      <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="shrink-0 text-muted-foreground">{name}</span>
                    </>
                  )}
                </button>
              ))}
            </div>
          </section>
        )}

        {bySource.length > 0 && (
          <section className="mt-6">
            <p className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{t('brain.whereItAppears')}</p>
            <div className="space-y-3">
              {bySource.map(([sourceId, group]) => (
                <div key={sourceId} className="rounded-xl border bg-card p-3">
                  <p className="truncate text-[13px] font-medium" title={group.title}>{group.title}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {group.mentions.map((m, i) =>
                      m.page_start ? (
                        <button
                          key={i}
                          type="button"
                          title={m.context ?? undefined}
                          onClick={() =>
                            openEvidence({ kind: 'pages', sourceId, start: m.page_start as number, end: (m.page_end ?? m.page_start) as number })
                          }
                          className="cite-chip !h-6 !px-2 !text-[11px]"
                        >
                          {m.page_end && m.page_end !== m.page_start
                            ? t('chat.citePages', { start: m.page_start, end: m.page_end })
                            : t('chat.citePage', { page: m.page_start })}
                        </button>
                      ) : null
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  )
}
