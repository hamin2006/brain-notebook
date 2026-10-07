'use client'

import { ArrowUpRight, ImagePlus, ScanEye, Share2, TextSearch, Waypoints } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { NotebookOverview } from '@/lib/api/explore'
import { useWorkspaceStore } from '@/lib/stores/workspace-store'
import { BrainMark } from '@/components/brand/BrainMark'

/**
 * The empty conversation: what the notebook holds and what the agent can do
 * with it, as starters built from the notebook's own concepts.
 */
export function ChatWelcome({
  notebookName,
  overview,
  onAsk,
  allowImages,
}: {
  notebookName?: string
  overview?: NotebookOverview
  onAsk: (question: string) => void
  allowImages?: boolean
}) {
  const { t } = useTranslation()
  const openEvidence = useWorkspaceStore((s) => s.openEvidence)
  const concepts = overview?.top_concepts ?? []
  const pick = (i: number, fallback: string) => concepts[i]?.name ?? fallback

  const starters = [
    {
      icon: Waypoints,
      tone: 'text-iris',
      title: t('brain.starterTraceTitle'),
      prompt: t('brain.starterTracePrompt', { concept: pick(0, t('brain.starterFallbackConcept')) }),
    },
    {
      icon: TextSearch,
      tone: 'text-amber',
      title: t('brain.starterEveryTitle'),
      prompt: t('brain.starterEveryPrompt', { concept: pick(1, t('brain.starterFallbackConcept')) }),
    },
    {
      icon: ScanEye,
      tone: 'text-plum',
      title: t('brain.starterDiagramTitle'),
      prompt: t('brain.starterDiagramPrompt', { concept: pick(2, t('brain.starterFallbackConcept')) }),
    },
    {
      icon: Share2,
      tone: 'text-fern',
      title: t('brain.starterRelateTitle'),
      prompt: t('brain.starterRelatePrompt', {
        a: pick(3, t('brain.starterFallbackConcept')),
        b: pick(4, t('brain.starterFallbackConcept2')),
      }),
    },
  ]

  return (
    <div className="mx-auto flex w-full max-w-[46rem] flex-col items-center px-2 pb-6 pt-[8vh] text-center animate-fade-up">
      <BrainMark className="size-10" />
      <h2 className="mt-5 font-display text-[40px] leading-[1.05] tracking-tight">
        {t('brain.welcomeTitle')}
      </h2>
      <p className="mt-3 max-w-md text-sm text-muted-foreground">
        {overview
          ? t('brain.welcomeStats', {
              name: notebookName ?? '',
              documents: overview.documents,
              pages: overview.pages,
              concepts: overview.concepts,
            })
          : t('brain.welcomeFallback')}
      </p>

      <div className="mt-8 grid w-full grid-cols-1 gap-2.5 text-left sm:grid-cols-2">
        {starters.map((s) => (
          <button
            key={s.title}
            type="button"
            onClick={() => onAsk(s.prompt)}
            className="group card-hover flex flex-col gap-2 rounded-xl border bg-card p-3.5 shadow-soft"
          >
            <span className="flex items-center gap-2 text-xs font-medium">
              <s.icon className={`h-3.5 w-3.5 ${s.tone}`} />
              {s.title}
              <ArrowUpRight className="ml-auto h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </span>
            <span className="text-[13px] leading-snug text-muted-foreground group-hover:text-foreground">{s.prompt}</span>
          </button>
        ))}
      </div>

      {concepts.length > 0 && (
        <div className="mt-8 w-full">
          <p className="mb-2.5 text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {t('brain.keyConcepts')}
          </p>
          <div className="flex flex-wrap justify-center gap-1.5">
            {concepts.slice(0, 14).map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => openEvidence({ kind: 'concept', conceptId: c.id, name: c.name })}
                className="rounded-full border bg-card px-2.5 py-1 text-xs shadow-soft transition-colors hover:border-fern/50 hover:text-fern"
                title={t('brain.conceptSpread', { documents: c.documents, mentions: c.mentions })}
              >
                {c.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {allowImages && (
        <p className="mt-8 flex items-center gap-1.5 text-xs text-muted-foreground">
          <ImagePlus className="h-3.5 w-3.5" />
          {t('brain.imageHint')}
        </p>
      )}
    </div>
  )
}
