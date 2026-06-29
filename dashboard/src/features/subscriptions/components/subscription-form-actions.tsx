import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

export interface SubscriptionFormActionsProps {
  onCancel: () => void
  isSaving: boolean
  className?: string
}

export function SubscriptionFormActions({ onCancel, isSaving, className }: SubscriptionFormActionsProps) {
  const { t } = useTranslation()

  return (
    <div className={cn('mt-3 flex flex-col gap-2 border-t pt-3 sm:mt-6 sm:flex-row sm:gap-3 sm:pt-6', className)}>
      <div className="flex-1"></div>
      <div className="flex flex-col gap-2 sm:shrink-0 sm:flex-row sm:gap-3">
        <Button type="button" variant="outline" onClick={onCancel} className="w-full min-w-[100px] sm:w-auto" disabled={isSaving}>
          {t('cancel')}
        </Button>
        <Button type="submit" disabled={isSaving} isLoading={isSaving} loadingText={t('saving')} className="w-full min-w-[100px] sm:w-auto">
          {t('save')}
        </Button>
      </div>
    </div>
  )
}
