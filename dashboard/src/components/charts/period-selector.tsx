import { useTranslation } from 'react-i18next'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import {
  CHART_PERIOD_OVERRIDE_AUTO,
  CHART_PERIOD_VALUES,
  type ChartPeriodOverride,
  getChartPeriodLabel,
} from '@/utils/chart-period-utils'

type PeriodSelectorProps = {
  value: ChartPeriodOverride
  onValueChange: (value: ChartPeriodOverride) => void
  className?: string
}

export default function PeriodSelector({ value, onValueChange, className }: PeriodSelectorProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <Select value={value} onValueChange={next => onValueChange(next as ChartPeriodOverride)}>
      <SelectTrigger
        aria-label={t('statistics.period', { defaultValue: 'Period' })}
        className={cn('h-9 w-[5.75rem] shrink-0 px-2 py-0 text-xs sm:w-[7rem] [&>span]:truncate', className)}
        dir={dir}
      >
        <SelectValue>{getChartPeriodLabel(value, t)}</SelectValue>
      </SelectTrigger>
      <SelectContent dir={dir}>
        <SelectItem value={CHART_PERIOD_OVERRIDE_AUTO}>{getChartPeriodLabel(CHART_PERIOD_OVERRIDE_AUTO, t)}</SelectItem>
        {CHART_PERIOD_VALUES.map(period => (
          <SelectItem key={period} value={period}>
            {getChartPeriodLabel(period, t)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
