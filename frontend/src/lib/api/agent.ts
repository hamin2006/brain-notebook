import apiClient from './client'
import { AgentMemory, AgentSettings, RebuildAgentDataResponse } from '@/lib/types/api'

export const agentApi = {
  getSettings: async () => {
    const response = await apiClient.get<AgentSettings>('/agent/settings')
    return response.data
  },

  updateSettings: async (data: Partial<AgentSettings>) => {
    const response = await apiClient.put<AgentSettings>('/agent/settings', data)
    return response.data
  },

  listMemories: async () => {
    const response = await apiClient.get<AgentMemory[]>('/agent/memories')
    return response.data
  },

  deleteMemory: async (id: string) => {
    await apiClient.delete(`/agent/memories/${encodeURIComponent(id)}`)
  },

  rebuild: async (what: 'page_embeddings' | 'concepts') => {
    const response = await apiClient.post<RebuildAgentDataResponse>('/agent/rebuild', { what })
    return response.data
  },
}
