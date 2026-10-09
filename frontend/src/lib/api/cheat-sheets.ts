import apiClient from './client'

export type RecallKind = 'formula' | 'definition' | 'theorem' | 'method' | 'example' | 'pitfall'
export const RECALL_KINDS: RecallKind[] = ['formula', 'definition', 'theorem', 'method', 'example', 'pitfall']
export const DEFAULT_KINDS: RecallKind[] = ['formula', 'definition', 'theorem', 'method']

export type SheetStatus = 'queued' | 'extracting' | 'composing' | 'done' | 'failed'

export interface SheetOptions {
  pages: number
  columns: number
  kinds: RecallKind[]
  instructions: string
  paper: 'letter' | 'a4'
  scale: number
}

export interface SheetCite {
  source: string
  page_start: number
  page_end: number
}

export interface SheetLine {
  id: string
  text: string
  items: string[]
  kind: RecallKind
  cites: SheetCite[]
  pinned?: boolean
  edited?: boolean
}

export interface SheetTopic {
  id: string
  title: string
  lines: SheetLine[]
}

export interface SheetLayout {
  title: string
  topics: SheetTopic[]
  budget_chars?: number
  chars?: number
}

export interface SheetComment {
  id: string
  version: number
  line?: string | null
  text: string
  status: 'open' | 'addressed'
  note?: string | null
  created: string
}

export interface SheetDetail {
  mode?: 'compose' | 'revise' | 'shorten' | 'more'
  sections_total?: number
  sections_done?: number
  failed_sections?: { source: string; section: number }[]
  items?: number
  seconds?: number
  usage?: { cost: number }
}

export interface CheatSheetSummary {
  id: string
  notebook: string
  title: string
  sources: string[]
  options: SheetOptions
  status: SheetStatus
  error?: string | null
  detail?: SheetDetail | null
  current_version?: number | null
  created: string
  updated: string
}

export interface CheatSheet extends CheatSheetSummary {
  version?: number | null
  layout?: SheetLayout | null
  versions: { number: number; created: string }[]
  comments: SheetComment[]
  source_names: Record<string, string>
}

export interface CreateCheatSheetRequest {
  title?: string
  source_ids?: string[]
  pages: number
  columns: number
  kinds: RecallKind[]
  instructions: string
  paper: 'letter' | 'a4'
}

const sheetPath = (id: string) => `/cheat-sheets/${encodeURIComponent(id)}`

export const cheatSheetsApi = {
  list: async (notebookId: string) =>
    (await apiClient.get<CheatSheetSummary[]>(`/notebooks/${notebookId}/cheat-sheets`)).data,

  sources: async (notebookId: string) =>
    (await apiClient.get<{ id: string; title: string }[]>(`/notebooks/${notebookId}/cheat-sheets/sources`)).data,

  create: async (notebookId: string, data: CreateCheatSheetRequest) =>
    (await apiClient.post<CheatSheetSummary>(`/notebooks/${notebookId}/cheat-sheets`, data)).data,

  get: async (id: string, version?: number | null) =>
    (await apiClient.get<CheatSheet>(sheetPath(id), { params: version ? { version } : {} })).data,

  rename: async (id: string, title: string) =>
    (await apiClient.patch<CheatSheetSummary>(sheetPath(id), { title })).data,

  remove: async (id: string) => {
    await apiClient.delete(sheetPath(id))
  },

  rebuild: async (id: string) => (await apiClient.post<CheatSheetSummary>(`${sheetPath(id)}/rebuild`)).data,

  resize: async (id: string, direction: 'shorten' | 'more') =>
    (await apiClient.post<CheatSheetSummary>(`${sheetPath(id)}/resize`, { direction })).data,

  revise: async (id: string) => (await apiClient.post<CheatSheetSummary>(`${sheetPath(id)}/revise`)).data,

  updateLine: async (id: string, lineId: string, data: { text?: string; pinned?: boolean }) =>
    (await apiClient.patch<SheetLine>(`${sheetPath(id)}/lines/${lineId}`, data)).data,

  deleteLine: async (id: string, lineId: string) => {
    await apiClient.delete(`${sheetPath(id)}/lines/${lineId}`)
  },

  addComment: async (id: string, data: { text: string; line?: string | null }) =>
    (await apiClient.post<SheetComment>(`${sheetPath(id)}/comments`, data)).data,

  updateComment: async (id: string, commentId: string, data: { text?: string; status?: 'open' | 'addressed' }) =>
    (await apiClient.patch<SheetComment>(`${sheetPath(id)}/comments/${encodeURIComponent(commentId)}`, data)).data,

  deleteComment: async (id: string, commentId: string) => {
    await apiClient.delete(`${sheetPath(id)}/comments/${encodeURIComponent(commentId)}`)
  },

  tex: async (id: string, version: number | null | undefined, citations: boolean) =>
    (
      await apiClient.get<Blob>(`${sheetPath(id)}/tex`, {
        params: { ...(version ? { version } : {}), citations },
        responseType: 'blob',
      })
    ).data,
}
