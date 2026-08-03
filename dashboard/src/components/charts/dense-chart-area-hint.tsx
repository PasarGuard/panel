import { useState } from 'react'
import { Link } from 'react-router'
import { AreaChart, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useChartViewType } from '@/hooks/use-chart-view-type'
import { cn } from '@/lib/utils'
import { CHART_AREA_SUGGESTION_POINT_LIMIT } from '@/utils/chart-performance'
import { setChartViewTypePreference } from '@/utils/userPreferenceStorage'

const DISMISS_STORAGE_KEY = 'pg-dense-chart-area-hint-dismissed'

type DenseChartAreaHintProps = {
  pointCount: number
  className?: string
}

/** Suggest Theme → Area chart when bar mode has too many candles. */
export default function DenseChartAreaHint({ pointCount, className }: DenseChartAreaHintProps) {
  const { t } = useTranslation()
  const chartViewType = useChartViewType()
  const [dismissed, setDismissed] = useState(() => {
    if (typeof sessionStorage === 'undefined') return false
    return sessionStorage.getItem(DISMISS_STORAGE_KEY) === '1'
  })

  if (dismissed || chartViewType !== 'bar' || pointCount <= CHART_AREA_SUGGESTION_POINT_LIMIT) {
    return null
  }

  const handleUseArea = () => {
    setChartViewTypePreference('area')
  }

  const handleDismiss = () => {
    setDismissed(true)
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(DISMISS_STORAGE_KEY, '1')
    }
  }

  return (
    <div
      className={cn(
        'border-border/60 bg-muted/40 text-muted-foreground mb-3 flex flex-col gap-2 rounded-md border px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between sm:gap-3',
        className,
      )}
      role="status"
    >
      <div className="flex min-w-0 items-start gap-2">
        <AreaChart className="text-primary mt-0.5 h-3.5 w-3.5 shrink-0" />
        <p className="text-pretty leading-relaxed">
          {t('statistics.denseChartAreaHint', {
            count: pointCount,
            defaultValue: 'This chart has {{count}} candles. Area charts from Theme settings usually perform better with large ranges.',
          })}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5 self-end sm:self-auto">
        <Button type="button" size="sm" variant="secondary" className="h-7 px-2.5 text-xs" onClick={handleUseArea}>
          {t('statistics.useAreaChart', { defaultValue: 'Use area chart' })}
        </Button>
        <Button type="button" size="sm" variant="ghost" className="h-7 px-2.5 text-xs" asChild>
          <Link to="/settings/theme">{t('theme.title', { defaultValue: 'Theme' })}</Link>
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-muted-foreground h-7 w-7"
          onClick={handleDismiss}
          aria-label={t('close', { defaultValue: 'Close' })}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
