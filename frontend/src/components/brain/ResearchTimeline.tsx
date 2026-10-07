'use client'

import { useEffect, useState } from 'react'
import {
  BookOpenText,
  Brain,
  Calculator,
  ChevronDown,
  Eraser,
  Globe,
  Globe2,
  ListOrdered,
  ListTree,
  NotebookPen,
  PenLine,
  ScanEye,
  Search,
  Share2,
  ShieldCheck,
  TextSearch,
  Users,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { describeStep } from '@/components/sources/AgentActivity'
import type { AgentActivity } from '@/lib/hooks/use-notebook-chat'
import type { AgentStep } from '@/lib/types/api'

export const TOOL_ICONS: Record<string, LucideIcon> = {
  list: ListTree,
  grep: TextSearch,
  search: Search,
  outline: ListOrdered,
  read: BookOpenText,
  view: ScanEye,
  graph: Share2,
  delegate: Users,
  note: NotebookPen,
  calculate: Calculator,
  review: ShieldCheck,
  remember: Brain,
  forget: Eraser,
  web_search: Globe,
  web_read: Globe2,
  answer: PenLine,
}

/** Distinct documents and pages a trace touched, from the addresses in its arguments. */
export function traceStats(steps: { tool: string; args: Record<string, unknown> }[]) {
  const documents = new Set<string>()
  let pages = 0
  for (const step of steps) {
    const text = JSON.stringify(step.args ?? {})
    for (const match of text.matchAll(/source:([a-zA-Z0-9_]+)/g)) documents.add(match[1])
    if (step.tool === 'view') pages += 1
  }
  return { steps: steps.length, documents: documents.size, pagesViewed: pages }
}

function StepRow({
  tool,
  args,
  result,
  running,
  index,
}: {
  tool: string
  args: Record<string, unknown>
  result?: string
  running?: boolean
  index: number
}) {
  const { t } = useTranslation()
  const Icon = TOOL_ICONS[tool] ?? Wrench
  return (
    <li className="relative flex gap-3 pb-3 last:pb-0 animate-fade-up" style={{ animationDelay: `${Math.min(index, 6) * 20}ms` }}>
      <span
        className={cn(
          'relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full border bg-card',
          running ? 'border-iris/40 text-iris' : 'text-muted-foreground'
        )}
      >
        <Icon className={cn('h-3 w-3', running && 'animate-pulse')} />
      </span>
      <div className="min-w-0 flex-1 pt-0.5">
        <p className={cn('text-[12.5px] leading-snug break-words', running ? 'text-foreground' : 'text-ink-soft')}>
          {describeStep(tool, args, t)}
        </p>
        {result && (
          <p className="mt-0.5 truncate font-mono text-[10.5px] text-muted-foreground" title={result}>
            {result}
          </p>
        )}
      </div>
    </li>
  )
}

function Timeline({ children }: { children: React.ReactNode }) {
  return (
    <ol className="relative before:absolute before:bottom-3 before:left-[11.5px] before:top-3 before:w-px before:bg-border">
      {children}
    </ol>
  )
}

function useElapsed(start: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return Math.max(0, Math.round((now - start) / 1000))
}

/** The agent at work: a live timeline of tool calls with a rotating iris edge. */
export function LiveResearch({ activity, startedAt }: { activity: AgentActivity; startedAt: number }) {
  const { t } = useTranslation()
  const elapsed = useElapsed(startedAt)
  const writing = activity.text.length > 0
  const stats = traceStats(activity.steps)
  return (
    <div className="agent-live rounded-2xl border bg-card p-4 shadow-soft">
      <div className="mb-3 flex items-center gap-2">
        <span className="relative flex size-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-iris opacity-60" />
          <span className="relative inline-flex size-2 rounded-full bg-iris" />
        </span>
        <span className="shimmer-text text-[13px] font-medium">
          {writing ? t('brain.writingAnswer') : t('chat.researching')}
        </span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          {stats.steps > 0 && `${t('brain.traceSteps', { count: stats.steps })} · `}
          {elapsed}s
        </span>
      </div>
      {activity.steps.length > 0 && (
        <Timeline>
          {activity.steps.map((step, index) => (
            <StepRow
              key={`${step.step}-${index}`}
              index={index}
              tool={step.tool}
              args={step.args}
              result={step.summary}
              running={step.summary === undefined}
            />
          ))}
        </Timeline>
      )}
    </div>
  )
}

/** A finished answer's research, folded into one line until opened. */
export function ResearchTrace({ trace }: { trace: AgentStep[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  if (!trace.length) return null
  const stats = traceStats(trace)
  const tools = [...new Set(trace.map((s) => s.tool))].slice(0, 6)
  return (
    <div className="rounded-xl border bg-surface-recessed/60">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-muted-foreground hover:text-foreground"
        aria-expanded={open}
      >
        <span className="flex -space-x-1">
          {tools.map((tool) => {
            const Icon = TOOL_ICONS[tool] ?? Wrench
            return (
              <span key={tool} className="flex size-5 items-center justify-center rounded-full border bg-card">
                <Icon className="h-2.5 w-2.5" />
              </span>
            )
          })}
        </span>
        <span className="font-medium text-foreground/80">{t('brain.researchedSummary', { count: stats.steps })}</span>
        {stats.documents > 0 && <span>· {t('brain.traceDocuments', { count: stats.documents })}</span>}
        {stats.pagesViewed > 0 && <span>· {t('brain.tracePagesViewed', { count: stats.pagesViewed })}</span>}
        <ChevronDown className={cn('ml-auto h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="border-t px-3 py-3">
          <Timeline>
            {trace.map((step, index) => (
              <StepRow key={index} index={index} tool={step.tool} args={step.args} result={step.result} />
            ))}
          </Timeline>
        </div>
      )}
    </div>
  )
}
