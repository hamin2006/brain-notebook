import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FileViewer, formatBytes } from './FileViewer'
import { exploreApi, type FilePreview } from '@/lib/api/explore'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/api/explore', () => ({
  exploreApi: {
    preview: vi.fn(),
    file: vi.fn(),
    pageImage: vi.fn().mockResolvedValue('blob:page'),
  },
}))

vi.mock('@/components/ui/markdown-renderer', () => ({
  MarkdownRenderer: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
}))

const base = { filename: 'f', media_type: 'x', size: 2048 }

function show(preview: Partial<FilePreview>, onDownload?: () => void) {
  vi.mocked(exploreApi.preview).mockResolvedValue({ ...base, kind: 'none', ...preview } as FilePreview)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <FileViewer sourceId="source:abc" onDownload={onDownload} />
    </QueryClientProvider>
  )
}

describe('FileViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    globalThis.IntersectionObserver = class {
      observe() {}
      disconnect() {}
    } as unknown as typeof IntersectionObserver
  })

  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(25 * 1024 * 1024)).toBe('25 MB')
  })

  it('lists pages in batches', async () => {
    show({ kind: 'pages', pages: 45 })
    expect(await screen.findAllByRole('figure')).toHaveLength(30)
    fireEvent.click(screen.getByText('brain.fileMorePages'))
    expect(screen.getAllByRole('figure')).toHaveLength(45)
    expect(screen.queryByText('brain.fileMorePages')).toBeNull()
  })

  it('shows text as is and says when it was cut short', async () => {
    show({ kind: 'text', text: 'line one\nline two', truncated: true })
    expect(await screen.findByText(/line one/)).toBeTruthy()
    expect(screen.getByText('brain.fileTruncated')).toBeTruthy()
  })

  it('renders Markdown', async () => {
    show({ kind: 'markdown', text: '# Title' })
    expect((await screen.findByTestId('markdown')).textContent).toBe('# Title')
  })

  it('puts HTML and documents in a sandbox without scripts', async () => {
    const { container } = show({ kind: 'html', text: '<p>hi</p>' })
    await waitFor(() => expect(container.querySelector('iframe')).not.toBeNull())
    const frame = container.querySelector('iframe') as HTMLIFrameElement
    expect(frame.getAttribute('sandbox')).toBe('')
    expect(frame.getAttribute('srcdoc')).toBe('<p>hi</p>')
  })

  it('switches sheets and reports hidden rows', async () => {
    show({
      kind: 'table',
      sheets: [
        { name: 'One', rows: [['a', 'b']], total_rows: 1, truncated: false },
        { name: 'Two', rows: [['c']], total_rows: 900, truncated: true },
      ],
    })
    expect(await screen.findByText('a')).toBeTruthy()
    fireEvent.click(screen.getByText('Two'))
    expect(screen.getByText('c')).toBeTruthy()
    expect(screen.getByText('brain.fileRowsShown')).toBeTruthy()
  })

  it('lists archive entries', async () => {
    show({ kind: 'archive', entries: [{ name: 'slides/a.pdf', size: 10, dir: false }], truncated: false })
    expect(await screen.findByText('slides/a.pdf')).toBeTruthy()
  })

  it('plays media from the downloaded bytes', async () => {
    vi.mocked(exploreApi.file).mockResolvedValue(new Blob(['x']))
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:media')
    globalThis.URL.revokeObjectURL = vi.fn()
    const { container } = show({ kind: 'audio' })
    await waitFor(() => expect(container.querySelector('audio')?.getAttribute('src')).toBe('blob:media'))
    expect(exploreApi.file).toHaveBeenCalledWith('source:abc')
  })

  it('offers the download when there is no preview', async () => {
    const onDownload = vi.fn()
    show({ kind: 'none' }, onDownload)
    expect(await screen.findByText('brain.fileNoPreview')).toBeTruthy()
    fireEvent.click(screen.getAllByText('common.download')[1])
    expect(onDownload).toHaveBeenCalled()
  })

  it('says so when the preview fails', async () => {
    vi.mocked(exploreApi.preview).mockRejectedValue(new Error('500'))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <FileViewer sourceId="source:abc" />
      </QueryClientProvider>
    )
    expect(await screen.findByText('brain.filePreviewFailed')).toBeTruthy()
  })
})
