'use client'

import { useState } from 'react'
import { Check, ChevronRight, Loader2 } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { AgentActivity as Activity } from '@/lib/hooks/use-notebook-chat'
import type { AgentStep, ChatEffort } from '@/lib/types/api'

type Translate = (key: string, options?: Record<string, unknown>) => string

const TOOL_KEYS: Record<string, string> = {
  list: 'chat.agentToolList',
  grep: 'chat.agentToolGrep',
  search: 'chat.agentToolSearch',
  outline: 'chat.agentToolOutline',
  read: 'chat.agentToolRead',
  view: 'chat.agentToolView',
  answer: 'chat.agentToolAnswer',
}

/** "Searching for “adam optimizer”" from a tool name and its arguments. */
export function describeStep(tool: string, args: Record<string, unknown>, t: Translate): string {
  const label = TOOL_KEYS[tool] ? t(TOOL_KEYS[tool]) : tool
  const subject =
    args.query || args.pattern || args.address || args.source || args.like || args.title_contains ||
    (args.sequence !== undefined && args.sequence !== null ? `#${args.sequence}` : '')
  return subject ? `${label} “${String(subject)}”` : label
}

export function AgentActivityView({ activity }: { activity: Activity }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg px-4 py-3 bg-card border space-y-2 min-w-0 max-w-full">
      <div className="flex items-center gap-2 text-xs font-medium text-teal">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {t('chat.researching')}
      </div>
      {activity.steps.length > 0 && (
        <ol className="space-y-1">
          {activity.steps.map((step, index) => (
            <li key={`${step.step}-${index}`} className="flex gap-2 text-xs text-muted-foreground min-w-0">
              {step.summary === undefined ? (
                <Loader2 className="h-3 w-3 mt-0.5 flex-shrink-0 animate-spin" />
              ) : (
                <Check className="h-3 w-3 mt-0.5 flex-shrink-0 text-teal" />
              )}
              <span className="min-w-0 break-words">
                {describeStep(step.tool, step.args, t)}
                {step.summary && <span className="block opacity-75 truncate">{step.summary}</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
      {activity.text && (
        <div className="border-t pt-2 text-sm">
          <MarkdownRenderer>{activity.text}</MarkdownRenderer>
        </div>
      )}
    </div>
  )
}

export function ResearchSteps({ trace }: { trace: AgentStep[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  if (!trace.length) return null
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronRight className={`h-3 w-3 transition-transform ${open ? 'rotate-90' : ''}`} />
        {t('chat.researchSteps', { count: trace.length })}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mt-1 space-y-1 border-l pl-3">
          {trace.map((step, index) => (
            <li key={index} className="text-xs text-muted-foreground break-words">
              {describeStep(step.tool, step.args, t)}
              {step.result && <span className="block opacity-75 truncate">{step.result}</span>}
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function EffortSelect({
  value,
  onChange,
  disabled,
}: {
  value: ChatEffort
  onChange: (effort: ChatEffort) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <Select value={value} onValueChange={v => onChange(v as ChatEffort)} disabled={disabled}>
      <SelectTrigger className="h-8 w-[130px] text-xs" aria-label={t('chat.effort')}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="quick">{t('chat.effortQuick')}</SelectItem>
        <SelectItem value="standard">{t('chat.effortStandard')}</SelectItem>
        <SelectItem value="deep">{t('chat.effortDeep')}</SelectItem>
      </SelectContent>
    </Select>
  )
}

/** Localized page/section labels for citations: "#p12-18" -> "pp. 12–18". */
export function localizedLocator(t: Translate) {
  return (locator: string): string => {
    const pages = /^#p(\d+)(?:-(\d+))?$/.exec(locator)
    if (pages) {
      return pages[2] && pages[2] !== pages[1]
        ? t('chat.citePages', { start: pages[1], end: pages[2] })
        : t('chat.citePage', { page: pages[1] })
    }
    const section = /^#s(\d+)$/.exec(locator)
    if (section) return t('chat.citeSection', { index: section[1] })
    if (locator === '/summary') return t('chat.citeSummary')
    if (locator === '/outline') return t('chat.citeOutline')
    return locator
  }
}
