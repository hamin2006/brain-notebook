import { describe, it, expect } from 'vitest'
import { addressLocator, firstPage, parseReferenceHref } from './Citations'
import { traceStats } from './ResearchTimeline'
import { collectReferences, convertReferencesToCompactMarkdown } from '@/lib/utils/source-references'

describe('citations', () => {
  it('numbers distinct references in citation order, like the compact markdown', () => {
    const text = 'A [source:abc#p12-18]. B [note:n1]. Again [source:abc#p12-18], then [source:abc#p3].'
    const refs = collectReferences(text)
    expect(refs.map((r) => [r.number, r.type, r.id, r.locator])).toEqual([
      [1, 'source', 'abc', '#p12-18'],
      [2, 'note', 'n1', undefined],
      [3, 'source', 'abc', '#p3'],
    ])
    const markdown = convertReferencesToCompactMarkdown(text, 'References', undefined, false)
    expect(markdown).toContain('[3](#ref-source-abc@p3)')
    expect(markdown).not.toContain('References:')
  })

  it('parses reference hrefs and restores address locators', () => {
    expect(parseReferenceHref('#ref-source-abc@p12-18')).toEqual({ type: 'source', id: 'abc', locator: 'p12-18' })
    expect(parseReferenceHref('https://example.com')).toBeNull()
    expect(addressLocator('p12-18')).toBe('#p12-18')
    expect(addressLocator('s3')).toBe('#s3')
    expect(addressLocator('summary')).toBe('/summary')
    expect(firstPage('p12-18')).toBe(12)
    expect(firstPage('#p7')).toBe(7)
    expect(firstPage('s3')).toBeNull()
  })
})

describe('traceStats', () => {
  it('counts steps, distinct documents and page views', () => {
    const stats = traceStats([
      { tool: 'search', args: { query: 'adam' } },
      { tool: 'read', args: { address: 'source:a#p3-4' } },
      { tool: 'view', args: { address: 'source:b#p9' } },
      { tool: 'grep', args: { pattern: 'x', addresses: ['source:a', 'source:c'] } },
    ])
    expect(stats).toEqual({ steps: 4, documents: 3, pagesViewed: 1 })
  })
})
