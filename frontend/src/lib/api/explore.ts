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

export interface GraphDocument {
  id: string
  title: string
  sequence?: number | null
}

export interface GraphNode {
  id: string
  name: string
  mentions: number
  documents: string[]
  home: string
}

export interface GraphEdge {
  source: string
  target: string
  kind: 'relation' | 'co'
  label?: string | null
  weight: number
}

export interface ConceptGraphData {
  documents: GraphDocument[]
  nodes: GraphNode[]
  edges: GraphEdge[]
  total_concepts: number
}

export type FilePreviewKind =
  | 'pages'
  | 'image'
  | 'audio'
  | 'video'
  | 'text'
  | 'markdown'
  | 'html'
  | 'table'
  | 'document'
  | 'archive'
  | 'none'

export interface PreviewSheet {
  name: string
  rows: string[][]
  total_rows: number
  truncated: boolean
}

export interface ArchiveEntry {
  name: string
  size: number
  dir: boolean
}

/** How the file viewer shows a source's original file (`/sources/{id}/preview`). */
export interface FilePreview {
  kind: FilePreviewKind
  filename: string
  media_type: string
  size: number
  pages?: number
  text?: string
  truncated?: boolean
  sheets?: PreviewSheet[]
  html?: string
  entries?: ArchiveEntry[]
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

  graph: async (notebookId: string, limit = 400) => {
    const response = await apiClient.get<ConceptGraphData>(`/notebooks/${enc(notebookId)}/graph`, {
      params: { limit },
    })
    return response.data
  },

  structure: async (sourceId: string) => {
    const response = await apiClient.get<SourceStructure>(`/sources/${enc(sourceId)}/structure`)
    return response.data
  },

  preview: async (sourceId: string) => {
    const id = sourceId.replace(/^source:/, '')
    const response = await apiClient.get<FilePreview>(`/sources/${enc(id)}/preview`)
    return response.data
  },

  /** The original file's bytes (players need them; auth header included). */
  file: async (sourceId: string) => {
    const id = sourceId.replace(/^source:/, '')
    const response = await apiClient.get<Blob>(`/sources/${enc(id)}/file`, { responseType: 'blob' })
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
