'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowUp, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'

/** One line to ask the research agent across every notebook (opens Ask). */
export function AskBar({ className, placeholder }: { className?: string; placeholder?: string }) {
  const { t } = useTranslation()
  const router = useRouter()
  const [question, setQuestion] = useState('')

  const submit = () => {
    const q = question.trim()
    if (!q) return
    router.push(`/search?mode=ask&q=${encodeURIComponent(q)}`)
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      className={cn(
        'group flex items-center gap-3 rounded-2xl border bg-card p-2 pl-4 shadow-composer transition-colors focus-within:border-iris/50',
        className
      )}
    >
      <Sparkles className="h-4 w-4 shrink-0 text-iris" />
      <input
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder={placeholder ?? t('brain.askEverywherePlaceholder')}
        aria-label={t('brain.askEverywherePlaceholder')}
        className="h-10 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-ink-faint"
      />
      <button
        type="submit"
        disabled={!question.trim()}
        aria-label={t('brain.research')}
        className="flex h-10 items-center gap-1.5 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-30"
      >
        <span className="hidden sm:inline">{t('brain.research')}</span>
        <ArrowUp className="h-4 w-4" />
      </button>
    </form>
  )
}
