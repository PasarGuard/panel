import { useEffect, useMemo } from 'react'

import { CHART_PERIOD_OVERRIDE_AUTO, type ChartPeriodLimitOptions, type ChartPeriodOverride, type ChartRangeSelection, getAllowedChartPeriods } from '@/utils/chart-period-utils'

/**
 * Limits a chart's period override to the periods its range allows.
 * Returns the allowed periods for the PeriodSelector and the override to query with:
 * when the range changes so the picked period is no longer allowed, it falls back to auto.
 */
export function useChartPeriodLimit(range: ChartRangeSelection, periodOverride: ChartPeriodOverride, setPeriodOverride: (value: ChartPeriodOverride) => void, options?: ChartPeriodLimitOptions) {
  const { shortcut } = range
  const fromMs = range.customRange?.from?.getTime()
  const toMs = range.customRange?.to?.getTime()
  const recordBucketMinutes = options?.recordBucketMinutes

  const allowedPeriods = useMemo(
    () =>
      getAllowedChartPeriods(
        {
          shortcut,
          customRange: fromMs !== undefined && toMs !== undefined ? { from: new Date(fromMs), to: new Date(toMs) } : undefined,
        },
        { recordBucketMinutes },
      ),
    [shortcut, fromMs, toMs, recordBucketMinutes],
  )

  const isAllowed = allowedPeriods.includes(periodOverride)

  useEffect(() => {
    if (!isAllowed) setPeriodOverride(CHART_PERIOD_OVERRIDE_AUTO)
  }, [isAllowed, setPeriodOverride])

  return {
    allowedPeriods,
    periodOverride: isAllowed ? periodOverride : CHART_PERIOD_OVERRIDE_AUTO,
  }
}
