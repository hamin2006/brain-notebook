'use client'

import { memo, useCallback, useState, useRef, useEffect, useId } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { ArrowUp, Loader2, Paperclip, History, SquarePen, Zap, Search, Telescope, Lightbulb, FileText, StickyNote } from 'lucide-react'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import {
  SourceChatMessage,
  SourceChatContextIndicator,
  BaseChatSession,
  ChatEffort,
  Grounding
} from '@/lib/types/api'
import type { AgentActivity } from '@/lib/hooks/use-notebook-chat'
import type { NotebookOverview } from '@/lib/api/explore'
import { PagePreviewDialog, PageTarget, parsePageLocator } from './PagePreviewDialog'
import { AttachmentStrip, MAX_ATTACHMENTS, imageFiles, readImageFile } from './ImageAttachments'
import { ModelSelector } from './ModelSelector'
import { SessionManager } from '@/components/sources/SessionManager'
import { MessageActions } from '@/components/sources/MessageActions'
import { type ReferenceClick } from '@/components/brain/Citations'
import { AnswerContent } from '@/components/brain/Answer'
import { LiveResearch, ResearchTrace } from '@/components/brain/ResearchTimeline'
import { ChatWelcome } from '@/components/brain/ChatWelcome'
import { BrainMark } from '@/components/brand/BrainMark'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { toast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface NotebookContextStats {
  sourcesInsights: number
  sourcesFull: number
  notesCount: number
  tokenCount?: number
  charCount?: number
}

interface ChatPanelProps {
  messages: SourceChatMessage[]
  isStreaming: boolean
  contextIndicators: SourceChatContextIndicator | null
  onSendMessage: (message: string, modelOverride?: string, images?: string[]) => void
  modelOverride?: string
  onModelChange?: (model?: string) => void
  // Session management props
  sessions?: BaseChatSession[]
  currentSessionId?: string | null
  onCreateSession?: (title: string) => void
  onSelectSession?: (sessionId: string) => void
  onDeleteSession?: (sessionId: string) => void
  onUpdateSession?: (sessionId: string, title: string) => void
  loadingSessions?: boolean
  // Start an empty conversation (session created on first message)
  onNewChat?: () => void
  // Generic props for reusability
  title?: string
  contextType?: 'source' | 'notebook'
  // Notebook context stats (for notebook chat)
  notebookContextStats?: NotebookContextStats
  // Notebook ID for saving notes
  notebookId?: string
  notebookName?: string
  // What the notebook holds (welcome screen starters)
  overview?: NotebookOverview
  // Titles for citations, keyed "source:abc" / "note:xyz"
  referenceTitles?: Record<string, string>
  // Open a cited page range in a side panel instead of a dialog
  onOpenPages?: (target: PageTarget) => void
  // Research agent (notebook chat): live steps and effort level
  agentActivity?: AgentActivity | null
  effort?: ChatEffort
  onEffortChange?: (effort: ChatEffort) => void
  // Notebook setting: answer only from the notebook, or add general knowledge
  grounding?: Grounding
  onGroundingChange?: (grounding: Grounding) => void
  // Let the user attach images to a message (notebook chat)
  allowImages?: boolean
}

export function ChatPanel({
  messages,
  isStreaming,
  contextIndicators,
  onSendMessage,
  modelOverride,
  onModelChange,
  sessions = [],
  currentSessionId,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  onUpdateSession,
  loadingSessions = false,
  onNewChat,
  title,
  contextType = 'source',
  notebookContextStats,
  notebookId,
  notebookName,
  overview,
  referenceTitles = {},
  onOpenPages,
  agentActivity,
  effort,
  onEffortChange,
  allowImages = false
}: ChatPanelProps) {
  const { t } = useTranslation()
  const [sessionManagerOpen, setSessionManagerOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { openModal } = useModalManager()
  const [pageTarget, setPageTarget] = useState<PageTarget | null>(null)
  const [startedAt, setStartedAt] = useState(() => Date.now())

  useEffect(() => {
    if (isStreaming) setStartedAt(Date.now())
  }, [isStreaming])

  // Stable reference-click handler so memoized messages don't re-render on
  // composer keystrokes (the input state lives in the ChatComposer child).
  const handleReferenceClick = useCallback<ReferenceClick>((type, id, locator) => {
    // A page citation shows the page itself; anything else opens the item.
    const pages = type === 'source' ? parsePageLocator(locator) : null
    if (pages) {
      const target = { sourceId: id, ...pages }
      if (onOpenPages) onOpenPages(target)
      else setPageTarget(target)
      return
    }
    const modalType = type === 'source_insight' ? 'insight' : type as 'source' | 'note' | 'insight'
    try {
      openModal(modalType, id)
    } catch {
      toast.error(t('common.noResults'))
    }
  }, [openModal, onOpenPages, t])

  // Auto-scroll to bottom when new messages or research steps arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, agentActivity?.steps.length, agentActivity?.text.length])

  const currentTitle = sessions.find(s => s.id === currentSessionId)?.title
  const hasSessions = !!(onSelectSession && onCreateSession && onDeleteSession)
  const scopeLabel = notebookContextStats
    ? t('brain.scopeLabel', {
        sources: notebookContextStats.sourcesFull + notebookContextStats.sourcesInsights,
        notes: notebookContextStats.notesCount,
      })
    : null

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {/* Conversation bar */}
      <div className="flex h-11 flex-shrink-0 items-center gap-2 px-4">
        <p className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
          {currentTitle || title || t('brain.newConversation')}
        </p>
        {onNewChat && (
          <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-muted-foreground" onClick={onNewChat} disabled={isStreaming}>
            <SquarePen className="h-3.5 w-3.5" />
            <span className="hidden text-xs sm:inline">{t('brain.newChat')}</span>
          </Button>
        )}
        {hasSessions && (
          <Dialog open={sessionManagerOpen} onOpenChange={setSessionManagerOpen}>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 text-muted-foreground"
              onClick={() => setSessionManagerOpen(true)}
              disabled={loadingSessions}
            >
              <History className="h-3.5 w-3.5" />
              <span className="hidden text-xs sm:inline">{t('chat.sessions')}</span>
              {sessions.length > 0 && <span className="font-mono text-[10px] opacity-70">{sessions.length}</span>}
            </Button>
            <DialogContent className="sm:max-w-[420px] p-0 overflow-hidden">
              <DialogTitle className="sr-only">{t('chat.sessionsTitle')}</DialogTitle>
              <SessionManager
                sessions={sessions}
                currentSessionId={currentSessionId ?? null}
                onCreateSession={(title) => onCreateSession?.(title)}
                onSelectSession={(sessionId) => {
                  onSelectSession?.(sessionId)
                  setSessionManagerOpen(false)
                }}
                onUpdateSession={(sessionId, title) => onUpdateSession?.(sessionId, title)}
                onDeleteSession={(sessionId) => onDeleteSession?.(sessionId)}
                loadingSessions={loadingSessions}
              />
            </DialogContent>
          </Dialog>
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[46rem] space-y-10 px-4 pb-10 pt-4 md:px-6">
          {messages.length === 0 && !isStreaming ? (
            contextType === 'notebook' ? (
              <ChatWelcome
                notebookName={notebookName}
                overview={overview}
                onAsk={(q) => onSendMessage(q, modelOverride)}
                allowImages={allowImages}
              />
            ) : (
              <div className="flex flex-col items-center py-16 text-center text-muted-foreground">
                <BrainMark className="size-9 opacity-80" />
                <p className="mt-4 font-display text-2xl text-foreground">{t('brain.welcomeTitle')}</p>
                <p className="mt-1 text-xs">{t('chat.askQuestions')}</p>
              </div>
            )
          ) : (
            messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                notebookId={notebookId}
                referenceTitles={referenceTitles}
                onReferenceClick={handleReferenceClick}
              />
            ))
          )}
          {isStreaming && (
            <div className="space-y-4 animate-fade-up">
              <AgentHeader />
              {agentActivity ? (
                <>
                  {(agentActivity.steps.length > 0 || !agentActivity.text) && (
                    <LiveResearch activity={agentActivity} startedAt={startedAt} />
                  )}
                  {agentActivity.text && (
                    <div className="answer-prose">
                      <MarkdownRenderer>{agentActivity.text}</MarkdownRenderer>
                      <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-iris" />
                    </div>
                  )}
                </>
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="shimmer-text">{t('chat.researching')}</span>
                </div>
              )}
            </div>
          )}
          {contextIndicators && <SourceContextIndicators indicators={contextIndicators} />}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Composer */}
      <div className="flex-shrink-0 px-4 pb-4 md:px-6">
        <ChatComposer
          onSendMessage={onSendMessage}
          isStreaming={isStreaming}
          modelOverride={modelOverride}
          onModelChange={onModelChange}
          effort={effort}
          onEffortChange={onEffortChange}
          allowImages={allowImages}
          scopeLabel={scopeLabel}
        />
      </div>

      <PagePreviewDialog
        target={pageTarget}
        onClose={() => setPageTarget(null)}
        onOpenSource={(sourceId) => {
          setPageTarget(null)
          openModal('source', sourceId.replace(/^source:/, ''))
        }}
      />
    </div>
  )
}

