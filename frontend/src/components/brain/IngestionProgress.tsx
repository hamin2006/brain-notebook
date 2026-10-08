'use client'

import { AlertTriangle, Check, CircleDashed, Loader2, Minus, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useRetryIngestion, useSourceIngestion } from '@/lib/hooks/use-ingestion'
import type { IngestionStage, NotebookIngestion, StageStatus, StageStatusName } from '@/lib/api/ingestion'
import { cn } from '@/lib/utils'

type T = (key: string, options?: Record<string, unknown>) => string

export function stageLabel(t: T, stage: IngestionStage): string {
  switch (stage) {
    case 'extract': return t('brain.stageExtract')
    case 'caption': return t('brain.stageCaption')
    case 'embed': return t('brain.stageEmbed')
    case 'analyze': return t('brain.stageAnalyze')
    case 'page_images': return t('brain.stagePageImages')
    case 'concepts': return t('brain.stageConcepts')
  }
}

function statusLabel(t: T, status: StageStatusName): string {
  switch (status) {
    case 'done': return t('brain.stageDone')
    case 'skipped': return t('brain.stageSkipped')
    case 'queued': return t('brain.stageQueued')
    case 'running': return t('brain.stageRunning')
    case 'failed': return t('brain.stageFailedShort')
    default: return t('brain.stagePending')
  }
}

export function formatDuration(t: T, seconds: number): string {
  return seconds < 90
    ? t('brain.durationSeconds', { seconds: Math.max(1, Math.round(seconds)) })
    : t('brain.durationMinutes', { minutes: (seconds / 60).toFixed(1) })
}

/** Share of the notebook's stage work that is finished, 0–1. */
export function ingestionProgress(data: NotebookIngestion): number {
  let total = 0
  let finished = 0
  for (const item of data.items) {
    for (const stage of item.stages) {
      total += 1
      if (stage.status === 'done' || stage.status === 'skipped') finished += 1
    }
  }
  return total ? finished / total : 1
}

/**
 * The library's indexing strip: how many documents are ready, what the
 * pipeline is doing now, and how many need attention. Hidden once everything
 * is ingested.
 */
export function IngestionStrip({ data }: { data?: NotebookIngestion }) {
  const { t } = useTranslation()
  if (!data || (data.complete && data.sources_failed === 0)) return null
  const progress = ingestionProgress(data)
  const active = Object.entries(data.active) as [IngestionStage, number][]
  return (
    <div className="mx-3 mb-2 rounded-lg border bg-card px-3 py-2" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-[12px] font-medium">
        {data.complete ? (
          <AlertTriangle className="h-3.5 w-3.5 text-warn" />
        ) : (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-iris" />
        )}
        <span className="truncate">
          {t('brain.ingestIndexing', { ready: data.sources_complete, total: data.sources })}
        </span>
        {data.sources_failed > 0 && (
          <span className="ml-auto shrink-0 text-warn">
            {t('brain.ingestNeedAttention', { count: data.sources_failed })}
          </span>
        )}
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-iris transition-all duration-500"
          style={{ width: `${Math.round(progress * 100)}%` }}
        />
      </div>
      {active.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
          {active.map(([stage, count]) => (
            <span key={stage}>
              {stageLabel(t, stage)} · {count}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function StageIcon({ status }: { status: StageStatusName }) {
  switch (status) {
    case 'done':
      return <Check className="h-3.5 w-3.5 text-fern" />
    case 'skipped':
      return <Minus className="h-3.5 w-3.5 text-muted-foreground" />
    case 'running':
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-iris" />
    case 'failed':
      return <AlertTriangle className="h-3.5 w-3.5 text-warn" />
    default:
      return <CircleDashed className="h-3.5 w-3.5 text-muted-foreground" />
  }
}

function stageNote(stage: StageStatus): string | null {
  return stage.status === 'failed' ? (stage.error ?? null) : null
}

/** A source's pipeline: each stage's status and run time, with retry on failure. */
export function IngestionTimeline({ sourceId }: { sourceId: string }) {
  const { t } = useTranslation()
  const { data } = useSourceIngestion(sourceId)
  const retry = useRetryIngestion()
  if (!data) return null
  const total = data.stages.reduce((sum, s) => sum + (s.seconds ?? 0), 0)
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {t('brain.ingestion')}
        </h4>
        {data.complete && total > 0 && (
          <span className="text-[11px] text-muted-foreground">
            {t('brain.ingestionSummary', { duration: formatDuration(t, total) })}
          </span>
        )}
      </div>
      <ol className="mt-2 space-y-1.5">
        {data.stages.map((stage) => {
          const note = stageNote(stage)
          return (
            <li key={stage.stage} className="flex items-start gap-2 text-[13px]">
              <span className="mt-0.5"><StageIcon status={stage.status} /></span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className={cn(stage.status === 'pending' && 'text-muted-foreground')}>
                    {stageLabel(t, stage.stage)}
                  </span>
                  <span className="ml-auto shrink-0 text-[11px] tabular-nums text-muted-foreground">
                    {stage.seconds != null ? formatDuration(t, stage.seconds) : statusLabel(t, stage.status)}
                  </span>
                </div>
                {note && <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{note}</p>}
              </div>
            </li>
          )
        })}
      </ol>
      {data.failed && (
        <Button
          variant="outline"
          size="sm"
          className="mt-2 h-7 text-xs"
          disabled={retry.isPending}
          onClick={() => retry.mutate(sourceId)}
        >
          <RefreshCw className="h-3 w-3" />
          {t('brain.retryStage')}
        </Button>
      )}
    </div>
  )
}
