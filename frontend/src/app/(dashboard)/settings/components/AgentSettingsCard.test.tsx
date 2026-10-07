import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsCard } from './AgentSettingsCard'

const update = vi.fn()
const rebuild = vi.fn()
const forget = vi.fn()

vi.mock('@/lib/hooks/use-agent', () => ({
  useAgentSettings: () => ({
    data: {
      rerank_model: 'voyageai/rerank-3-lite',
      page_embedding_model: '',
      knowledge_graph: true,
      memory: true,
      web_search: false,
    },
    isLoading: false,
  }),
  useAgentMemories: () => ({
    data: [
      { id: 'memory:a', content: 'Final exam is on Dec 10', notebook_id: 'notebook:x', created: '' },
      { id: 'memory:b', content: 'Prefers short answers', notebook_id: null, created: '' },
    ],
  }),
  useUpdateAgentSettings: () => ({ mutate: update, isPending: false }),
  useRebuildAgentData: () => ({ mutate: rebuild, isPending: false }),
  useDeleteAgentMemory: () => ({ mutate: forget, isPending: false }),
}))

describe('AgentSettingsCard', () => {
  beforeEach(() => vi.clearAllMocks())

  it('saves an edited model id, trimmed', () => {
    render(<AgentSettingsCard />)
    fireEvent.change(screen.getByLabelText('settings.rerankModel'), { target: { value: ' cohere/rerank-v3.5 ' } })
    fireEvent.click(screen.getAllByText('common.save')[0])
    expect(update).toHaveBeenCalledWith({ rerank_model: 'cohere/rerank-v3.5' })
  })

  it('toggles features and disables page backfill when the model is empty', () => {
    render(<AgentSettingsCard />)
    fireEvent.click(screen.getByLabelText('settings.agentMemory'))
    expect(update).toHaveBeenCalledWith({ memory: false })
    fireEvent.click(screen.getByLabelText('settings.webSearch'))
    expect(update).toHaveBeenCalledWith({ web_search: true })
    expect((screen.getByText('settings.rebuildPageEmbeddings') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByText('settings.rebuildConcepts'))
    expect(rebuild).toHaveBeenCalledWith('concepts')
  })

  it('lists memories and forgets one', () => {
    render(<AgentSettingsCard />)
    expect(screen.getByText('Final exam is on Dec 10')).toBeTruthy()
    expect(screen.getByText('(settings.memoryEverywhere)')).toBeTruthy()
    fireEvent.click(screen.getAllByLabelText('settings.forgetMemory')[1])
    expect(forget).toHaveBeenCalledWith('memory:b')
  })
})
