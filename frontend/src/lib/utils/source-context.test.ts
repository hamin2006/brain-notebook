import { describe, it, expect } from 'vitest'
import { applyBulkContext, bulkMode, computeSelections } from './source-context'

const item = (id: string) => ({ id })

describe('bulkMode', () => {
  it('include means full, exclude means off', () => {
    expect(bulkMode('include')).toBe('full')
    expect(bulkMode('exclude')).toBe('off')
  })
})

describe('computeSelections', () => {
  it('defaults new items to included', () => {
    expect(computeSelections({}, [item('s:1'), item('s:2')], 'include')).toEqual({
      's:1': 'full',
      's:2': 'full',
    })
  })

  it('defaults new items to off when the default is exclude', () => {
    expect(computeSelections({}, [item('s:1')], 'exclude')).toEqual({ 's:1': 'off' })
  })

  it('preserves existing explicit selections', () => {
    expect(computeSelections({ 's:1': 'off' }, [item('s:1'), item('s:2')], 'include')).toEqual({
      's:1': 'off',
      's:2': 'full',
    })
  })

  it('keeps later-loaded items excluded after an exclude-all (regression for #915)', () => {
    let selections = applyBulkContext({}, [item('s:1'), item('s:2')], 'exclude')
    expect(selections).toEqual({ 's:1': 'off', 's:2': 'off' })

    selections = computeSelections(
      selections,
      [item('s:1'), item('s:2'), item('s:3'), item('s:4')],
      'exclude',
    )
    expect(selections).toEqual({ 's:1': 'off', 's:2': 'off', 's:3': 'off', 's:4': 'off' })
  })
})

describe('applyBulkContext', () => {
  it('bulk includes/excludes every item', () => {
    expect(applyBulkContext({ 's:1': 'off' }, [item('s:1'), item('s:2')], 'include')).toEqual({
      's:1': 'full',
      's:2': 'full',
    })
    expect(applyBulkContext({ 's:1': 'full' }, [item('s:1')], 'exclude')).toEqual({ 's:1': 'off' })
  })
})
