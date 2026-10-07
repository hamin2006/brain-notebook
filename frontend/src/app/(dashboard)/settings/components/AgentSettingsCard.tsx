'use client'

import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
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
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.agentTitle')}</CardTitle>
        <CardDescription>{t('settings.agentDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ModelField
          id="rerank_model"
          label={t('settings.rerankModel')}
          help={t('settings.rerankHelp')}
          value={settings.rerank_model}
          onSave={value => update.mutate({ rerank_model: value })}
          disabled={busy}
        />
        <div className="space-y-2">
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
        </div>

        <div className="space-y-2">
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
        </div>

        <div className="space-y-2">
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
        </div>

        <div className="space-y-2">
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
          <div className="space-y-1">
            <p className="text-sm font-medium">{t('settings.memories')}</p>
            {memories.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('settings.noMemories')}</p>
            ) : (
              <ul className="space-y-1">
                {memories.map(memory => (
                  <li key={memory.id} className="flex items-start justify-between gap-2 rounded-md border px-3 py-2 text-sm">
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
        </div>
      </CardContent>
    </Card>
  )
}
