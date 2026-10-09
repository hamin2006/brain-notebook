import { describe, expect, it } from 'vitest'
import { applyAgentEvent, type AgentActivity } from '@/lib/hooks/use-notebook-chat'
import { describeStep, localizedLocator, withoutRecordIds } from './AgentActivity'

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key

describe('applyAgentEvent', () => {
  it('tracks steps, their results and the text being written', () => {
    let activity: AgentActivity = { steps: [], text: '' }
    activity = applyAgentEvent(activity, { type: 'text_delta', step: 1, text: 'Let me check' })
    activity = applyAgentEvent(activity, { type: 'step', step: 1, tool: 'search', args: { query: 'adam' } })
    expect(activity.text).toBe('') // thinking aloud before a tool call is dropped
    activity = applyAgentEvent(activity, { type: 'step', step: 1, tool: 'grep', args: { pattern: 'rmsprop' } })
    activity = applyAgentEvent(activity, { type: 'step_result', step: 1, tool: 'grep', summary: '2 matches' })
    activity = applyAgentEvent(activity, { type: 'text_delta', step: 2, text: 'Adam ' })
    activity = applyAgentEvent(activity, { type: 'text_delta', step: 2, text: 'combines…' })
    expect(activity.steps.map(s => [s.tool, s.summary])).toEqual([['search', undefined], ['grep', '2 matches']])
    expect(activity.text).toBe('Adam combines…')
  })

  it('ignores a result for an unknown step', () => {
    const activity = { steps: [], text: '' }
    expect(applyAgentEvent(activity, { type: 'step_result', step: 9, tool: 'read', summary: 'x' })).toBe(activity)
  })
})

describe('describeStep', () => {
  it('names the tool and its main argument', () => {
    expect(describeStep('search', { query: 'adam optimizer', level: 'passage' }, t)).toBe('chat.agentToolSearch “adam optimizer”')
    expect(describeStep('list', { sequence: 4 }, t)).toBe('chat.agentToolList “#4”')
    expect(describeStep('list', {}, t)).toBe('chat.agentToolList')
    expect(describeStep('mystery', {}, t)).toBe('mystery')
  })

  it('prefers the readable subject the server sends', () => {
    expect(describeStep('read', { address: 'source:kwj1#p73-81' }, t, 'Lecture 6.pdf pp. 73–81')).toBe(
      'chat.agentToolRead “Lecture 6.pdf pp. 73–81”'
    )
  })

  it('never shows a record id, even without a readable subject', () => {
    expect(describeStep('view', { address: 'source:kwj1#p76' }, t)).not.toContain('source:')
    expect(withoutRecordIds('Showing source:kwj1#p76. The image follows', t)).toBe(
      'Showing brain.traceDocument chat.citePage:{"page":"76"}. The image follows'
    )
    expect(withoutRecordIds('[note:n1] and source:x/summary', t)).toBe(
      '[brain.traceDocument] and brain.traceDocument chat.citeSummary'
    )
    expect(withoutRecordIds('41 match(es) for /residual/', t)).toBe('41 match(es) for /residual/')
  })
})

describe('localizedLocator', () => {
  it('formats page and section locators through translations', () => {
    const format = localizedLocator(t)
    expect(format('#p94')).toBe('chat.citePage:{"page":"94"}')
    expect(format('#p86-94')).toBe('chat.citePages:{"start":"86","end":"94"}')
    expect(format('#s3')).toBe('chat.citeSection:{"index":"3"}')
    expect(format('/summary')).toBe('chat.citeSummary')
  })
})
