import apiClient from './client'

export type IngestionStage = 'extract' | 'caption' | 'embed' | 'analyze' | 'page_images' | 'concepts'
export type StageStatusName = 'pending' | 'queued' | 'running' | 'done' | 'skipped' | 'failed'

export interface StageStatus {
  stage: IngestionStage
  status: StageStatusName
  version?: number | null
  current_version: number
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  seconds?: number | null
  error?: string | null
  detail?: Record<string, unknown> | null
}

export interface SourceIngestion {
  source_id: string
  title?: string | null
  complete: boolean
  failed: boolean
  current_stage?: IngestionStage | null
  stages: StageStatus[]
}

export interface NotebookIngestion {
  complete: boolean
  sources: number
  sources_complete: number
  sources_failed: number
  active: Partial<Record<IngestionStage, number>>
  items: SourceIngestion[]
}

export const ingestionApi = {
  notebook: async (notebookId: string) =>
    (await apiClient.get<NotebookIngestion>(`/notebooks/${notebookId}/ingestion`)).data,
  source: async (sourceId: string) =>
    (await apiClient.get<SourceIngestion>(`/sources/${sourceId}/ingestion`)).data,
  retry: async (sourceId: string) =>
    (await apiClient.post<SourceIngestion>(`/sources/${sourceId}/ingestion/retry`)).data,
}
