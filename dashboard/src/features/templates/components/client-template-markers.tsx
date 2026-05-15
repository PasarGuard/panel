import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { Merge } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface ClientTemplateMarkersProps {
  isDefault?: boolean
  isSystem?: boolean
  className?: string
}

const baseMarkerClassName = 'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md border shadow-sm'

export default function ClientTemplateMarkers({ isDefault, isSystem, className }: ClientTemplateMarkersProps) {
  const { t } = useTranslation()

  if (!isDefault && !isSystem) {
    return null
  }

  const isDefaultSystem = isDefault && isSystem
  const label = isDefaultSystem
    ? t('clientTemplates.defaultSystem', { defaultValue: 'Default System' })
    : isDefault
      ? t('clientTemplates.default', { defaultValue: 'Default' })
      : t('clientTemplates.system', { defaultValue: 'System' })
  const markerStyleClassName = isDefaultSystem
    ? 'border-amber-300/70 bg-amber-100/80 text-amber-700 dark:border-amber-500/50 dark:bg-amber-500/15 dark:text-amber-300'
    : isDefault
      ? 'border-sky-300/70 bg-sky-100/80 text-sky-700 dark:border-sky-500/50 dark:bg-sky-500/15 dark:text-sky-300'
      : 'border-violet-300/70 bg-violet-100/80 text-violet-700 dark:border-violet-500/50 dark:bg-violet-500/15 dark:text-violet-300'

  return (
    <TooltipProvider delayDuration={120}>
      <div className={cn('flex items-center gap-1', className)}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span aria-label={label} className={cn(baseMarkerClassName, markerStyleClassName)}>
              <Merge className="h-3 w-3 fill-current" />
            </span>
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}
