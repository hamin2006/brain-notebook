import type { ContextMode } from '@/lib/types/notebook-context'

/**
 * Bulk chat-context actions for sources and notes. Context is binary: an item
 * is either in the agent's search scope (`full`) or left out (`off`).
 */
export type ContextDefault = 'include' | 'exclude'

interface ItemLike {
  id: string
}

/** Resolve the context mode a bulk action implies for a single item. */
export function bulkMode(action: ContextDefault): ContextMode {
  return action === 'exclude' ? 'off' : 'full'
}

/**
 * Compute chat-context selections for a batch of items while preserving
 * existing choices.
 *
 * Newly-seen items adopt `defaultAction`, so a prior bulk action also governs
 * items that load later via pagination — otherwise a bulk action would
 * silently miss items loaded after it (#223/#915).
 */
export function computeSelections(
  existing: Record<string, ContextMode>,
  items: ItemLike[],
  defaultAction: ContextDefault = 'include',
): Record<string, ContextMode> {
  const next = { ...existing }
  for (const item of items) {
    if (next[item.id] === undefined) {
      next[item.id] = bulkMode(defaultAction)
    }
  }
  return next
}

/** Apply a uniform bulk context action to every given item. */
export function applyBulkContext(
  existing: Record<string, ContextMode>,
  items: ItemLike[],
  action: ContextDefault,
): Record<string, ContextMode> {
  const next = { ...existing }
  for (const item of items) {
    next[item.id] = bulkMode(action)
  }
  return next
}
