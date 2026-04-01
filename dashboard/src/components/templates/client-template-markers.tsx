import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { Shield, Star } from 'lucide-react'
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

  return (
    <TooltipProvider delayDuration={120}>
      <div className={cn('flex items-center gap-1', className)}>
        {isDefault && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                aria-label={t('default', { defaultValue: 'Default' })}
                className={cn(baseMarkerClassName, 'border-border/60 bg-muted/70 text-foreground/80')}
              >
                <Star className="h-3 w-3 fill-current" />
              </span>
            </TooltipTrigger>
            <TooltipContent>{t('default', { defaultValue: 'Default' })}</TooltipContent>
          </Tooltip>
        )}
        {isSystem && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                aria-label={t('system', { defaultValue: 'System' })}
                className={cn(baseMarkerClassName, 'border-border/60 bg-background text-muted-foreground')}
              >
                <Shield className="h-3 w-3" />
              </span>
            </TooltipTrigger>
            <TooltipContent>{t('system', { defaultValue: 'System' })}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </TooltipProvider>
  )
}
