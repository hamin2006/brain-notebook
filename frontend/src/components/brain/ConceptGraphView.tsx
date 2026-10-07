'use client'

import dynamic from 'next/dynamic'
import { useState } from 'react'
import { Box, Map as MapIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ConceptGraph2D } from './ConceptGraph'

// WebGL and three.js load only when someone opens the 3D view
const ConceptGraph3D = dynamic(() => import('./ConceptGraph3D').then((m) => m.ConceptGraph3D), {
  ssr: false,
  loading: () => (
    <div className="flex h-full flex-1 items-center justify-center">
      <LoadingSpinner size="lg" />
    </div>
  ),
})

/** The Graph view: the 2D map for reading, or the 3D scene for exploring. */
export function ConceptGraph({ notebookId }: { notebookId: string }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'2d' | '3d'>('2d')
  return (
    <div className="relative flex h-full min-h-0 flex-1">
      {mode === '2d' ? <ConceptGraph2D notebookId={notebookId} /> : <ConceptGraph3D notebookId={notebookId} />}
      <div
        className="absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center rounded-full border bg-card/90 p-0.5 shadow-lift backdrop-blur"
        role="radiogroup"
        aria-label={t('brain.graphMode')}
      >
        {([
          { value: '2d', icon: MapIcon, label: t('brain.graph2d') },
          { value: '3d', icon: Box, label: t('brain.graph3d') },
        ] as const).map(({ value, icon: Icon, label }) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={mode === value}
            onClick={() => setMode(value)}
            className={cn(
              'flex h-7 items-center gap-1.5 rounded-full px-3 text-[11.5px] font-medium transition-colors',
              mode === value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
