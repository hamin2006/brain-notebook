'use client'

import { useEffect, useState } from 'react'
import { Download, FileQuestion, Folder, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import { PageThumb } from '@/components/brain/PageThumb'
import { exploreApi, type FilePreview, type PreviewSheet } from '@/lib/api/explore'
import { useFilePreview } from '@/lib/hooks/use-explore'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

const PAGES_PER_BATCH = 30

/** "2.4 MB" */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`
}

/**
 * The source's original file, shown the way its type allows: pages, image,
 * player, text, table, document text or archive listing (`kind` from the API).
 */
export function FileViewer({ sourceId, onDownload }: { sourceId: string; onDownload?: () => void }) {
  const { t } = useTranslation()
  const { data: preview, isLoading, isError } = useFilePreview(sourceId)

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }
  if (isError || !preview) {
    return <Unavailable message={t('brain.filePreviewFailed')} onDownload={onDownload} />
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span className="min-w-0 truncate" title={preview.filename}>
          {preview.filename} · {formatBytes(preview.size)}
        </span>
        {onDownload && (
          <Button variant="ghost" size="sm" className="h-7 shrink-0 gap-1.5 text-xs" onClick={onDownload}>
            <Download className="h-3.5 w-3.5" />
            {t('common.download')}
          </Button>
        )}
      </div>
      <PreviewBody sourceId={sourceId} preview={preview} onDownload={onDownload} />
    </div>
  )
}

function PreviewBody({
  sourceId,
  preview,
  onDownload,
}: {
  sourceId: string
  preview: FilePreview
  onDownload?: () => void
}) {
  const { t } = useTranslation()
  switch (preview.kind) {
    case 'pages':
      return <PagesView sourceId={sourceId} pages={preview.pages ?? 0} />
    case 'image':
      return (
        <PageThumb
          sourceId={sourceId}
          page={1}
          size="full"
          alt={preview.filename}
          className="min-h-48 w-full rounded-md border"
          imgClassName="h-auto object-contain"
        />
      )
    case 'audio':
    case 'video':
      return <MediaView sourceId={sourceId} kind={preview.kind} />
    case 'text':
      return (
        <>
          <pre className="whitespace-pre-wrap break-words rounded-md border bg-surface-recessed p-4 font-mono text-xs leading-relaxed">
            {preview.text}
          </pre>
          {preview.truncated && <Note>{t('brain.fileTruncated')}</Note>}
        </>
      )
    case 'markdown':
      return (
        <>
          <MarkdownRenderer>{preview.text ?? ''}</MarkdownRenderer>
          {preview.truncated && <Note>{t('brain.fileTruncated')}</Note>}
        </>
      )
    case 'html':
    case 'document':
      return (
        <>
          {preview.kind === 'document' && <Note>{t('brain.fileTextOnly')}</Note>}
          {/* Empty sandbox: no scripts, no same-origin access to the app */}
          <iframe
            sandbox=""
            srcDoc={preview.kind === 'html' ? preview.text : preview.html}
            title={preview.filename}
            className="h-[70vh] w-full rounded-md border bg-white"
          />
        </>
      )
    case 'table':
      return <TableView sheets={preview.sheets ?? []} />
    case 'archive':
      return (
        <>
          <ul className="divide-y rounded-md border text-xs">
            {(preview.entries ?? []).map((entry) => (
              <li key={entry.name} className="flex items-center gap-2 px-3 py-1.5">
                {entry.dir && <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                <span className="min-w-0 flex-1 truncate font-mono">{entry.name}</span>
                {!entry.dir && <span className="shrink-0 text-muted-foreground">{formatBytes(entry.size)}</span>}
              </li>
            ))}
          </ul>
          {preview.truncated && <Note>{t('brain.fileEntriesTruncated', { count: preview.entries?.length ?? 0 })}</Note>}
        </>
      )
    default:
      return <Unavailable message={t('brain.fileNoPreview')} onDownload={onDownload} />
  }
}

/** Every page of a PDF, loaded as it scrolls into view, a batch at a time. */
function PagesView({ sourceId, pages }: { sourceId: string; pages: number }) {
  const { t } = useTranslation()
  const [shown, setShown] = useState(PAGES_PER_BATCH)
  const visible = Math.min(shown, pages)
  return (
    <div className="space-y-4">
      {Array.from({ length: visible }, (_, i) => i + 1).map((page) => (
        <figure key={page} className="space-y-1">
          <PageThumb
            sourceId={sourceId}
            page={page}
            size="full"
            lazy
            alt={t('chat.pagePreviewTitle', { page })}
            className="min-h-48 w-full rounded-md border"
            imgClassName="h-auto object-contain"
          />
          <figcaption className="text-center text-[11px] text-muted-foreground">
            {t('chat.citePage', { page })}
          </figcaption>
        </figure>
      ))}
      {visible < pages && (
        <div className="flex justify-center">
          <Button variant="outline" size="sm" onClick={() => setShown((n) => n + PAGES_PER_BATCH)}>
            {t('brain.fileMorePages', { shown: visible, total: pages })}
          </Button>
        </div>
      )}
    </div>
  )
}

/** Audio and video play from the downloaded bytes (requests need the auth header). */
function MediaView({ sourceId, kind }: { sourceId: string; kind: 'audio' | 'video' }) {
  const { t } = useTranslation()
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    setUrl(null)
    setFailed(false)
    exploreApi
      .file(sourceId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [sourceId])
  if (failed) return <Unavailable message={t('brain.filePreviewFailed')} />
  if (!url) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }
  return kind === 'audio' ? (
    <audio controls src={url} className="w-full" />
  ) : (
    <video controls src={url} className="max-h-[70vh] w-full rounded-md border bg-black" />
  )
}

function TableView({ sheets }: { sheets: PreviewSheet[] }) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const sheet = sheets[Math.min(index, sheets.length - 1)]
  if (!sheet) return <Unavailable message={t('brain.fileNoPreview')} />
  return (
    <div className="space-y-2">
      {sheets.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {sheets.map((s, i) => (
            <Button
              key={`${s.name}-${i}`}
              variant={i === index ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setIndex(i)}
            >
              {s.name}
            </Button>
          ))}
        </div>
      )}
      <div className="max-h-[70vh] overflow-auto rounded-md border">
        <table className="w-full border-collapse text-xs">
          <tbody>
            {sheet.rows.map((row, r) => (
              <tr key={r} className={cn(r === 0 && 'bg-surface-recessed font-medium')}>
                {row.map((cell, c) => (
                  <td key={c} className="whitespace-nowrap border-b border-r px-2 py-1 align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sheet.truncated && (
        <Note>{t('brain.fileRowsShown', { shown: sheet.rows.length, total: sheet.total_rows })}</Note>
      )}
    </div>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>
}

function Unavailable({ message, onDownload }: { message: string; onDownload?: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed px-6 py-10 text-center">
      <FileQuestion className="h-6 w-6 text-muted-foreground" />
      <p className="max-w-sm text-sm text-muted-foreground">{message}</p>
      {onDownload && (
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onDownload}>
          <Download className="h-3.5 w-3.5" />
          {t('common.download')}
        </Button>
      )}
    </div>
  )
}
