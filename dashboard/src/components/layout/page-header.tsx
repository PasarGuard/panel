import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import useDirDetection from '@/hooks/use-dir-detection'
import { getDocsUrl } from '@/utils/docs-url'
import Snowfall from '@/components/common/snowfall'
import { cn } from '@/lib/utils'
import { HelpCircle, LucideIcon, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router'

interface PageHeaderProps {
  title: string
  description?: string
  buttonText?: string
  onButtonClick?: () => void
  buttonIcon?: LucideIcon
  buttonTooltip?: string
  tutorialUrl?: string
  className?: string
}

export default function PageHeader({
  title,
  description,
  buttonText,
  onButtonClick,
  buttonIcon: Icon = Plus,
  buttonTooltip,
  tutorialUrl,
  className,
}: PageHeaderProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const location = useLocation()

  // Generate tutorial URL if not provided
  const docsUrl = tutorialUrl || getDocsUrl(location.pathname)

  return (
    <div
      dir={dir}
      className={cn('relative mx-auto flex w-full flex-row items-start justify-between gap-4 overflow-hidden px-4 py-4 md:pt-6', className)}
    >
      <Snowfall className="snowfall--header" />
      <div className="relative z-10 flex min-w-0 flex-1 flex-col gap-y-1">
        <div className="flex min-w-0 items-center gap-2.5">
          <h1 className="truncate text-lg font-medium sm:text-xl">{t(title)}</h1>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={docsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md border-0 text-primary transition-colors hover:border-2 hover:border-primary/40 hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  aria-label={t('tutorial', { defaultValue: 'View tutorial' })}
                >
                  <HelpCircle className="h-4 w-4" />
                </a>
              </TooltipTrigger>
              <TooltipContent>
                <p>{t('tutorial', { defaultValue: 'View tutorial' })}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        {description && <span className="whitespace-normal text-xs text-muted-foreground sm:text-sm">{t(description)}</span>}
      </div>
      {buttonText && onButtonClick && (
        <div className="relative z-10 shrink-0">
          {buttonTooltip ? (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button className="flex items-center" onClick={onButtonClick} size="sm">
                    {Icon && <Icon />}
                    <span>{t(buttonText)}</span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{buttonTooltip}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <Button className="flex items-center" onClick={onButtonClick} size="sm">
              {Icon && <Icon />}
              <span>{t(buttonText)}</span>
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
