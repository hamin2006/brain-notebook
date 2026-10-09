'use client'

import { memo, useLayoutEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { MessageSquare, Pin } from 'lucide-react'
import { KATEX_OPTIONS } from '@/lib/utils/katex-options'
import { cn } from '@/lib/utils'
import type { SheetCite, SheetLayout, SheetLine, SheetOptions } from '@/lib/api/cheat-sheets'
import { COLUMN_GAP_PT, MARGIN_IN, citeLabel, pageGeometry } from './sheet-utils'

export interface SheetFit {
  /** The content runs past the last column of the last page. */
  overflow: boolean
  /** How much of the sheet the content fills (0-1; 1 when it overflows). */
  fill: number
}

interface SheetPreviewProps {
  /** The sheet's title (renaming it doesn't touch stored layouts). */
  title: string
  layout: SheetLayout
  options: SheetOptions
  names: Record<string, string>
  selectedLine: string | null
  onSelectLine: (lineId: string | null) => void
  commentCounts: Record<string, number>
  showCites: boolean
  printCites: boolean
  onCiteClick: (cite: SheetCite) => void
  onMeasure: (fit: SheetFit) => void
}

const LineText = memo(function LineText({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[[rehypeKatex, KATEX_OPTIONS]]}
      components={{ p: ({ children }) => <>{children}</> }}
    >
      {text}
    </ReactMarkdown>
  )
})

function Flow({
  layout,
  names,
  selectedLine,
  onSelectLine,
  commentCounts,
  showCites,
  printCites,
  onCiteClick,
}: Omit<SheetPreviewProps, 'options' | 'onMeasure' | 'title'>) {
  const line = (l: SheetLine) => (
    <div
      key={l.id}
      data-line={l.id}
      role="button"
      tabIndex={0}
      onClick={(e) => {
        e.stopPropagation()
        onSelectLine(selectedLine === l.id ? null : l.id)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelectLine(selectedLine === l.id ? null : l.id)
        }
      }}
      className={cn(
        'sheet-line cursor-pointer rounded-[2px] outline-none [break-inside:avoid]',
        'hover:bg-accent/60 focus-visible:bg-accent/60',
        selectedLine === l.id && 'bg-amber-tint ring-1 ring-amber/60'
      )}
    >
      {(l.pinned || commentCounts[l.id]) && (
        <span className="sheet-screen-only mr-0.5 inline-flex items-center gap-0.5 align-middle text-[0.8em] text-amber">
          {l.pinned && <Pin className="h-[0.9em] w-[0.9em]" />}
          {!!commentCounts[l.id] && <MessageSquare className="h-[0.9em] w-[0.9em]" />}
        </span>
      )}
      <LineText text={l.text} />
      {l.cites.length > 0 && (
        <span className={cn('sheet-cites ml-0.5 whitespace-nowrap', !showCites && 'sheet-hidden-on-screen', !printCites && 'sheet-hidden-in-print')}>
          {l.cites.map((cite, i) => (
            <button
              key={i}
              type="button"
              title={`${names[cite.source] ?? ''} p. ${cite.page_start}${cite.page_end !== cite.page_start ? `–${cite.page_end}` : ''}`}
              onClick={(e) => {
                e.stopPropagation()
                onCiteClick(cite)
              }}
              className="ml-0.5 align-super text-[0.7em] leading-none text-muted-foreground hover:text-amber"
            >
              {citeLabel(cite, names)}
            </button>
          ))}
        </span>
      )}
    </div>
  )
  return (
    <>
      {layout.topics.map((topic) => (
        <section key={topic.id}>
          <h3 className="sheet-topic mt-[0.35em] rounded-[2px] bg-muted px-[0.3em] text-[1.05em] font-bold leading-tight [break-after:avoid] first:mt-0">
            {topic.title}
          </h3>
          {topic.lines.map(line)}
        </section>
      ))}
    </>
  )
}

/**
 * The sheet at its printed size. The content is one multi-column flow as wide
 * as all pages side by side and as tall as one page; each page shows its slice
 * of it, so what is on screen is what prints. The browser measures the flow
 * to report overflow (Shorten) and leftover room (Add more).
 */
export function SheetPreview(props: SheetPreviewProps) {
  const { layout, options, onMeasure } = props
  const g = pageGeometry(options)
  const gapIn = COLUMN_GAP_PT / 72
  const flowWidth = options.pages * g.contentWidth + (options.pages - 1) * gapIn
  const flowRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    const flow = flowRef.current
    const end = endRef.current
    if (!flow || !end) return
    const measure = () => {
      const overflow = flow.scrollWidth > flow.clientWidth + 2
      if (overflow) return onMeasure({ overflow: true, fill: 1 })
      const box = flow.getBoundingClientRect()
      const mark = end.getBoundingClientRect()
      const columnsTotal = options.pages * options.columns
      const columnWidth = (box.width - (columnsTotal - 1) * (gapIn * 96)) / columnsTotal
      const column = Math.min(columnsTotal - 1, Math.max(0, Math.floor((mark.left - box.left) / (columnWidth + gapIn * 96))))
      const within = Math.min(1, Math.max(0, (mark.bottom - box.top) / box.height))
      onMeasure({ overflow: false, fill: (column + within) / columnsTotal })
    }
    measure()
    // KaTeX fonts load late and change line heights.
    const fonts = (document as Document & { fonts?: FontFaceSet }).fonts
    fonts?.ready.then(measure).catch(() => undefined)
    const observer = new ResizeObserver(measure)
    observer.observe(flow)
    return () => observer.disconnect()
  }, [layout, options.pages, options.columns, options.paper, props.showCites, gapIn, onMeasure])

  // One height for every page's slice (the first page also holds the title),
  // so columns break at the same place in each copy.
  const flowHeight = `calc(${g.contentHeight}in - ${(g.font + 2) * 1.5}pt)`
  const flowStyle = {
    width: `${flowWidth}in`,
    height: flowHeight,
    columnCount: options.pages * options.columns,
    columnGap: `${COLUMN_GAP_PT}pt`,
    columnFill: 'auto' as const,
    columnRule: '0.5pt solid var(--border)',
    fontSize: `${g.font}pt`,
    lineHeight: 1.2,
  }

  return (
    <div className="cheat-sheet flex flex-col items-center gap-6" onClick={() => props.onSelectLine(null)}>
      {Array.from({ length: options.pages }, (_, page) => (
        <div
          key={page}
          className="cheat-sheet-page shrink-0 bg-card text-card-foreground shadow-soft ring-1 ring-border"
          style={{ width: `${g.paperWidth}in`, height: `${g.paperHeight}in`, padding: `${MARGIN_IN}in` }}
        >
          {page === 0 && (
            <div className="mb-[0.3em] text-center font-bold" style={{ fontSize: `${g.font + 2}pt` }}>
              {props.title}
            </div>
          )}
          <div className="relative overflow-hidden" style={{ width: `${g.contentWidth}in`, height: flowHeight }}>
            <div
              ref={page === 0 ? flowRef : undefined}
              aria-hidden={page > 0 || undefined}
              style={{
                ...flowStyle,
                transform: page ? `translateX(-${page * (g.contentWidth + gapIn)}in)` : undefined,
              }}
            >
              <Flow {...props} />
              {page === 0 && <span ref={endRef} className="inline-block h-0 w-0" />}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
