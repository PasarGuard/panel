import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface ApplySectionProps {
  title: string
  description: string
  badges: Array<{
    icon: LucideIcon
    label: string
    value?: string | number
  }>
  buttonLabel: string
  buttonIcon: LucideIcon
  onApply: () => void
  disabled?: boolean
  isLoading?: boolean
  variant?: 'default' | 'destructive'
  className?: string
}

export function ApplySection({ title, description, badges, buttonLabel, buttonIcon: ButtonIcon, onApply, disabled = false, isLoading = false, variant = 'default', className }: ApplySectionProps) {
  const { t } = useTranslation()

  return (
    <Card className={cn('bg-card transition-shadow hover:shadow-md', className)}>
      <CardContent className="flex flex-col items-center justify-center gap-3 px-3 py-4 sm:gap-4 sm:px-4 sm:py-5 md:gap-5 md:px-6 md:py-6 lg:gap-6 lg:py-8">
        <div className="space-y-1 text-center sm:space-y-1.5 md:space-y-2">
          <h3 className="text-sm font-semibold sm:text-base md:text-lg">{title}</h3>
          <p className="text-muted-foreground px-2 text-xs sm:text-sm">{description}</p>
        </div>

        <div className="flex w-full flex-wrap items-center justify-center gap-1.5 sm:gap-2 md:gap-3">
          {badges.map((badge, index) => (
            <Badge key={index} variant="outline" className="flex items-center gap-1 px-2 py-0.5 text-[10px] sm:gap-1.5 sm:px-2.5 sm:py-1 sm:text-xs md:text-sm">
              <badge.icon className="h-2.5 w-2.5 shrink-0 sm:h-3 sm:w-3" />
              <span className="max-w-[150px] truncate whitespace-nowrap sm:max-w-none">{badge.value !== undefined ? `${badge.label}: ${badge.value}` : badge.label}</span>
            </Badge>
          ))}
        </div>

        <Button onClick={onApply} className="flex w-full items-center justify-center gap-2 px-4 sm:w-auto sm:px-6" disabled={disabled || isLoading} size="lg" variant={variant}>
          <ButtonIcon className="h-3.5 w-3.5 shrink-0 sm:h-4 sm:w-4" />
          <span className="text-sm whitespace-nowrap sm:text-base">{isLoading ? t('applying', { defaultValue: 'Applying...' }) : buttonLabel}</span>
        </Button>
      </CardContent>
    </Card>
  )
}
