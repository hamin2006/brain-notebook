'use client'

import { useRef } from 'react'
import { cn } from '@/lib/utils'

const KEY_STEP = 24

/**
 * A vertical drag handle that sets the width of the pane on one `side` of it.
 * Drag with the pointer, use the arrow keys when focused, double-click to reset.
 */
export function ResizeHandle({
  width,
  min,
  max,
  side,
  label,
  onResize,
  onReset,
}: {
  width: number
  min: number
  /** Read at drag time, so it follows the window size. */
  max: () => number
  /** Where the resized pane sits relative to the handle. */
  side: 'left' | 'right'
  label: string
  onResize: (width: number) => void
  onReset: () => void
}) {
  const drag = useRef<{ x: number; width: number } | null>(null)
  const clamp = (w: number) => Math.round(Math.min(Math.max(w, min), Math.max(min, max())))
  // Moving toward the pane shrinks it; away from it grows it.
  const grow = (dx: number) => (side === 'left' ? dx : -dx)

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      tabIndex={0}
      className={cn(
        'relative z-10 -mx-1 w-2 shrink-0 cursor-col-resize touch-none select-none',
        'after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:transition-colors',
        'hover:after:w-0.5 hover:after:bg-ring focus-visible:outline-none focus-visible:after:w-0.5 focus-visible:after:bg-ring'
      )}
      onPointerDown={(e) => {
        e.preventDefault()
        drag.current = { x: e.clientX, width }
        e.currentTarget.setPointerCapture?.(e.pointerId)
      }}
      onPointerMove={(e) => {
        if (drag.current) onResize(clamp(drag.current.width + grow(e.clientX - drag.current.x)))
      }}
      onPointerUp={() => {
        drag.current = null
      }}
      onPointerCancel={() => {
        drag.current = null
      }}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
        e.preventDefault()
        onResize(clamp(width + grow(e.key === 'ArrowRight' ? KEY_STEP : -KEY_STEP)))
      }}
    />
  )
}
