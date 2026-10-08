'use client'

import React, { useState, useEffect, memo } from 'react'
import { SourceListResponse } from '@/lib/types/api'
import { PageThumb } from '@/components/brain/PageThumb'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from '@/components/ui/dropdown-menu'
import {
  FileText,
  ExternalLink,
  Upload,
  MoreVertical,
  Trash2,
  RefreshCw,
  Clock,
  CheckCircle,
  AlertTriangle,
  Loader2,
  Unlink
} from 'lucide-react'
import { useSourceStatus } from '@/lib/hooks/use-sources'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { TFunction } from 'i18next'
import { cn } from '@/lib/utils'
import { ContextToggle } from '@/components/common/ContextToggle'
import { ContextMode } from '@/app/(dashboard)/notebooks/[id]/page'
import { stageLabel } from '@/components/brain/IngestionProgress'
import type { IngestionStage } from '@/lib/api/ingestion'

interface SourceCardProps {
  source: SourceListResponse
  onDelete?: (sourceId: string) => void
  onRetry?: (sourceId: string) => void
  onRefreshContent?: (sourceId: string) => void
  onRemoveFromNotebook?: (sourceId: string) => void
  onClick?: (sourceId: string) => void
  onRefresh?: () => void
  className?: string
  showRemoveFromNotebook?: boolean
  contextMode?: ContextMode
  onContextModeChange?: (mode: ContextMode) => void
  /** The ingestion stage in progress after extraction (captions, concepts…). */
  ingestionStage?: IngestionStage | null
  /** A stage that failed after extraction, retried with onRetryStage. */
  ingestionFailedStage?: IngestionStage | null
  onRetryStage?: (sourceId: string) => void
}

const SOURCE_TYPE_ICONS = {
  link: ExternalLink,
  upload: Upload,
  text: FileText,
} as const

const getStatusConfig = (t: TFunction) => ({
  new: {
    icon: Clock,
    color: 'text-teal',
    bgColor: 'bg-teal-tint',
    borderColor: 'border-teal/30',
    label: t('sources.statusProcessing'),
    description: t('sources.statusPreparingDesc')
  },
  queued: {
    icon: Clock,
    color: 'text-teal',
    bgColor: 'bg-teal-tint',
    borderColor: 'border-teal/30',
    label: t('sources.statusQueued'),
    description: t('sources.statusQueuedDesc')
  },
  running: {
    icon: Loader2,
    color: 'text-teal',
    bgColor: 'bg-teal-tint',
    borderColor: 'border-teal/30',
    label: t('sources.statusProcessing'),
    description: t('sources.statusProcessingDesc')
  },
  completed: {
    icon: CheckCircle,
    color: 'text-fern',
    bgColor: 'bg-fern-tint',
    borderColor: 'border-fern/30',
    label: t('sources.statusCompleted'),
    description: t('sources.statusCompletedDesc')
  },
  failed: {
    icon: AlertTriangle,
    color: 'text-destructive',
    bgColor: 'bg-destructive-tint',
    borderColor: 'border-destructive/30',
    label: t('sources.statusFailed'),
    description: t('sources.statusFailedDesc')
  }
} as const)

type SourceStatus = 'new' | 'queued' | 'running' | 'completed' | 'failed'

function isSourceStatus(status: unknown): status is SourceStatus {
  return typeof status === 'string' && ['new', 'queued', 'running', 'completed', 'failed'].includes(status)
}

function getSourceType(source: SourceListResponse): 'link' | 'upload' | 'text' {
  // Determine type based on asset information
  if (source.asset?.url) return 'link'
  if (source.asset?.file_path) return 'upload'
  return 'text'
}