function AgentHeader() {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2">
      <BrainMark className="size-6" />
      <span className="text-[13px] font-semibold">{t('brain.agentName')}</span>
    </div>
  )
}

function SourceContextIndicators({ indicators }: { indicators: SourceChatContextIndicator }) {
  const { t } = useTranslation()
  const items = [
    { icon: FileText, count: indicators.sources?.length ?? 0, label: t('navigation.sources') },
    { icon: Lightbulb, count: indicators.insights?.length ?? 0, label: t('common.insights') },
    { icon: StickyNote, count: indicators.notes?.length ?? 0, label: t('common.notes') },
  ].filter(i => i.count > 0)
  if (!items.length) return null
  return (
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      {items.map(({ icon: Icon, count, label }) => (
        <span key={label} className="flex items-center gap-1">
          <Icon className="h-3 w-3" />
          {count} {label}
        </span>
      ))}
    </div>
  )
}

const EFFORTS: { value: ChatEffort; icon: typeof Zap; key: string; hint: string }[] = [
  { value: 'quick', icon: Zap, key: 'chat.effortQuick', hint: 'brain.effortQuickHint' },
  { value: 'standard', icon: Search, key: 'chat.effortStandard', hint: 'brain.effortStandardHint' },
  { value: 'deep', icon: Telescope, key: 'chat.effortDeep', hint: 'brain.effortDeepHint' },
]

