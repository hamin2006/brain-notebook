'use client'

import { EyeOff, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { ContextMode } from '@/app/(dashboard)/notebooks/[id]/page'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ContextToggleProps {
  mode: ContextMode
  onChange: (mode: ContextMode) => void
  className?: string
}

export function ContextToggle({
  mode,
  onChange,
  className
}: ContextToggleProps) {
  const { t } = useTranslation()

  const MODE_CONFIG = {
    off: {
      icon: EyeOff,
      label: t('common.contextModes.off'),
      color: 'text-muted-foreground',
      bgColor: 'hover:bg-muted'
    },
    full: {
      icon: FileText,
      label: t('common.contextModes.full'),
      color: 'text-ctx-full',
      bgColor: 'hover:bg-ctx-full-tint'
    }
  } as const
  const config = MODE_CONFIG[mode]
  const Icon = config.icon

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation() // Prevent card click
    onChange(mode === 'off' ? 'full' : 'off')
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-8 w-8 p-0 transition-colors',
              config.bgColor,
              className
            )}
            onClick={handleClick}
          >
            <Icon className={cn('h-4 w-4', config.color)} />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">{config.label}</p>
          <p className="text-[10px] text-muted-foreground mt-1">
            {t('common.contextModes.clickToCycle')}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
