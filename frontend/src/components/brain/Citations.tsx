'use client'

import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { FileText, Lightbulb, StickyNote } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { ReferenceData, ReferenceType } from '@/lib/utils/source-references'
import { localizedLocator } from '@/components/sources/AgentActivity'
import { PageThumb } from './PageThumb'

export type ReferenceClick = (type: ReferenceType, id: string, locator?: string) => void

/** "p12-18" or "#p12-18" -> first page; null for other locators. */
export function firstPage(locator?: string): number | null {
  const match = locator ? /^#?p(\d+)/.exec(locator) : null
  return match ? Number(match[1]) : null
}

/** An href locator ("p12-18", "s3", "summary") back in address form ("#p12-18", "/summary"). */
export function addressLocator(locator: string): string {
  if (/^[#/]/.test(locator)) return locator
  return /^[psc]\d/.test(locator) ? `#${locator}` : `/${locator}`
}

/** "#ref-source-abc@p12-18" -> its parts (the href convertReferencesToCompactMarkdown writes). */
export function parseReferenceHref(href: string): { type: ReferenceType; id: string; locator?: string } | null {
  if (!href.startsWith('#ref-')) return null
  const [target, locator] = href.substring(5).split('@')
  const parts = target.split('-')
  return { type: parts[0] as ReferenceType, id: parts.slice(1).join('-'), locator }
}

/** An inline numbered citation; hovering shows the cited page. */
export function CitationChip({
  number,
  type,
  id,
  locator,
  title,
  onClick,
}: {
  number: React.ReactNode
  type: ReferenceType
  id: string
  locator?: string
  title?: string
  onClick: ReferenceClick
}) {
  const { t } = useTranslation()
  const page = type === 'source' ? firstPage(locator) : null
  const where = locator ? localizedLocator(t)(addressLocator(locator)) : null
  return (
    <TooltipPrimitive.Provider delayDuration={120}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <button
            type="button"
            className="cite-chip"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onClick(type, id, locator)
            }}
          >
            {number}
          </button>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side="top"
            sideOffset={6}
            className="z-50 w-64 overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-pop animate-in fade-in-0 zoom-in-95"
          >
            {page ? <PageThumb sourceId={id} page={page} className="aspect-[16/10] border-b" /> : null}
            <div className="flex items-start gap-2 p-2.5">
              {type === 'note' ? (
                <StickyNote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
              ) : type === 'source_insight' ? (
                <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
              ) : (
                <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
              )}
              <div className="min-w-0">
                <p className="line-clamp-2 text-xs font-medium">{title ?? `${type}:${id}`}</p>
                {where && <p className="mt-0.5 font-mono text-[10.5px] text-muted-foreground">{where}</p>}
              </div>
            </div>
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

/** The pages an answer cites, as a row of thumbnails under it. */
export function CitedSources({
  references,
  titles,
  onClick,
}: {
  references: ReferenceData[]
  titles: Record<string, string>
  onClick: ReferenceClick
}) {
  const { t } = useTranslation()
  if (!references.length) return null
  const label = localizedLocator(t)
  return (
    <div className="space-y-2">
      <p className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
        {t('brain.sourcesCited', { count: references.length })}
      </p>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {references.map((ref) => {
          const page = ref.type === 'source' ? firstPage(ref.locator) : null
          const title = titles[`${ref.type}:${ref.id}`] ?? `${ref.type}:${ref.id}`
          return (
            <button
              key={`${ref.type}:${ref.id}${ref.locator ?? ''}`}
              type="button"
              onClick={() => onClick(ref.type, ref.id, ref.locator?.replace(/^#/, ''))}
              className={cn(
                'group w-[150px] shrink-0 overflow-hidden rounded-xl border bg-card text-left shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-lift'
              )}
            >
              <div className="relative">
                {page ? (
                  <PageThumb sourceId={ref.id} page={page} className="aspect-[16/10] border-b" />
                ) : (
                  <div className="flex aspect-[16/10] items-center justify-center border-b bg-surface-recessed text-muted-foreground">
                    {ref.type === 'note' ? <StickyNote className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                  </div>
                )}
                <span className="absolute left-1.5 top-1.5 cite-chip !m-0 bg-card">{ref.number}</span>
              </div>
              <div className="p-2">
                <p className="truncate text-[11.5px] font-medium" title={title}>{title}</p>
                {ref.locator && <p className="font-mono text-[10px] text-muted-foreground">{label(ref.locator)}</p>}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
