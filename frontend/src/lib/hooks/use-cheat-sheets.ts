'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cheatSheetsApi, type CheatSheet, type CreateCheatSheetRequest, type SheetStatus } from '@/lib/api/cheat-sheets'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'

export const BUILDING_STATUSES: SheetStatus[] = ['queued', 'extracting', 'composing']

export function isBuilding(status?: SheetStatus | null): boolean {
  return !!status && BUILDING_STATUSES.includes(status)
}

export function useCheatSheets(notebookId: string, enabled = true) {
  return useQuery({
    queryKey: QUERY_KEYS.cheatSheets(notebookId),
    queryFn: () => cheatSheetsApi.list(notebookId),
    enabled: !!notebookId && enabled,
    staleTime: 10_000,
  })
}

export function useCheatSheetSources(notebookId: string, enabled = true) {
  return useQuery({
    queryKey: [...QUERY_KEYS.cheatSheets(notebookId), 'sources'],
    queryFn: () => cheatSheetsApi.sources(notebookId),
    enabled: !!notebookId && enabled,
    staleTime: 30_000,
  })
}

/** A sheet with one version's layout; polls every 2 s while it is being built. */
export function useCheatSheet(id: string, version?: number | null) {
  return useQuery({
    queryKey: QUERY_KEYS.cheatSheet(id, version ?? null),
    queryFn: () => cheatSheetsApi.get(id, version),
    enabled: !!id,
    staleTime: 5_000,
    refetchInterval: (query) => (isBuilding(query.state.data?.status) ? 2000 : false),
  })
}

function useSheetMutation<TVars, TResult>(
  sheetId: string,
  mutationFn: (vars: TVars) => Promise<TResult>,
  failureKey: string,
  onDone?: () => void
) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cheat-sheets'] })
      onDone?.()
    },
    onError: (error: unknown) => {
      toast({ title: t('common.error'), description: getApiErrorKey(error, failureKey), variant: 'destructive' })
    },
  })
}

export function useCreateCheatSheet(notebookId: string) {
  const { t } = useTranslation()
  return useSheetMutation(
    notebookId,
    (data: CreateCheatSheetRequest) => cheatSheetsApi.create(notebookId, data),
    t('cheatSheet.createFailed')
  )
}

/** Review actions on one sheet: everything that changes it goes through here. */
export function useCheatSheetActions(sheetId: string) {
  const { t } = useTranslation()
  const failed = t('cheatSheet.actionFailed')
  return {
    rename: useSheetMutation(sheetId, (title: string) => cheatSheetsApi.rename(sheetId, title), failed),
    remove: useSheetMutation(sheetId, () => cheatSheetsApi.remove(sheetId), failed),
    rebuild: useSheetMutation(sheetId, () => cheatSheetsApi.rebuild(sheetId), failed),
    resize: useSheetMutation(sheetId, (direction: 'shorten' | 'more') => cheatSheetsApi.resize(sheetId, direction), failed),
    revise: useSheetMutation(sheetId, () => cheatSheetsApi.revise(sheetId), failed),
    updateLine: useSheetMutation(
      sheetId,
      ({ lineId, text, pinned }: { lineId: string; text?: string; pinned?: boolean }) =>
        cheatSheetsApi.updateLine(sheetId, lineId, { text, pinned }),
      failed
    ),
    deleteLine: useSheetMutation(sheetId, (lineId: string) => cheatSheetsApi.deleteLine(sheetId, lineId), failed),
    addComment: useSheetMutation(
      sheetId,
      (data: { text: string; line?: string | null }) => cheatSheetsApi.addComment(sheetId, data),
      failed
    ),
    resolveComment: useSheetMutation(
      sheetId,
      ({ commentId, status }: { commentId: string; status: 'open' | 'addressed' }) =>
        cheatSheetsApi.updateComment(sheetId, commentId, { status }),
      failed
    ),
    deleteComment: useSheetMutation(sheetId, (commentId: string) => cheatSheetsApi.deleteComment(sheetId, commentId), failed),
  }
}

export type { CheatSheet }
