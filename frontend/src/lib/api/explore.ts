import apiClient from './client'

export interface ConceptSummary {
  id: string
  name: string
  documents: number
  mentions: number
}

export interface NotebookOverview {
  documents: number
  pages: number
  sections: number
  notes: number
  concepts: number
  top_concepts: ConceptSummary[]
}

export interface ConceptMention {
  source_id: string
  source_title: string
  page_start?: number | null
  page_end?: number | null
  context?: string | null
}

export interface ConceptRelation {
  concept_id: string
  name: string
  relation: string
  outgoing: boolean
  source_id: string
  page_start?: number | null
  page_end?: number | null
}

export interface ConceptDetail {
  id: string
  name: string
  mentions: ConceptMention[]
  relations: ConceptRelation[]
}

export interface SourceSection {
  index: number
  title: string
  page_start?: number | null
  page_end?: number | null
  summary?: string | null
}

export interface SourceStructure {
  id: string
  metadata: Record<string, unknown>
  page_count: number
  summary?: string | null
  sections: SourceSection[]
  concepts: ConceptSummary[]
}

const enc = encodeURIComponent

/** What ingestion built: counts, the concept graph and document structure. */
export const exploreApi = {
  overview: async (notebookId: string, limit = 24) => {
    const response = await apiClient.get<NotebookOverview>(`/notebooks/${enc(notebookId)}/overview`, {
      params: { limit },
    })
    return response.data
  },

  concept: async (notebookId: string, conceptId: string) => {
    const response = await apiClient.get<ConceptDetail>(
      `/notebooks/${enc(notebookId)}/concepts/${enc(conceptId)}`
    )
    return response.data
  },

  structure: async (sourceId: string) => {
    const response = await apiClient.get<SourceStructure>(`/sources/${enc(sourceId)}/structure`)
    return response.data
  },

  /** A rendered page as an object URL (auth header included). */
  pageImage: async (sourceId: string, page: number, size: 'thumb' | 'full') => {
    const id = sourceId.replace(/^source:/, '')
    const response = await apiClient.get<Blob>(`/sources/${enc(id)}/pages/${page}/image`, {
      params: size === 'thumb' ? { max_side: 480, format: 'jpeg' } : { max_side: 1600 },
      responseType: 'blob',
    })
    return URL.createObjectURL(response.data)
  },
}
