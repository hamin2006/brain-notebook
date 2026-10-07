import { describe, expect, it } from 'vitest'
import {
  convertReferencesToCompactMarkdown,
  defaultLocatorFormatter,
  parseSourceReferences,
} from './source-references'

describe('parseSourceReferences', () => {
  it('captures agent address locators as part of the reference', () => {
    const refs = parseSourceReferences('Adam [source:l4#p94] and dropout [source:l3#p123-132] see [source:l4/summary]')
    expect(refs.map(r => [r.type, r.id, r.locator])).toEqual([
      ['source', 'l4', '#p94'],
      ['source', 'l3', '#p123-132'],
      ['source', 'l4', '/summary'],
    ])
  })

  it('keeps plain references unchanged', () => {
    const [ref] = parseSourceReferences('see [note:abc]')
    expect(ref).toMatchObject({ type: 'note', id: 'abc', locator: undefined })
  })
})

describe('convertReferencesToCompactMarkdown', () => {
  it('consumes the brackets around page citations', () => {
    const out = convertReferencesToCompactMarkdown('Adam combines momentum and RMSProp [source:l4#p94].')
    expect(out.startsWith('Adam combines momentum and RMSProp [1](#ref-source-l4@p94).')).toBe(true)
    expect(out).toContain('[1] - [source:l4 · p. 94](#ref-source-l4@p94)')
    expect(out).not.toContain('#p94]')
  })

  it('numbers each location separately and reuses numbers for repeats', () => {
    const out = convertReferencesToCompactMarkdown(
      'A [source:l4#p86-94]. B [source:l4#p94]. C [source:l4#p94].',
      'References',
      locator => `PAGE ${locator}`
    )
    expect(out).toContain('A [1](#ref-source-l4@p86-94). B [2](#ref-source-l4@p94). C [2](#ref-source-l4@p94).')
    expect(out).toContain('[1] - [source:l4 · PAGE #p86-94]')
    expect(out).toContain('[2] - [source:l4 · PAGE #p94]')
  })

  it('leaves legacy citations as before', () => {
    expect(convertReferencesToCompactMarkdown('See [source:abc].')).toBe(
      'See [1](#ref-source-abc).\n\nReferences:\n[1] - [source:abc](#ref-source-abc)'
    )
  })
})

describe('defaultLocatorFormatter', () => {
  it.each([
    ['#p12', 'p. 12'],
    ['#p12-18', 'pp. 12–18'],
    ['#p5-5', 'p. 5'],
    ['#s3', '§3'],
    ['#c7', '#7'],
    ['/summary', 'summary'],
  ])('%s -> %s', (locator, label) => {
    expect(defaultLocatorFormatter(locator)).toBe(label)
  })
})
