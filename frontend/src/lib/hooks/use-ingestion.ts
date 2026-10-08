'use client'

import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ingestionApi } from '@/lib/api/ingestion'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import { useToast } from '@/lib/hooks/use-toast'

const POLL_MS = 4000

// Keys live under ['sources', ...] so the broad source invalidation after an
// upload, delete or retry refetches them too.
export const ingestionKeys = {
  notebook: (id: string) => ['sources', 'ingestion', 'notebook', id] as const,
  source: (id: string) => ['sources', 'ingestion', 'source', id] as const,
}

/** A notebook's ingestion progress; polls while any source is unfinished. */
export function useNotebookIngestion(notebookId: string) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ingestionKeys.notebook(notebookId),
    queryFn: () => ingestionApi.notebook(notebookId),
    enabled: !!notebookId,
    refetchInterval: (q) => (q.state.data && q.state.data.complete ? false : POLL_MS),
  })
  // When ingestion finishes, what it built (outline, concepts, graph) changed.
  const wasComplete = useRef<boolean | null>(null)
  const complete = query.data?.complete
  useEffect(() => {
    if (complete === undefined) return
    if (wasComplete.current === false && complete) {
      queryClient.invalidateQueries({ queryKey: ['explore'] })
    }
    wasComplete.current = complete
  }, [complete, queryClient])
  return query
}

/** One source's stages; polls while it is unfinished. */
export function useSourceIngestion(sourceId: string | null) {
  return useQuery({
    queryKey: ingestionKeys.source(sourceId ?? ''),
    queryFn: () => ingestionApi.source(sourceId as string),
    enabled: !!sourceId,
    refetchInterval: (q) => (q.state.data && q.state.data.complete && !q.state.data.failed ? false : POLL_MS),
  })
}

/** Re-run a source from its failed (or outdated) stage. */
export function useRetryIngestion() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sourceId: string) => ingestionApi.retry(sourceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sources', 'ingestion'] }),
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorMessage(error, (key) => t(key)),
        variant: 'destructive',
      })
    },
  })
}
