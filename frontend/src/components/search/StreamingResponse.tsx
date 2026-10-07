'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { useTranslation } from '@/lib/hooks/use-translation'
import { toast } from 'sonner'
import { BrainMark } from '@/components/brand/BrainMark'
import { LiveResearch, ResearchTrace } from '@/components/brain/ResearchTimeline'
import { AnswerContent } from '@/components/brain/Answer'
import type { ReferenceClick } from '@/components/brain/Citations'
import { PagePreviewDialog, PageTarget, parsePageLocator } from '@/components/sources/PagePreviewDialog'
import type { AgentStep } from '@/lib/types/api'

interface StrategyData {
  reasoning: string
  searches: Array<{ term: string; instructions: string }>
}

interface StreamingResponseProps {
  isStreaming: boolean
  strategy: StrategyData | null
  answers: string[]
  finalAnswer: string | null
}

/** Ask's answer: the agent's research steps as they happen, then the cited answer. */
export function StreamingResponse({
  isStreaming,
  strategy,
  finalAnswer
}: StreamingResponseProps) {
  const { openModal } = useModalManager()
  const { t } = useTranslation()
  const [pageTarget, setPageTarget] = useState<PageTarget | null>(null)
  const [startedAt, setStartedAt] = useState(() => Date.now())

  useEffect(() => {
    if (isStreaming) setStartedAt(Date.now())
  }, [isStreaming])

  // Each "search" of the strategy is one tool call: instructions = tool, term = its subject
  const steps: AgentStep[] = useMemo(
    () => (strategy?.searches ?? []).map((s) => ({ tool: s.instructions, args: { query: s.term } })),
    [strategy]
  )

  const handleReferenceClick = useCallback<ReferenceClick>((type, id, locator) => {
    const pages = type === 'source' ? parsePageLocator(locator) : null
    if (pages) {
      setPageTarget({ sourceId: id, ...pages })
      return
    }
    const modalType = type === 'source_insight' ? 'insight' : type as 'source' | 'note' | 'insight'
    try {
      openModal(modalType, id)
    } catch {
      const typeLabel = type === 'source_insight' ? 'insight' : type
      toast.error(t('common.itemNotFound', { type: typeLabel }))
    }
  }, [openModal, t])

  if (!strategy && !finalAnswer && !isStreaming) {
    return null
  }

  return (
    <div
      className="space-y-4 animate-fade-up"
      role="region"
      aria-label={t('common.accessibility.askResponse')}
      aria-live="polite"
      aria-busy={isStreaming}
    >
      <div className="flex items-center gap-2">
        <BrainMark className="size-6" />
        <span className="text-[13px] font-semibold">{t('brain.agentName')}</span>
      </div>

      {isStreaming && !finalAnswer ? (
        steps.length > 0 ? (
          <LiveResearch
            activity={{
              steps: steps.map((s, i) => ({ step: i, tool: s.tool, args: s.args, summary: i < steps.length - 1 ? '' : undefined })),
              text: '',
            }}
            startedAt={startedAt}
          />
        ) : (
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin text-iris" />
            <span className="shimmer-text">{t('chat.researching')}</span>
          </div>
        )
      ) : (
        steps.length > 0 && <ResearchTrace trace={steps} />
      )}

      {finalAnswer && <AnswerContent content={finalAnswer} onReferenceClick={handleReferenceClick} />}

      <PagePreviewDialog
        target={pageTarget}
        onClose={() => setPageTarget(null)}
        onOpenSource={(sourceId) => {
          setPageTarget(null)
          openModal('source', sourceId.replace(/^source:/, ''))
        }}
      />
    </div>
  )
}
