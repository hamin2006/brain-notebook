'use client'

import { useEffect, useState } from 'react'
import { Trash2, Sparkles, ArrowDownWideNarrow, ScanEye, Share2, Globe2, Brain, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import {
  useAgentMemories,
  useAgentSettings,
  useDeleteAgentMemory,
  useRebuildAgentData,
  useUpdateAgentSettings,
} from '@/lib/hooks/use-agent'
import { useTranslation } from '@/lib/hooks/use-translation'

function ModelField({
  id,
  label,
  help,
  value,
  onSave,
  disabled,
}: {
  id: string
  label: string
  help: string
  value: string
  onSave: (value: string) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex gap-2">
        <Input id={id} value={draft} onChange={e => setDraft(e.target.value)} disabled={disabled} />
        <Button variant="outline" onClick={() => onSave(draft.trim())} disabled={disabled || draft.trim() === value}>
          {t('common.save')}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">{help}</p>
    </div>
  )
}

/** Research agent extensions: rerank, visual page search, concept graph, memory. */
export function AgentSettingsCard() {
  const { t } = useTranslation()
  const { data: settings, isLoading } = useAgentSettings()
  const { data: memories = [] } = useAgentMemories()
  const update = useUpdateAgentSettings()
  const rebuild = useRebuildAgentData()
  const forget = useDeleteAgentMemory()

  if (isLoading || !settings) {
    return (
      <Card>
        <CardContent className="py-6">
          <LoadingSpinner />
        </CardContent>
      </Card>
    )
  }

  const busy = update.isPending
  return (
    <Card className="gap-0 overflow-hidden py-0">
      <CardHeader className="border-b bg-surface-recessed/50 py-5">
        <CardTitle className="flex items-center gap-2 font-display text-[24px] font-normal">
          <Sparkles className="h-4 w-4 text-iris" />
          {t('settings.agentTitle')}
        </CardTitle>
        <CardDescription>{t('settings.agentDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-px bg-border p-0 md:grid-cols-2">
        <FeatureTile icon={ArrowDownWideNarrow} tone="text-iris" active={!!settings.rerank_model}>
          <ModelField
            id="rerank_model"
            label={t('settings.rerankModel')}
            help={t('settings.rerankHelp')}
            value={settings.rerank_model}
            onSave={value => update.mutate({ rerank_model: value })}
            disabled={busy}
          />
        </FeatureTile>

        <FeatureTile icon={ScanEye} tone="text-plum" active={!!settings.page_embedding_model}>
          <ModelField
            id="page_embedding_model"
            label={t('settings.pageEmbeddingModel')}
            help={t('settings.pageEmbeddingHelp')}
            value={settings.page_embedding_model}
            onSave={value => update.mutate({ page_embedding_model: value })}
            disabled={busy}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => rebuild.mutate('page_embeddings')}
            disabled={!settings.page_embedding_model || rebuild.isPending}
          >
            {t('settings.rebuildPageEmbeddings')}
          </Button>
        </FeatureTile>

        <FeatureTile icon={Share2} tone="text-fern" active={settings.knowledge_graph}>
          <div className="flex items-center gap-2">
            <Checkbox
              id="knowledge_graph"
              checked={settings.knowledge_graph}
              onCheckedChange={checked => update.mutate({ knowledge_graph: checked === true })}
              disabled={busy}
            />
            <Label htmlFor="knowledge_graph">{t('settings.knowledgeGraph')}</Label>
          </div>
          <p className="text-sm text-muted-foreground">{t('settings.knowledgeGraphHelp')}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => rebuild.mutate('concepts')}
            disabled={!settings.knowledge_graph || rebuild.isPending}
          >
            {t('settings.rebuildConcepts')}
          </Button>
        </FeatureTile>

        <FeatureTile icon={Globe2} tone="text-slate-hue" active={settings.web_search}>
          <div className="flex items-center gap-2">
            <Checkbox
              id="web_search"
              checked={settings.web_search}
              onCheckedChange={checked => update.mutate({ web_search: checked === true })}
              disabled={busy}
            />
            <Label htmlFor="web_search">{t('settings.webSearch')}</Label>
          </div>
          <p className="text-sm text-muted-foreground">{t('settings.webSearchHelp')}</p>
        </FeatureTile>

        <FeatureTile icon={Brain} tone="text-amber" active={settings.memory} wide>
          <div className="flex items-center gap-2">
            <Checkbox
              id="agent_memory"
              checked={settings.memory}
              onCheckedChange={checked => update.mutate({ memory: checked === true })}
              disabled={busy}
            />
            <Label htmlFor="agent_memory">{t('settings.agentMemory')}</Label>
          </div>
          <p className="text-sm text-muted-foreground">{t('settings.agentMemoryHelp')}</p>
          <div className="space-y-2">
            <p className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{t('settings.memories')}</p>
            {memories.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('settings.noMemories')}</p>
            ) : (
              <ul className="grid gap-2 md:grid-cols-2">
                {memories.map(memory => (
                  <li key={memory.id} className="flex items-start justify-between gap-2 rounded-xl border bg-card px-3 py-2 text-sm shadow-soft">
                    <span>
                      {memory.content}
                      {!memory.notebook_id && (
                        <span className="ml-2 text-xs text-muted-foreground">({t('settings.memoryEverywhere')})</span>
                      )}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 flex-shrink-0"
                      aria-label={t('settings.forgetMemory')}
                      title={t('settings.forgetMemory')}
                      onClick={() => forget.mutate(memory.id)}
                      disabled={forget.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </FeatureTile>
      </CardContent>
    </Card>
  )
}

/** One agent capability: an icon that lights up when it's on, and its controls. */
function FeatureTile({
  icon: Icon,
  tone,
  active,
  wide,
  children,
}: {
  icon: LucideIcon
  tone: string
  active: boolean
  wide?: boolean
  children: React.ReactNode
}) {
  return (
    <div className={cn('flex gap-4 bg-card p-5', wide && 'md:col-span-2')}>
      <div className={cn('flex size-9 shrink-0 items-center justify-center rounded-xl border bg-surface-recessed', active ? tone : 'text-muted-foreground opacity-60')}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-3">{children}</div>
    </div>
  )
}
