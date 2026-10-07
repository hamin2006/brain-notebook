import { describe, expect, it } from 'vitest'
import { parsePageLocator } from './PagePreviewDialog'

describe('parsePageLocator', () => {
  it.each([
    ['p94', { start: 94, end: 94 }],
    ['p86-94', { start: 86, end: 94 }],
    ['p9-3', { start: 9, end: 9 }],
  ])('%s', (locator, expected) => {
    expect(parsePageLocator(locator)).toEqual(expected)
  })

  it('ignores non-page locators', () => {
    expect(parsePageLocator('s3')).toBeNull()
    expect(parsePageLocator('summary')).toBeNull()
    expect(parsePageLocator(undefined)).toBeNull()
  })
})
