import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentApi } from '@/lib/api/agent'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { AgentSettings } from '@/lib/types/api'

function useErrorToast() {
  const { toast } = useToast()
  const { t } = useTranslation()
  return (error: unknown) =>
    toast({
      title: t('common.error'),
      description: getApiErrorMessage(error, (key) => t(key), 'common.error'),
      variant: 'destructive',
    })
}

export function useAgentSettings() {
  return useQuery({ queryKey: QUERY_KEYS.agentSettings, queryFn: () => agentApi.getSettings() })
}

export function useUpdateAgentSettings() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (data: Partial<AgentSettings>) => agentApi.updateSettings(data),
    onSuccess: (settings) => {
      queryClient.setQueryData(QUERY_KEYS.agentSettings, settings)
      toast({ title: t('common.success'), description: t('common.saveSuccess') })
    },
    onError,
  })
}

export function useAgentMemories() {
  return useQuery({ queryKey: QUERY_KEYS.agentMemories, queryFn: () => agentApi.listMemories() })
}

export function useDeleteAgentMemory() {
  const queryClient = useQueryClient()
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (id: string) => agentApi.deleteMemory(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.agentMemories }),
    onError,
  })
}

export function useRebuildAgentData() {
  const { toast } = useToast()
  const { t } = useTranslation()
  const onError = useErrorToast()
  return useMutation({
    mutationFn: (what: 'page_embeddings' | 'concepts') => agentApi.rebuild(what),
    onSuccess: (result) =>
      toast({ title: t('common.success'), description: t('settings.rebuildSubmitted', { count: result.submitted }) }),
    onError,
  })
}
