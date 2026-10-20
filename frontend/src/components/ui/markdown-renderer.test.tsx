import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { MarkdownRenderer } from './markdown-renderer'

describe('MarkdownRenderer', () => {
  it('renders basic markdown', () => {
    const { container } = render(<MarkdownRenderer>{'# Title\n\nSome **bold** text'}</MarkdownRenderer>)
    expect(container.querySelector('h1')?.textContent).toBe('Title')
    expect(container.querySelector('strong')?.textContent).toBe('bold')
  })

  it('highlights fenced code blocks for registered languages', () => {
    const { container } = render(
      <MarkdownRenderer>{'```python\ndef hello():\n    return 42\n```'}</MarkdownRenderer>
    )
    // PrismLight emits token spans when the grammar is registered; a plain
    // fallback would leave the code block without any token markup.
    expect(container.querySelectorAll('span[class*="token"]').length).toBeGreaterThan(0)
  })

  it('falls back to plain text for unknown languages without crashing', () => {
    const { container } = render(
      <MarkdownRenderer>{'```notalanguage\nsome content\n```'}</MarkdownRenderer>
    )
    expect(container.textContent).toContain('some content')
  })

  it('keeps the rendered nodes across re-renders (a remount resets the scroll)', () => {
    const md = '# Title\n\nSome text'
    const { container, rerender } = render(<MarkdownRenderer>{md}</MarkdownRenderer>)
    const heading = container.querySelector('h1')
    rerender(<MarkdownRenderer components={{}}>{md}</MarkdownRenderer>)
    expect(container.querySelector('h1')).toBe(heading)
  })

  it('renders inline code without a highlighter block', () => {
    const { container } = render(<MarkdownRenderer>{'Use `npm ci` here'}</MarkdownRenderer>)
    expect(container.querySelector('code')?.textContent).toBe('npm ci')
    expect(container.querySelectorAll('span[class*="token"]').length).toBe(0)
  })
})