function SourceCardImpl({
  source,
  onClick,
  onDelete,
  onRetry,
  onRefreshContent,
  onRemoveFromNotebook,
  onRefresh,
  className,
  showRemoveFromNotebook = false,
  contextMode,
  onContextModeChange,
  ingestionStage,
  ingestionFailedStage,
  onRetryStage
}: SourceCardProps) {
  const { t } = useTranslation()
  const statusConfigMap = getStatusConfig(t)
  
  // Only fetch status for sources that might have async processing
  const sourceWithStatus = source as SourceListResponse & { command_id?: string; status?: string }

  // Track processing state to continue polling until we detect completion
  const [wasProcessing, setWasProcessing] = useState(false)

  // Only poll status while the source is actually being processed (or just finished
  // and we still need one more poll to catch completion). The list endpoint already
  // populates `status` alongside `command_id`, so we no longer poll for every
  // completed source — that scaled linearly with the number of cards and caused the
  // list lag reported in #503.
  //
  // A source with a `command_id` but no resolved `status` yet is still ambiguous
  // (it renders as a synthetic "new"), so keep polling those until a real status
  // arrives — otherwise such a card would be stuck "processing" forever.
  const shouldFetchStatus =
    sourceWithStatus.status === 'new' ||
    sourceWithStatus.status === 'queued' ||
    sourceWithStatus.status === 'running' ||
    (!!sourceWithStatus.command_id && !sourceWithStatus.status) ||
    wasProcessing // Keep polling if we were processing to catch the completion

  const { data: statusData, isLoading: statusLoading } = useSourceStatus(
    source.id,
    shouldFetchStatus
  )

  // Determine current status
  // If source has a command_id but no status, treat as "new" (just created)
  const rawStatus = statusData?.status || sourceWithStatus.status
  const currentStatus: SourceStatus = isSourceStatus(rawStatus)
    ? rawStatus
    : (sourceWithStatus.command_id ? 'new' : 'completed')


  // Track processing state and detect completion
  useEffect(() => {
    const currentStatusFromData = statusData?.status || sourceWithStatus.status

    // If we're currently processing, mark that we were processing
    if (currentStatusFromData === 'new' || currentStatusFromData === 'running' || currentStatusFromData === 'queued') {
      setWasProcessing(true)
    }

    // If we were processing and now completed/failed, trigger refresh and stop polling
    if (wasProcessing &&
        (currentStatusFromData === 'completed' || currentStatusFromData === 'failed')) {
      setWasProcessing(false) // Stop polling

      if (onRefresh) {
        setTimeout(() => onRefresh(), 500) // Small delay to ensure API is updated
      }
    }
  }, [statusData, sourceWithStatus.status, wasProcessing, onRefresh, source.id])
  
  const statusConfig = statusConfigMap[currentStatus] || statusConfigMap.completed
  const StatusIcon = statusConfig.icon
  const sourceType = getSourceType(source)
  const SourceTypeIcon = SOURCE_TYPE_ICONS[sourceType]
  
   const title = source.title || t('sources.untitledSource')

  const handleRetry = () => {
    if (onRetry) {
      onRetry(source.id)
    }
  }

  const handleRefreshContent = () => {
    if (onRefreshContent) {
      onRefreshContent(source.id)
    }
  }

  const handleDelete = () => {
    if (onDelete) {
      onDelete(source.id)
    }
  }

  const handleRemoveFromNotebook = () => {
    if (onRemoveFromNotebook) {
      onRemoveFromNotebook(source.id)
    }
  }

  const handleCardClick = () => {
    if (onClick) {
      onClick(source.id)
    }
  }

  const isProcessing: boolean = currentStatus === 'new' || currentStatus === 'running' || currentStatus === 'queued'
  const isFailed: boolean = currentStatus === 'failed'
  const isCompleted: boolean = currentStatus === 'completed'

  const hasPages = /\.(pdf|png|jpe?g|webp|gif|tiff?|bmp)$/i.test(source.asset?.file_path ?? '')
  const excluded = contextMode === 'off'

  return (
    <div
      className={cn(
        'group relative flex cursor-pointer gap-3 rounded-xl border border-transparent p-2 transition-colors hover:border-border hover:bg-card hover:shadow-soft',
        excluded && 'opacity-55',
        className
      )}
      onClick={handleCardClick}
    >
      {/* Page-one thumbnail (or the source type) */}
      {hasPages ? (
        <PageThumb sourceId={source.id} page={1} className="h-[46px] w-[62px] shrink-0 rounded-md border" />
      ) : (
        <div className="flex h-[46px] w-[62px] shrink-0 items-center justify-center rounded-md border bg-surface-recessed text-muted-foreground">
          <SourceTypeIcon className="h-4 w-4" />
        </div>
      )}

      <div className="min-w-0 flex-1 pr-7">
        <h4 className="text-[13px] font-medium leading-snug line-clamp-2 break-words" title={title}>
          {title}
        </h4>

        {!isCompleted ? (
          <div className={cn('mt-1 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium', statusConfig.bgColor, statusConfig.color)}>
            <StatusIcon className={cn('h-3 w-3', isProcessing && 'animate-spin')} />
            {statusLoading && shouldFetchStatus ? t('sources.checking') : statusConfig.label}
          </div>
        ) : (
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[11px] text-muted-foreground">
            {source.topics && source.topics.length > 0 ? (
              <span className="truncate">
                {source.topics.slice(0, 2).join(' · ')}
                {source.topics.length > 2 && ` +${source.topics.length - 2}`}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <SourceTypeIcon className="h-3 w-3" />
                {sourceType === 'link' ? t('sources.addUrl') : sourceType === 'upload' ? t('sources.uploadFile') : t('sources.enterText')}
              </span>
            )}
          </div>
        )}

        {isCompleted && ingestionFailedStage ? (
          <div className="mt-1 flex items-center gap-1.5 text-[11px] text-warn">
            <AlertTriangle className="h-3 w-3 shrink-0" />
            <span className="truncate">{t('brain.stageFailed', { stage: stageLabel(t, ingestionFailedStage) })}</span>
            {onRetryStage && (
              <button
                type="button"
                className="ml-1 shrink-0 font-medium text-foreground hover:underline"
                onClick={(e) => {
                  e.stopPropagation()
                  onRetryStage(source.id)
                }}
              >
                {t('brain.retryStage')}
              </button>
            )}
          </div>
        ) : isCompleted && ingestionStage ? (
          <div className="mt-1 flex items-center gap-1.5 text-[11px] text-iris">
            <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
            <span className="truncate">{stageLabel(t, ingestionStage)}</span>
          </div>
        ) : null}

        {statusData?.message && (isProcessing || isFailed) && (
          <p className="mt-1 text-[11px] italic text-muted-foreground">{statusData.message}</p>
        )}

        {isProcessing && typeof statusData?.processing_info?.progress === 'number' && (
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-iris transition-all duration-300"
              style={{ width: `${statusData.processing_info.progress as number}%` }}
            />
          </div>
        )}

        {/* Prominent retry action surfaced directly on failed cards so it's
            discoverable without opening the dropdown menu (#726). */}
        {isFailed ? (
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              handleRetry()
            }}
            disabled={!onRetry}
            className="mt-2 h-7 text-xs"
          >
            <RefreshCw className="h-3 w-3" />
            {t('sources.retryProcessing')}
          </Button>
        ) : null}
      </div>

      {/* Context toggle and actions */}
      <div className="absolute right-1.5 top-1.5 flex flex-col items-center gap-0.5">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 data-[state=open]:opacity-100"
              onClick={(e) => e.stopPropagation()}
              aria-label={t('common.actions')}
            >
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            {showRemoveFromNotebook && (
              <>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRemoveFromNotebook()
                  }}
                  disabled={!onRemoveFromNotebook}
                >
                  <Unlink className="h-4 w-4 mr-2" />
                  {t('sources.removeFromNotebook')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}

            {isFailed && (
              <>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRetry()
                  }}
                  disabled={!onRetry}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  {t('sources.retryProcessing')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}

            {sourceType === 'link' && isCompleted && onRefreshContent && (
              <>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRefreshContent()
                  }}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  {t('sources.refreshContent')}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}

            <DropdownMenuItem
              onClick={(e) => {
                e.stopPropagation()
                handleDelete()
              }}
              disabled={!onDelete}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              {t('sources.deleteSource')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {onContextModeChange && contextMode && (
          <ContextToggle
            mode={contextMode}
            hasInsights={source.insights_count > 0}
            onChange={onContextModeChange}
            className="h-7 w-7"
          />
        )}
      </div>
    </div>
  )
}

