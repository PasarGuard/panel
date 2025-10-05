import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import useDirDetection from '@/hooks/use-dir-detection'
import { LucideIcon, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface PageHeaderProps {
  title: string
  description?: string
  buttonText?: string
  onButtonClick?: () => void
  buttonIcon?: LucideIcon
  buttonTooltip?: string
}

export default function PageHeader({ title, description, buttonText, onButtonClick, buttonIcon: Icon = Plus, buttonTooltip }: PageHeaderProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  return (
    <div dir={dir} className="w-full mx-auto py-4 md:pt-6 gap-4 flex items-start justify-between flex-row px-4">
      <div className="flex flex-col gap-y-1">
        <h1 className="font-medium text-lg sm:text-xl">{t(title)}</h1>
        {description && <span className="whitespace-normal text-muted-foreground text-xs sm:text-sm">{t(description)}</span>}
      </div>
      {buttonText && onButtonClick && (
        <div>
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
