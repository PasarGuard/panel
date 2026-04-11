'use client'

import { DatePicker } from '@/components/common/date-picker'
import { formatDateByLocale } from '@/utils/datePickerUtils'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

type BulkExpiredDateFiltersProps = {
  expiredAfter: Date | undefined
  expiredBefore: Date | undefined
  onExpiredAfterChange: (date: Date | undefined) => void
  onExpiredBeforeChange: (date: Date | undefined) => void
  className?: string
}

/**
 * Optional expired-on date range when filtering by Expired status (BulkUser expired_after / expired_before).
 * Uses the same DatePicker behavior as cleanup settings and other app surfaces.
 */
export function BulkExpiredDateFilters({
  expiredAfter,
  expiredBefore,
  onExpiredAfterChange,
  onExpiredBeforeChange,
  className,
}: BulkExpiredDateFiltersProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const isPersianLocale = i18n.language === 'fa'
  const formatDate = (date: Date) => formatDateByLocale(date, isPersianLocale, false)

  return (
    <div className={cn('space-y-3', className)} dir={dir}>
      <p className="text-xs text-muted-foreground sm:text-sm">{t('bulk.expiredFilterHint')}</p>
      <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <DatePicker
            mode="single"
            date={expiredAfter}
            onDateChange={onExpiredAfterChange}
            label={t('bulk.expiredFilterAfter')}
            placeholder={t('bulk.expiredFilterAfterPlaceholder')}
            minDate={new Date('1900-01-01')}
            maxDate={new Date()}
            formatDate={formatDate}
            side="bottom"
            align="center"
            className="[&_label]:text-xs sm:[&_label]:text-sm [&_button]:text-xs sm:[&_button]:text-sm"
          />
        </div>
        <div className="space-y-2">
          <DatePicker
            mode="single"
            date={expiredBefore}
            onDateChange={onExpiredBeforeChange}
            label={t('bulk.expiredFilterBefore')}
            placeholder={t('bulk.expiredFilterBeforePlaceholder')}
            minDate={new Date('1900-01-01')}
            maxDate={new Date()}
            formatDate={formatDate}
            side="bottom"
            align="center"
            className="[&_label]:text-xs sm:[&_label]:text-sm [&_button]:text-xs sm:[&_button]:text-sm"
          />
        </div>
      </div>
    </div>
  )
}
