'use client'

import { useMemo } from 'react'
import { useQueries } from '@tanstack/react-query'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { useTranslation } from '@/lib/hooks/use-translation'
import { convertReferencesToCompactMarkdown, collectReferences } from '@/lib/utils/source-references'
import { localizedLocator } from '@/components/sources/AgentActivity'
import { sourcesApi } from '@/lib/api/sources'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { CitationChip, CitedSources, parseReferenceHref, type ReferenceClick } from './Citations'

/**
 * Titles for cited sources the caller doesn't already know (e.g. Ask, which
 * spans notebooks), fetched once per source and cached.
 */
function useMissingTitles(ids: string[]) {
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: QUERY_KEYS.source(id),
      queryFn: () => sourcesApi.get(id),
      staleTime: 5 * 60_000,
    })),
  })
  return useMemo(() => {
    const titles: Record<string, string> = {}
    results.forEach((r, i) => {
      if (r.data?.title) titles[`source:${ids[i]}`] = r.data.title
    })
    return titles
  }, [results, ids])
}

/** An answer: prose with numbered citation chips, then the cited pages. */
export function AnswerContent({
  content,
  referenceTitles = {},
  onReferenceClick,
}: {
  content: string
  referenceTitles?: Record<string, string>
  onReferenceClick: ReferenceClick
}) {
  const { t } = useTranslation()
  const markdown = useMemo(
    () => convertReferencesToCompactMarkdown(content, t('common.references'), localizedLocator(t), false),
    [content, t]
  )
  const references = useMemo(() => collectReferences(content), [content])
  const missing = useMemo(
    () => [...new Set(references.filter((r) => r.type === 'source' && !referenceTitles[`source:${r.id}`]).map((r) => r.id))],
    [references, referenceTitles]
  )
  const fetched = useMissingTitles(missing)
  const titles = useMemo(() => ({ ...fetched, ...referenceTitles }), [fetched, referenceTitles])

  const components = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
      const ref = href ? parseReferenceHref(href) : null
      if (ref) {
        return (
          <CitationChip
            number={children}
            type={ref.type}
            id={ref.id}
            locator={ref.locator}
            title={titles[`${ref.type}:${ref.id}`]}
            onClick={onReferenceClick}
          />
        )
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" {...props} className="text-iris underline-offset-2 hover:underline">
          {children}
        </a>
      )
    },
  }), [titles, onReferenceClick])

  return (
    <div className="space-y-5">
      <div className="answer-prose">
        <MarkdownRenderer components={components}>{markdown}</MarkdownRenderer>
      </div>
      <CitedSources references={references} titles={titles} onClick={onReferenceClick} />
    </div>
  )
}