// Composer owns the input state so keystrokes (including IME composition) only
// re-render this small component instead of the whole message history.
interface ChatComposerProps {
  onSendMessage: (message: string, modelOverride?: string, images?: string[]) => void
  isStreaming: boolean
  modelOverride?: string
  onModelChange?: (model?: string) => void
  effort?: ChatEffort
  onEffortChange?: (effort: ChatEffort) => void
  // Let the user attach images to a message (notebook chat)
  allowImages?: boolean
  // "Searching 7 sources · 4 notes"
  scopeLabel?: string | null
}

function ChatComposer({
  onSendMessage,
  isStreaming,
  modelOverride,
  onModelChange,
  effort,
  onEffortChange,
  allowImages = false,
  scopeLabel
}: ChatComposerProps) {
  const { t } = useTranslation()
  const chatInputId = useId()
  const [input, setInput] = useState('')
  const [images, setImages] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const addImages = async (files: File[]) => {
    const room = MAX_ATTACHMENTS - images.length
    if (!allowImages || room <= 0 || !files.length) return
    try {
      const urls = await Promise.all(files.slice(0, room).map(file => readImageFile(file)))
      setImages(prev => [...prev, ...urls].slice(0, MAX_ATTACHMENTS))
    } catch {
      toast.error(t('common.error'))
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    const files = imageFiles(e.clipboardData?.files)
    if (allowImages && files.length) {
      e.preventDefault()
      void addImages(files)
    }
  }

  const handleSend = () => {
    if (input.trim() && !isStreaming) {
      onSendMessage(input.trim(), modelOverride, images.length ? images : undefined)
      setInput('')
      setImages([])
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter' || e.nativeEvent.isComposing) return
    // Enter sends; Shift+Enter is a new line. Cmd/Ctrl+Enter also sends.
    if (!e.shiftKey || e.metaKey || e.ctrlKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      className={cn(
        '@container mx-auto w-full max-w-[46rem] rounded-2xl border bg-card shadow-composer transition-colors focus-within:border-foreground/25',
        dragging && 'border-iris ring-2 ring-iris/20'
      )}
      onDragOver={allowImages ? (e) => { e.preventDefault(); setDragging(true) } : undefined}
      onDragLeave={allowImages ? () => setDragging(false) : undefined}
      onDrop={allowImages ? (e) => {
        e.preventDefault()
        setDragging(false)
        void addImages(imageFiles(e.dataTransfer?.files))
      } : undefined}
    >
      {images.length > 0 && (
        <div className="px-3 pt-3">
          <AttachmentStrip images={images} onRemove={index => setImages(prev => prev.filter((_, i) => i !== index))} />
        </div>
      )}
      <Textarea
        id={chatInputId}
        name="chat-message"
        autoComplete="off"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        placeholder={t('chat.sendPlaceholder')}
        disabled={isStreaming}
        className="max-h-[200px] min-h-[52px] resize-none border-0 bg-transparent px-4 pt-3.5 text-[15px] shadow-none focus-visible:ring-0"
        rows={1}
      />
      <div className="flex min-w-0 items-center gap-1 px-2 pb-2">
        {allowImages && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={e => {
                void addImages(imageFiles(e.target.files))
                e.target.value = ''
              }}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t('chat.attachImage')}
              title={t('chat.attachImage')}
              disabled={isStreaming || images.length >= MAX_ATTACHMENTS}
              onClick={() => fileInputRef.current?.click()}
              className="text-muted-foreground"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
          </>
        )}
        {onEffortChange && effort && (
          <div className="flex items-center rounded-lg bg-surface-recessed p-0.5" role="radiogroup" aria-label={t('chat.effort')}>
            {EFFORTS.map(({ value, icon: Icon, key, hint }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={effort === value}
                disabled={isStreaming}
                onClick={() => onEffortChange(value)}
                title={t(hint)}
                className={cn(
                  'flex h-7 items-center gap-1 rounded-md px-2 text-[11.5px] font-medium transition-colors',
                  effort === value ? 'bg-card text-foreground shadow-soft' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Icon className={cn('h-3 w-3', effort === value && value === 'deep' && 'text-iris')} />
                <span className="hidden @md:inline">{t(key)}</span>
              </button>
            ))}
          </div>
        )}
        {scopeLabel && (
          <span className="ml-1 hidden min-w-0 truncate text-[11px] text-muted-foreground @xl:inline">{scopeLabel}</span>
        )}
        <div className="flex-1" />
        {onModelChange && (
          <ModelSelector
            currentModel={modelOverride}
            onModelChange={onModelChange}
            disabled={isStreaming}
          />
        )}
        <Button
          onClick={handleSend}
          disabled={!input.trim() || isStreaming}
          size="icon-sm"
          aria-label={t('brain.send')}
          className="rounded-lg"
        >
          {isStreaming ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowUp className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  )
}

// Single chat message row. Memoized so historical messages don't re-render when
// unrelated state (e.g. the composer input) changes.
interface ChatMessageProps {
  message: SourceChatMessage
  notebookId?: string
  referenceTitles: Record<string, string>
  onReferenceClick: ReferenceClick
}

const ChatMessage = memo(function ChatMessage({
  message,
  notebookId,
  referenceTitles,
  onReferenceClick
}: ChatMessageProps) {
  if (message.type === 'human') {
    return (
      <div className="flex justify-end animate-fade-up">
        <div className="max-w-[85%] space-y-2 rounded-2xl rounded-br-md bg-surface-sunken px-4 py-2.5">
          {message.images?.length ? <AttachmentStrip images={message.images} /> : null}
          <p className="whitespace-pre-wrap break-words text-[14.5px] leading-relaxed">{message.content}</p>
        </div>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      <AgentHeader />
      {message.trace && message.trace.length > 0 && <ResearchTrace trace={message.trace} />}
      <AnswerContent content={message.content} referenceTitles={referenceTitles} onReferenceClick={onReferenceClick} />
      <MessageActions content={message.content} notebookId={notebookId} />
    </div>
  )
})
