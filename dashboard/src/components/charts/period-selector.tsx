import { useTranslation } from 'react-i18next'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
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
  /** Periods that can be picked for the current range. Others are shown disabled. All are allowed when omitted. */
  allowedPeriods?: readonly ChartPeriodOverride[]
}

export default function PeriodSelector({ value, onValueChange, className, allowedPeriods }: PeriodSelectorProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const disabledHint = t('statistics.periodTooFineForRange', { defaultValue: 'Too many points for this range. Pick a shorter range.' })

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
        <TooltipProvider delayDuration={150}>
          {CHART_PERIOD_VALUES.map(period => {
            const disabled = allowedPeriods ? !allowedPeriods.includes(period) : false
            const item = (
              <SelectItem key={period} value={period} disabled={disabled}>
                {getChartPeriodLabel(period, t)}
              </SelectItem>
            )
            if (!disabled) return item

            // A disabled item gets no pointer events, so the wrapper carries the tooltip
            return (
              <Tooltip key={period}>
                <TooltipTrigger asChild>
                  <div>{item}</div>
                </TooltipTrigger>
                <TooltipContent side="left" dir={dir}>
                  {disabledHint}
                </TooltipContent>
              </Tooltip>
            )
          })}
        </TooltipProvider>
      </SelectContent>
    </Select>
  )
}
