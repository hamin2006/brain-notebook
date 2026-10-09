import type { RecallKind, SheetCite, SheetOptions } from '@/lib/api/cheat-sheets'

type T = (key: string, options?: Record<string, unknown>) => string

export function sheetHref(notebookId: string, sheetId: string): string {
  return `/notebooks/${encodeURIComponent(notebookId)}/cheat-sheets/${encodeURIComponent(sheetId)}`
}

export function kindLabel(kind: RecallKind, t: T): string {
  switch (kind) {
    case 'formula':
      return t('cheatSheet.kindFormula')
    case 'definition':
      return t('cheatSheet.kindDefinition')
    case 'theorem':
      return t('cheatSheet.kindTheorem')
    case 'method':
      return t('cheatSheet.kindMethod')
    case 'example':
      return t('cheatSheet.kindExample')
    case 'pitfall':
      return t('cheatSheet.kindPitfall')
  }
}

/** A short name for a document in a citation mark: "L45" for "… Lecture 45 …",
 * else the first words of its name. */
export function shortSourceLabel(name: string | undefined): string {
  if (!name) return '?'
  const match = /\b(lecture|lect|lec|week|class|chapter|ch)\.?\s*(\d+)/i.exec(name)
  if (match) {
    const prefix: Record<string, string> = { lecture: 'L', lect: 'L', lec: 'L', week: 'W', class: 'C', chapter: 'Ch', ch: 'Ch' }
    return `${prefix[match[1].toLowerCase()]}${Number(match[2])}`
  }
  const words = name.replace(/\.(pdf|pptx?|docx?)$/i, '').split(/\s+/).slice(0, 2).join(' ')
  return words.length > 14 ? `${words.slice(0, 13)}…` : words
}

export function citeLabel(cite: SheetCite, names: Record<string, string>): string {
  const pages = cite.page_start === cite.page_end ? `${cite.page_start}` : `${cite.page_start}–${cite.page_end}`
  return `${shortSourceLabel(names[cite.source])}·${pages}`
}

/** Printed geometry, matching the backend's budget (FONT_PT_BY_COLUMNS). */
export const PAPER = {
  letter: { width: 8.5, height: 11 },
  a4: { width: 8.27, height: 11.69 },
} as const
export const MARGIN_IN = 0.35
export const COLUMN_GAP_PT = 8

export function fontPt(columns: number): number {
  return columns <= 2 ? 8 : columns >= 4 ? 6 : 7
}

export function pageGeometry(options: Pick<SheetOptions, 'paper' | 'columns'>) {
  const paper = PAPER[options.paper] ?? PAPER.letter
  return {
    paperWidth: paper.width,
    paperHeight: paper.height,
    contentWidth: paper.width - 2 * MARGIN_IN,
    contentHeight: paper.height - 2 * MARGIN_IN,
    font: fontPt(options.columns),
  }
}
