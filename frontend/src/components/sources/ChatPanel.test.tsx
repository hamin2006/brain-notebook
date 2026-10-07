import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChatPanel } from './ChatPanel'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: () => ({ openModal: vi.fn() }),
}))

// Keep the message-content deps light for this composer-focused test.
vi.mock('@/components/sources/MessageActions', () => ({
  MessageActions: () => null,
}))

// jsdom has no canvas: attached images become a fixed data URL.
vi.mock('./ImageAttachments', async importOriginal => ({
  ...(await importOriginal<typeof import('./ImageAttachments')>()),
  readImageFile: vi.fn(async () => 'data:image/jpeg;base64,IMG'),
}))

describe('ChatPanel composer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom does not implement scrollIntoView (used by the auto-scroll effect).
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
  })

  const getTextarea = () => screen.getByRole('textbox') as HTMLTextAreaElement

  it('sends the typed message and clears the input on send-button click', () => {
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: '  hello world  ' } })

    const sendButton = screen.getByRole('button')
    fireEvent.click(sendButton)

    expect(onSendMessage).toHaveBeenCalledTimes(1)
    expect(onSendMessage).toHaveBeenCalledWith('hello world', undefined, undefined)
    expect(textarea.value).toBe('')
  })

  it('sends on Cmd+Enter on macOS', () => {
    const uaSpy = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
    )
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: 'via cmd' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true, ctrlKey: false })

    expect(onSendMessage).toHaveBeenCalledWith('via cmd', undefined, undefined)
    expect(textarea.value).toBe('')
    uaSpy.mockRestore()
  })

  it('sends on Ctrl+Enter on non-macOS', () => {
    const uaSpy = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    )
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: 'via ctrl' } })
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true, metaKey: false })

    expect(onSendMessage).toHaveBeenCalledWith('via ctrl', undefined, undefined)
    expect(textarea.value).toBe('')
    uaSpy.mockRestore()
  })

  it('sends on plain Enter and keeps Shift+Enter for a new line', () => {
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: 'first line' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(onSendMessage).not.toHaveBeenCalled()

    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSendMessage).toHaveBeenCalledWith('first line', undefined, undefined)
  })

  it('does not send while streaming', () => {
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={true}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    // Textarea is disabled while streaming, but the guard must also hold.
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })

    expect(onSendMessage).not.toHaveBeenCalled()
  })

  it('sends pasted images with the message when images are allowed', async () => {
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
        allowImages
      />
    )
    const textarea = getTextarea()
    const file = new File(['x'], 'shot.png', { type: 'image/png' })
    fireEvent.paste(textarea, { clipboardData: { files: [file] } })
    expect(await screen.findByAltText('chat.attachedImage')).toBeTruthy()

    fireEvent.change(textarea, { target: { value: 'which lecture has this?' } })
    fireEvent.click(screen.getByLabelText('chat.attachImage').parentElement!.querySelectorAll('button')[1])

    expect(onSendMessage).toHaveBeenCalledWith('which lecture has this?', undefined, [
      'data:image/jpeg;base64,IMG',
    ])
    expect(screen.queryByAltText('chat.attachedImage')).toBeNull()
  })

  it('ignores pasted images when images are not allowed', () => {
    render(
      <ChatPanel messages={[]} isStreaming={false} contextIndicators={null} onSendMessage={vi.fn()} />
    )
    const file = new File(['x'], 'shot.png', { type: 'image/png' })
    fireEvent.paste(getTextarea(), { clipboardData: { files: [file] } })
    expect(screen.queryByLabelText('chat.attachImage')).toBeNull()
    expect(screen.queryByAltText('chat.attachedImage')).toBeNull()
  })
})
