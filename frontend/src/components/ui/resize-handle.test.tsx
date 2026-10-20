import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ResizeHandle } from './resize-handle'

// jsdom has no PointerEvent, so pointer events would arrive without clientX.
if (!('PointerEvent' in window)) {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init)
      this.pointerId = init.pointerId ?? 0
    }
  }
  Object.assign(window, { PointerEvent: PointerEventPolyfill })
}

function setup(side: 'left' | 'right', width = 400) {
  const onResize = vi.fn()
  const onReset = vi.fn()
  render(
    <ResizeHandle side={side} label="Resize" width={width} min={300} max={() => 800} onResize={onResize} onReset={onReset} />
  )
  return { handle: screen.getByRole('separator', { name: 'Resize' }), onResize, onReset }
}

describe('ResizeHandle', () => {
  it('grows a right-hand pane when dragged left, clamped to max', () => {
    const { handle, onResize } = setup('right')
    fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientX: 440, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(460)
    fireEvent.pointerMove(handle, { clientX: -1000, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(800)
    fireEvent.pointerUp(handle, { pointerId: 1 })
    fireEvent.pointerMove(handle, { clientX: 0, pointerId: 1 })
    expect(onResize).toHaveBeenCalledTimes(2) // no resizing after release
  })

  it('grows a left-hand pane when dragged right, clamped to min', () => {
    const { handle, onResize } = setup('left')
    fireEvent.pointerDown(handle, { clientX: 300, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientX: 330, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(430)
    fireEvent.pointerMove(handle, { clientX: 0, pointerId: 1 })
    expect(onResize).toHaveBeenLastCalledWith(300)
  })

  it('resizes with the arrow keys and resets on double-click', () => {
    const { handle, onResize, onReset } = setup('right')
    fireEvent.keyDown(handle, { key: 'ArrowLeft' })
    expect(onResize).toHaveBeenLastCalledWith(424)
    fireEvent.doubleClick(handle)
    expect(onReset).toHaveBeenCalled()
  })
})
