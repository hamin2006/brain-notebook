'use client'

import { useEffect, useRef, useState } from 'react'
import { FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { usePageImage } from '@/lib/hooks/use-explore'

/** A rendered document page; falls back to a quiet placeholder. */
export function PageThumb({
  sourceId,
  page,
  size = 'thumb',
  className,
  imgClassName,
  alt,
  lazy = false,
}: {
  sourceId: string | null | undefined
  page: number | null | undefined
  size?: 'thumb' | 'full'
  className?: string
  imgClassName?: string
  alt?: string
  // Fetch only once scrolled into view (long page grids)
  lazy?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(!lazy)
  useEffect(() => {
    if (visible || !ref.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [visible])
  const { data: url, isLoading, isError } = usePageImage(visible ? sourceId : null, page, size)
  return (
    <div ref={ref} className={cn('relative overflow-hidden bg-surface-recessed', className)}>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- blob URL of a rendered page
        <img
          src={url}
          alt={alt ?? ''}
          className={cn('h-full w-full object-cover object-top animate-fade-up', imgClassName)}
          draggable={false}
        />
      ) : isLoading || !visible ? (
        <div className="absolute inset-0 animate-pulse bg-surface-sunken/60" />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-ink-faint">
          <FileText className={cn('h-5 w-5', isError && 'opacity-50')} />
        </div>
      )}
    </div>
  )
}
