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

  return (
    <TooltipProvider delayDuration={120}>
      <div className={cn('flex items-center gap-1', className)}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              aria-label={label}
              className={cn(baseMarkerClassName, 'border-border/60 bg-muted/70 text-foreground/80')}
            >
              <Merge className="h-3 w-3 fill-current" />
            </span>
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}
