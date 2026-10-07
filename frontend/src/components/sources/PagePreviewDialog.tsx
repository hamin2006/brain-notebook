'use client'

import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { getAuthToken } from '@/lib/auth-token'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface PageTarget {
  sourceId: string // "source:abc" or "abc"
  start: number
  end: number
}

/** "p12-18" -> {start: 12, end: 18}; null for non-page locators. */
export function parsePageLocator(locator?: string): { start: number; end: number } | null {
  const match = locator ? /^p(\d+)(?:-(\d+))?$/.exec(locator) : null
  if (!match) return null
  const start = Number(match[1])
  return { start, end: match[2] ? Math.max(start, Number(match[2])) : start }
}

/** Shows the cited page of a source as an image, with paging through a cited range. */
export function PagePreviewDialog({
  target,
  onClose,
  onOpenSource,
}: {
  target: PageTarget | null
  onClose: () => void
  onOpenSource: (sourceId: string) => void
}) {
  const { t } = useTranslation()
  const [page, setPage] = useState(target?.start ?? 1)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (target) setPage(target.start)
  }, [target])

  useEffect(() => {
    if (!target) return
    let objectUrl: string | null = null
    let cancelled = false
    setImageUrl(null)
    setFailed(false)
    const id = target.sourceId.replace(/^source:/, '')
    const token = getAuthToken()
    fetch(`/api/sources/${id}/pages/${page}/image`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(response => {
        if (!response.ok) throw new Error(String(response.status))
        return response.blob()
      })
      .then(blob => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setImageUrl(objectUrl)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [target, page])

  if (!target) return null
  const inRange = target.end > target.start
  return (
    <Dialog open={!!target} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-4xl">
        <DialogTitle className="text-sm font-medium">{t('chat.pagePreviewTitle', { page })}</DialogTitle>
        <div className="flex min-h-[200px] items-center justify-center rounded-md border bg-muted">
          {failed ? (
            <p className="p-6 text-sm text-muted-foreground">{t('chat.pageImageUnavailable')}</p>
          ) : imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- blob URL of a rendered page
            <img src={imageUrl} alt={t('chat.pagePreviewTitle', { page })} className="max-h-[70vh] w-auto" />
          ) : (
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            {inRange && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('chat.previousPage')}
                  disabled={page <= target.start}
                  onClick={() => setPage(p => p - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-xs text-muted-foreground">
                  {t('chat.citePages', { start: target.start, end: target.end })}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('chat.nextPage')}
                  disabled={page >= target.end}
                  onClick={() => setPage(p => p + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
          <Button variant="outline" size="sm" onClick={() => onOpenSource(target.sourceId)}>
            {t('chat.openSource')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
