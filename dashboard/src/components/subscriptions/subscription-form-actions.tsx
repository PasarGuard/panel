import { Button } from '@/components/ui/button'
import { useTranslation } from 'react-i18next'

export interface SubscriptionFormActionsProps {
  onCancel: () => void
  isSaving: boolean
}

export function SubscriptionFormActions({ onCancel, isSaving }: SubscriptionFormActionsProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-2 pt-3 sm:flex-row sm:gap-3 sm:pt-4">
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
