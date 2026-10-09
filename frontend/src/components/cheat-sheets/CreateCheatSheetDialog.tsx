'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { DEFAULT_KINDS, RECALL_KINDS, type RecallKind } from '@/lib/api/cheat-sheets'
import { useCheatSheetSources, useCreateCheatSheet } from '@/lib/hooks/use-cheat-sheets'
import { useTranslation } from '@/lib/hooks/use-translation'
import { kindLabel, sheetHref } from './sheet-utils'

interface CreateCheatSheetDialogProps {
  notebookId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className="flex rounded-lg bg-surface-recessed p-0.5" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'h-7 flex-1 rounded-md px-3 text-xs font-medium transition-colors',
            value === option.value ? 'bg-card text-foreground shadow-soft' : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function CreateCheatSheetDialog({ notebookId, open, onOpenChange }: CreateCheatSheetDialogProps) {
  const { t } = useTranslation()
  const router = useRouter()
  const { data: sources, isLoading } = useCheatSheetSources(notebookId, open)
  const create = useCreateCheatSheet(notebookId)

  const [title, setTitle] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [pages, setPages] = useState(2)
  const [columns, setColumns] = useState(3)
  const [paper, setPaper] = useState<'letter' | 'a4'>('letter')
  const [kinds, setKinds] = useState<RecallKind[]>(DEFAULT_KINDS)
  const [instructions, setInstructions] = useState('')

  // All documents are picked when the dialog opens.
  useEffect(() => {
    if (open && sources) setSelected(new Set(sources.map((s) => s.id)))
  }, [open, sources])

  const allSelected = !!sources && selected.size === sources.length
  const toggleKind = (kind: RecallKind) =>
    setKinds((current) => (current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]))
  const ordered = useMemo(() => RECALL_KINDS.filter((k) => kinds.includes(k)), [kinds])

  const submit = async () => {
    const sheet = await create.mutateAsync({
      title: title.trim() || undefined,
      source_ids: allSelected ? undefined : Array.from(selected),
      pages,
      columns,
      paper,
      kinds: ordered,
      instructions: instructions.trim(),
    })
    onOpenChange(false)
    setTitle('')
    setInstructions('')
    router.push(sheetHref(notebookId, sheet.id))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('cheatSheet.newTitle')}</DialogTitle>
          <DialogDescription>{t('cheatSheet.newDescription')}</DialogDescription>
        </DialogHeader>

        <div className="grid gap-5 md:grid-cols-[1fr_1fr]">
          <div className="flex min-h-0 flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>{t('cheatSheet.documents')}</Label>
              {sources && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => setSelected(allSelected ? new Set() : new Set(sources.map((s) => s.id)))}
                >
                  {allSelected ? t('cheatSheet.selectNone') : t('cheatSheet.selectAll')}
                </button>
              )}
            </div>
            <div className="max-h-72 overflow-y-auto rounded-md border p-1.5">
              {isLoading && <Loader2 className="m-3 h-4 w-4 animate-spin text-muted-foreground" />}
              {sources?.map((source) => (
                <label
                  key={source.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-accent"
                >
                  <Checkbox
                    checked={selected.has(source.id)}
                    onCheckedChange={(checked) =>
                      setSelected((current) => {
                        const next = new Set(current)
                        if (checked) next.add(source.id)
                        else next.delete(source.id)
                        return next
                      })
                    }
                  />
                  <span className="truncate">{source.title}</span>
                </label>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {t('cheatSheet.documentsPicked', { count: selected.size, total: sources?.length ?? 0 })}
            </p>
          </div>

          <div className="flex flex-col gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="sheet-title">{t('cheatSheet.titleLabel')}</Label>
              <Input
                id="sheet-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t('cheatSheet.titlePlaceholder')}
                maxLength={200}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>{t('cheatSheet.length')}</Label>
                <Segmented
                  label={t('cheatSheet.length')}
                  value={pages}
                  onChange={setPages}
                  options={[
                    { value: 1, label: t('cheatSheet.onePage') },
                    { value: 2, label: t('cheatSheet.twoPages') },
                  ]}
                />
              </div>
              <div className="space-y-1.5">
                <Label>{t('cheatSheet.columns')}</Label>
                <Segmented
                  label={t('cheatSheet.columns')}
                  value={columns}
                  onChange={setColumns}
                  options={[2, 3, 4].map((n) => ({ value: n, label: String(n) }))}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>{t('cheatSheet.paper')}</Label>
              <Segmented
                label={t('cheatSheet.paper')}
                value={paper}
                onChange={setPaper}
                options={[
                  { value: 'letter', label: t('cheatSheet.paperLetter') },
                  { value: 'a4', label: t('cheatSheet.paperA4') },
                ]}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t('cheatSheet.include')}</Label>
              <div className="grid grid-cols-2 gap-1.5">
                {RECALL_KINDS.map((kind) => (
                  <label key={kind} className="flex cursor-pointer items-center gap-2 text-xs">
                    <Checkbox checked={kinds.includes(kind)} onCheckedChange={() => toggleKind(kind)} />
                    {kindLabel(kind, t)}
                  </label>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="sheet-instructions">{t('cheatSheet.instructions')}</Label>
          <Textarea
            id="sheet-instructions"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder={t('cheatSheet.instructionsPlaceholder')}
            rows={2}
            maxLength={2000}
          />
        </div>

        <DialogFooter className="items-center sm:justify-between">
          <p className="text-[11px] text-muted-foreground">{t('cheatSheet.buildHint')}</p>
          <Button onClick={submit} disabled={selected.size === 0 || ordered.length === 0 || create.isPending}>
            {create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('cheatSheet.build')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
