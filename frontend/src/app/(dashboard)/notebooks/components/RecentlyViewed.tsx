'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import type { Locale } from 'date-fns/locale'
import { BookOpen, FileText } from 'lucide-react'

import { PageThumb } from '@/components/brain/PageThumb'
import { notebooksApi } from '@/lib/api/notebooks'
import type { RecentlyViewedResponse } from '@/lib/types/api'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getDateLocale } from '@/lib/utils/date-locale'

interface RecentlyViewedProps {
  limit?: number
}

function getItemHref(item: RecentlyViewedResponse) {
  if (item.type === 'notebook') {
    return `/notebooks/${encodeURIComponent(item.id)}`
  }

  return `/sources/${item.id}`
}

function formatViewedAt(value: string, locale: Locale) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return formatDistanceToNow(date, {
    addSuffix: true,
    locale,
  })
}

export function RecentlyViewed({ limit = 10 }: RecentlyViewedProps) {
  const { t, language } = useTranslation()
  const locale = getDateLocale(language)
  const { data: items, isLoading, isError } = useQuery({
    queryKey: ['recently-viewed', limit],
    queryFn: () => notebooksApi.recentlyViewed(limit),
  })

  if (isLoading || isError || !items || items.length === 0) {
    return null
  }

  return (
    <section className="space-y-3">
      <h2 className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
        {t('brain.jumpBackIn')}
      </h2>
      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
        {items.map((item) => {
          const typeLabel =
            item.type === 'notebook'
              ? t('notebooks.recentlyViewedNotebook', { defaultValue: 'Notebook' })
              : t('notebooks.recentlyViewedSource', { defaultValue: 'Source' })

          return (
            <Link
              key={`${item.type}-${item.id}`}
              href={getItemHref(item)}
              className="group card-hover flex w-[248px] shrink-0 items-center gap-3 rounded-xl border bg-card p-2 pr-3 shadow-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {item.type === 'notebook' ? (
                <div className="flex h-11 w-14 shrink-0 items-center justify-center rounded-md bg-surface-recessed text-iris">
                  <BookOpen className="h-4 w-4" />
                </div>
              ) : (
                <PageThumb
                  sourceId={item.id}
                  page={1}
                  className="h-11 w-14 shrink-0 rounded-md border"
                />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{item.title}</p>
                <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-muted-foreground">
                  {item.type === 'notebook' ? <BookOpen className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                  {typeLabel} · {formatViewedAt(item.last_viewed_at, locale)}
                </p>
              </div>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
