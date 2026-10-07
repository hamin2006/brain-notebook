'use client'

import { useQuery } from '@tanstack/react-query'
import { exploreApi } from '@/lib/api/explore'

export function useNotebookOverview(notebookId: string, limit = 24) {
  return useQuery({
    queryKey: ['explore', 'overview', notebookId, limit],
    queryFn: () => exploreApi.overview(notebookId, limit),
    enabled: !!notebookId,
    staleTime: 60_000,
  })
}

export function useConcept(notebookId: string, conceptId: string | null) {
  return useQuery({
    queryKey: ['explore', 'concept', notebookId, conceptId],
    queryFn: () => exploreApi.concept(notebookId, conceptId as string),
    enabled: !!notebookId && !!conceptId,
    staleTime: 60_000,
  })
}

export function useConceptGraph(notebookId: string, enabled = true) {
  return useQuery({
    queryKey: ['explore', 'graph', notebookId],
    queryFn: () => exploreApi.graph(notebookId),
    enabled: !!notebookId && enabled,
    staleTime: 5 * 60_000,
  })
}

export function useSourceStructure(sourceId: string | null) {
  return useQuery({
    queryKey: ['explore', 'structure', sourceId],
    queryFn: () => exploreApi.structure(sourceId as string),
    enabled: !!sourceId,
    staleTime: 60_000,
  })
}

/**
 * A page image as an object URL. Cached for the session (pages don't change),
 * so a thumbnail shown in a citation, a card and the viewer is fetched once.
 */
export function usePageImage(sourceId: string | null | undefined, page: number | null | undefined, size: 'thumb' | 'full' = 'thumb') {
  return useQuery({
    queryKey: ['page-image', sourceId?.replace(/^source:/, ''), page, size],
    queryFn: () => exploreApi.pageImage(sourceId as string, page as number, size),
    enabled: !!sourceId && !!page && page > 0,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: false,
  })
}