/**
 * SourceCard is rendered in long lists (one per source). Without memoization, any
 * parent re-render (layout toggles, context-selection changes elsewhere) re-rendered
 * every card, causing UI jank that scaled with the number of sources (#503).
 *
 * We compare only the props that affect this card's rendered output. Handler identity
 * is intentionally ignored: callers often pass inline closures, and those closures
 * capture the source id, so a stale closure stays correct as long as the source data
 * below is unchanged.
 */
function topicsEqual(a?: string[], b?: string[]): boolean {
  if (a === b) return true
  if ((a?.length ?? 0) !== (b?.length ?? 0)) return false
  if (!a || !b) return true // both empty/undefined (lengths matched above)
  return a.every((topic, i) => topic === b[i])
}

function areEqual(prev: SourceCardProps, next: SourceCardProps): boolean {
  if (prev === next) return true

  const p = prev.source as SourceListResponse & { command_id?: string; status?: string }
  const n = next.source as SourceListResponse & { command_id?: string; status?: string }

  return (
    p.id === n.id &&
    p.title === n.title &&
    p.updated === n.updated &&
    p.status === n.status &&
    p.command_id === n.command_id &&
    p.embedded === n.embedded &&
    p.insights_count === n.insights_count &&
    p.asset?.url === n.asset?.url &&
    p.asset?.file_path === n.asset?.file_path &&
    topicsEqual(p.topics, n.topics) &&
    prev.contextMode === next.contextMode &&
    prev.ingestionStage === next.ingestionStage &&
    prev.ingestionFailedStage === next.ingestionFailedStage &&
    prev.showRemoveFromNotebook === next.showRemoveFromNotebook &&
    prev.className === next.className
  )
}

export const SourceCard = memo(SourceCardImpl, areEqual)
