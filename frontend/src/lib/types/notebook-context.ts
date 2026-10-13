/** Chat-context inclusion for a notebook source or note: searched by the agent, or off. */
export type ContextMode = 'off' | 'full'

export interface ContextSelections {
  sources: Record<string, ContextMode>
  notes: Record<string, ContextMode>
}
