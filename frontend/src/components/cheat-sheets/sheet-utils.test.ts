import { describe, expect, it } from 'vitest'
import { citeLabel, fontPt, kindLabel, pageGeometry, sheetHref, shortSourceLabel } from './sheet-utils'

describe('cheat sheet helpers', () => {
  it('shortens document names for citation marks', () => {
    expect(shortSourceLabel('MATH 138 Lecture 45 - Ch5 Ratio Test.pdf')).toBe('L45')
    expect(shortSourceLabel('Week 03 notes')).toBe('W3')
    expect(shortSourceLabel('Chapter 7 Series')).toBe('Ch7')
    expect(shortSourceLabel('Attention Is All You Need.pdf')).toBe('Attention Is')
    expect(shortSourceLabel(undefined)).toBe('?')
  })

  it('labels a citation with its pages', () => {
    const names = { 'source:a': 'Lecture 5' }
    expect(citeLabel({ source: 'source:a', page_start: 3, page_end: 3 }, names)).toBe('L5·3')
    expect(citeLabel({ source: 'source:a', page_start: 3, page_end: 6 }, names)).toBe('L5·3–6')
  })

  it('matches the backend type size and paper geometry', () => {
    expect([fontPt(2), fontPt(3), fontPt(4)]).toEqual([8, 7, 6])
    const letter = pageGeometry({ paper: 'letter', columns: 3 })
    expect(letter.contentWidth).toBeCloseTo(7.8)
    expect(pageGeometry({ paper: 'a4', columns: 4 }).paperHeight).toBe(11.69)
  })

  it('builds links and kind labels', () => {
    expect(sheetHref('notebook:n1', 'cheat_sheet:s1')).toBe('/notebooks/notebook%3An1/cheat-sheets/cheat_sheet%3As1')
    expect(kindLabel('method', (k) => k)).toBe('cheatSheet.kindMethod')
  })
})
