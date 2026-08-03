import dayjs from '@/lib/dayjs'
import { Period } from '@/service/api'
import type { TFunction } from 'i18next'
import { DateRange } from 'react-day-picker'
import { getPeriodFromDateRange } from './datePickerUtils'
import { formatOffsetDateTime, formatOffsetEndOfDay, formatOffsetStartOfDay, parseDateInput } from './dateTimeParsing'
import { getDateRangeFromShortcut } from './timeShortcutUtils'

export type PeriodOption = {
  label: string
  value: string
  period: Period
  hours?: number
  days?: number
  months?: number
  allTime?: boolean
}

const PERIOD_KEYS = [
  { key: '24h', period: Period.hour, amount: 24, unit: 'hour' },
  { key: '3d', period: Period.day, amount: 3, unit: 'day' },
  { key: '7d', period: Period.day, amount: 7, unit: 'day' },
  { key: '1m', period: Period.day, amount: 1, unit: 'month' },
  { key: '3m', period: Period.day, amount: 3, unit: 'month' },
] as const

export const TRAFFIC_SHORTCUT_KEYS = ['1h', '2h', '4h', '6h', '12h', '24h', '2d', '3d', '5d', '1w', '2w', '1m', 'all'] as const
export type TrafficShortcutKey = (typeof TRAFFIC_SHORTCUT_KEYS)[number]

export const CHART_PERIOD_OVERRIDE_AUTO = 'auto' as const
export type ChartPeriodOverride = typeof CHART_PERIOD_OVERRIDE_AUTO | Period
export const CHART_PERIOD_VALUES = [Period.minute, Period.hour, Period.day, Period.month] as const

export const resolvePeriodOverride = (override?: ChartPeriodOverride): Period | undefined => {
  if (!override || override === CHART_PERIOD_OVERRIDE_AUTO) return undefined
  return override
}

const capitalizeLabel = (label: string) => (label ? label.charAt(0).toLocaleUpperCase() + label.slice(1) : label)

export const getChartPeriodLabel = (period: ChartPeriodOverride, t: TFunction): string => {
  if (period === CHART_PERIOD_OVERRIDE_AUTO) {
    return t('statistics.periodAuto', { defaultValue: 'Auto' })
  }

  if (period === Period.minute) {
    return capitalizeLabel(t('time.minute', { defaultValue: 'minute' }))
  }

  if (period === Period.hour) {
    return capitalizeLabel(t('time.hour', { defaultValue: 'hour' }))
  }

  if (period === Period.day) {
    return capitalizeLabel(t('time.day', { defaultValue: 'day' }))
  }

  return capitalizeLabel(t('time.month', { defaultValue: 'month' }))
}

const isPersianLanguage = (language: string) => language.toLowerCase().startsWith('fa')

const getLocale = (language: string) => (isPersianLanguage(language) ? 'fa-IR' : 'en-US')

export const buildPeriodOptions = (t: TFunction): PeriodOption[] => [
  ...PERIOD_KEYS.map(option => ({
    label: `${option.amount} ${t(`time.${option.unit}${option.amount > 1 ? 's' : ''}`)}`,
    value: option.key,
    period: option.period,
    hours: option.unit === 'hour' ? option.amount : undefined,
    days: option.unit === 'day' ? option.amount : undefined,
    months: option.unit === 'month' ? option.amount : undefined,
  })),
  {
    label: t('alltime', { defaultValue: 'All Time' }),
    value: 'all',
    period: Period.day,
    allTime: true,
  },
]

export const getDefaultPeriodOption = (options: PeriodOption[]) => options[2] ?? options[0]

export const getDateRangeForPeriodOption = (periodOption: PeriodOption) => {
  const now = dayjs()
  let start: dayjs.Dayjs

  if (periodOption.allTime) {
    start = dayjs(new Date(2000, 0, 1, 0, 0, 0, 0))
  } else if (periodOption.hours) {
    start = now.subtract(periodOption.hours, 'hour')
  } else if (periodOption.days) {
    const daysToSubtract = periodOption.days === 7 ? 6 : periodOption.days === 3 ? 2 : periodOption.days === 1 ? 0 : periodOption.days
    start = now.subtract(daysToSubtract, 'day').startOf('day')
  } else if (periodOption.months) {
    start = now.subtract(periodOption.months, 'month').startOf('day')
  } else {
    start = now
  }

  return {
    startDate: formatOffsetDateTime(start.toDate()),
    endDate: formatOffsetDateTime(now.toDate()),
  }
}

export const toChartQueryEndDate = (endDate: string) => formatOffsetEndOfDay(endDate)

export const toChartPeriodStart = (periodStart: string | Date) => parseDateInput(periodStart)

const toChartDisplayDate = (periodStart: string | Date, includeTime: boolean) => {
  const parsed = toChartPeriodStart(periodStart)

  return new Date(
    parsed.year(),
    parsed.month(),
    parsed.date(),
    includeTime ? parsed.hour() : 0,
    includeTime ? parsed.minute() : 0,
    includeTime ? parsed.second() : 0,
    includeTime ? parsed.millisecond() : 0,
  )
}

export type ChartLabelRangeHint = {
  shortcut?: string
  customRange?: DateRange
  hours?: number
  days?: number
  months?: number
  allTime?: boolean
}

const getOptionSpanDays = (periodOption: PeriodOption): number | null => {
  if (periodOption.allTime) return Number.POSITIVE_INFINITY
  if (periodOption.months) return periodOption.months * 30
  if (periodOption.days) return periodOption.days
  if (periodOption.hours) return periodOption.hours / 24
  return null
}

/** Approximate span in days for label formatting decisions. */
export const getChartLabelSpanDays = (rangeHint?: ChartLabelRangeHint, periodOption?: PeriodOption): number | null => {
  if (rangeHint?.customRange?.from && rangeHint.customRange?.to) {
    return Math.abs(rangeHint.customRange.to.getTime() - rangeHint.customRange.from.getTime()) / (1000 * 60 * 60 * 24)
  }

  if (rangeHint?.allTime) return Number.POSITIVE_INFINITY
  if (rangeHint?.months) return rangeHint.months * 30
  if (rangeHint?.days) return rangeHint.days
  if (rangeHint?.hours) return rangeHint.hours / 24

  if (rangeHint?.shortcut) {
    const meta = getShortcutMeta(rangeHint.shortcut)
    if (meta.allTime) return Number.POSITIVE_INFINITY
    if (meta.months) return meta.months * 30
    if (meta.days) return meta.days
    if (meta.hours) return meta.hours / 24
  }

  return periodOption ? getOptionSpanDays(periodOption) : null
}

const formatAxisDateLabel = (periodStart: string | Date, language: string) => {
  const locale = getLocale(language)
  return toChartDisplayDate(periodStart, false).toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
  })
}

const formatAxisDateTimeLabel = (periodStart: string | Date, language: string) => {
  const locale = getLocale(language)
  return toChartDisplayDate(periodStart, true)
    .toLocaleString(locale, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    .replace(',', '')
}

export const formatPeriodLabel = (periodStart: string, periodOption: PeriodOption, language: string, rangeHint?: ChartLabelRangeHint): string => {
  const d = toChartPeriodStart(periodStart)
  const spanDays = getChartLabelSpanDays(rangeHint, periodOption)
  const isWeekOrLonger = spanDays != null && spanDays >= 7

  if (periodOption.period === Period.minute) {
    // 1w+ minute candles: date under the axis (HH:mm is useless across many days).
    if (isWeekOrLonger) return formatAxisDateLabel(periodStart, language)
    if (spanDays != null && spanDays >= 1) return formatAxisDateTimeLabel(periodStart, language)
    return d.format('HH:mm')
  }

  if (periodOption.period === Period.hour) {
    // Week+ ranges: prefer date; shorter multi-day keeps date+time.
    if (isWeekOrLonger) return formatAxisDateLabel(periodStart, language)
    return formatAxisDateTimeLabel(periodStart, language)
  }

  if (periodOption.period === Period.month) {
    const locale = getLocale(language)
    return toChartDisplayDate(periodStart, false).toLocaleString(locale, {
      year: 'numeric',
      month: 'short',
    })
  }

  if (periodOption.period === Period.day) {
    return formatAxisDateLabel(periodStart, language)
  }

  if (periodOption.hours) {
    return d.format('HH:mm')
  }

  return formatAxisDateLabel(periodStart, language)
}

export const formatTooltipDate = (periodStart: string | Date, period: Period, language: string): string => {
  const locale = getLocale(language)

  if (period === Period.month) {
    const localDate = toChartDisplayDate(periodStart, false)
    return localDate.toLocaleDateString(locale, {
      year: 'numeric',
      month: 'short',
    })
  }

  if (period === Period.day) {
    const localDate = toChartDisplayDate(periodStart, false)
    return localDate.toLocaleDateString(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  }

  return toChartDisplayDate(periodStart, true)
    .toLocaleString(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    .replace(',', '')
}

export const getXAxisInterval = (periodOption: PeriodOption, dataLength: number) => {
  if (periodOption.hours) {
    const targetLabels = 8
    return Math.max(1, Math.floor(dataLength / targetLabels))
  }

  if (periodOption.months || periodOption.allTime) {
    const targetLabels = 5
    return Math.max(1, Math.floor(dataLength / targetLabels))
  }

  if (periodOption.days && periodOption.days > 7) {
    const targetLabels = periodOption.days === 30 ? 10 : 8
    return Math.max(1, Math.floor(dataLength / targetLabels))
  }

  return 0
}

const getTargetXAxisLabels = (period: Period, windowWidth: number) => {
  const isNarrow = windowWidth < 500

  if (period === Period.minute) return isNarrow ? 4 : 6
  if (period === Period.hour) return isNarrow ? 5 : 8
  if (period === Period.month) return isNarrow ? 4 : 6
  return isNarrow ? 5 : 10
}

/** Cap x-axis ticks so candle labels stay readable when many points are present. */
export const getDenseXAxisInterval = (dataLength: number, targetLabels: number) => {
  if (dataLength <= targetLabels) return 0
  return Math.max(1, Math.ceil(dataLength / targetLabels) - 1)
}

type ChartXAxisIntervalParams = {
  dataLength: number
  period: Period
  shortcut?: string
  windowWidth?: number
  customRange?: DateRange
  periodOverride?: Period
}

export const getChartXAxisInterval = ({
  dataLength,
  period,
  shortcut,
  windowWidth = 1024,
  customRange,
  periodOverride,
}: ChartXAxisIntervalParams) => {
  const targetLabels = getTargetXAxisLabels(period, windowWidth)
  const densityInterval = getDenseXAxisInterval(dataLength, targetLabels)

  if (customRange?.from && customRange?.to) {
    if (period === Period.hour || period === Period.minute || period === Period.month) {
      return densityInterval
    }

    const daysDiff = Math.ceil(Math.abs(customRange.to.getTime() - customRange.from.getTime()) / (1000 * 60 * 60 * 24))
    if (daysDiff > 30) return getDenseXAxisInterval(dataLength, Math.min(targetLabels, 5))
    if (daysDiff > 7) return getDenseXAxisInterval(dataLength, targetLabels)
    return densityInterval
  }

  if (shortcut) {
    const shortcutInterval = getXAxisIntervalForShortcut(shortcut, dataLength, {
      minuteForOneHour: true,
      ...(periodOverride ? { periodOverride } : {}),
    })
    // Always respect density so overrides like 1w + Hour don't render every tick.
    return Math.max(densityInterval, shortcutInterval)
  }

  return densityInterval
}

type UsageStatWithPeriodStart = {
  period_start: string
}

const SHORTCUT_PATTERN = /^(\d+)([hdwm])$/

type ShortcutPeriodOptions = {
  minuteForOneHour?: boolean
  periodOverride?: Period
}

export const getShortcutPeriod = (shortcut: string, options?: ShortcutPeriodOptions): Period => {
  if (options?.periodOverride) {
    return options.periodOverride
  }

  if (shortcut === '1h' && options?.minuteForOneHour) {
    return Period.minute
  }

  if (shortcut.endsWith('h')) {
    return Period.hour
  }

  return Period.day
}

export const getShortcutMeta = (shortcut: string) => {
  if (shortcut === 'all') {
    return { allTime: true }
  }

  const match = shortcut.match(SHORTCUT_PATTERN)
  if (!match) return {}

  const amount = Number.parseInt(match[1], 10)
  const unit = match[2]

  if (!Number.isFinite(amount) || amount <= 0) return {}

  if (unit === 'h') {
    return { hours: amount }
  }

  if (unit === 'd') {
    return { days: amount }
  }

  if (unit === 'w') {
    return { days: amount * 7 }
  }

  return { months: amount }
}

export const getXAxisIntervalForShortcut = (shortcut: string, dataLength: number, options?: ShortcutPeriodOptions) => {
  const meta = getShortcutMeta(shortcut)
  const period: Period = getShortcutPeriod(shortcut, options)
  const isDensePeriod = period === Period.minute || period === Period.hour || period === Period.month

  // When aggregation is denser than the shortcut's natural bucket, prefer period-based thinning.
  if (isDensePeriod || options?.periodOverride) {
    return getDenseXAxisInterval(dataLength, getTargetXAxisLabels(period, 1024))
  }

  return getXAxisInterval(
    {
      label: shortcut,
      value: shortcut,
      period,
      hours: 'hours' in meta ? meta.hours : undefined,
      days: 'days' in meta ? meta.days : undefined,
      months: 'months' in meta ? meta.months : undefined,
      allTime: 'allTime' in meta ? meta.allTime : undefined,
    },
    dataLength,
  )
}

type ChartQueryRange = {
  period: Period
  startDate: string
  endDate: string
}

const buildChartQueryRange = (period: Period, from: Date, to: Date): ChartQueryRange => {
  const useDayBounds = period === Period.day || period === Period.month
  const startDate = useDayBounds ? formatOffsetStartOfDay(from) : formatOffsetDateTime(from)
  const endDate = useDayBounds ? formatOffsetEndOfDay(to) : formatOffsetDateTime(to)

  return { period, startDate, endDate }
}

export const getChartQueryRangeFromShortcut = (shortcut: string, now = new Date(), options?: ShortcutPeriodOptions): ChartQueryRange => {
  const safeRange = getDateRangeFromShortcut(shortcut, now)
  const from = safeRange?.from ?? now
  const to = safeRange?.to ?? now
  const period = getShortcutPeriod(shortcut, options)

  return buildChartQueryRange(period, from, to)
}

export const getChartQueryRangeFromDateRange = (range: DateRange, fallbackShortcut: string = '1w', options?: ShortcutPeriodOptions): ChartQueryRange => {
  if (!range.from || !range.to) {
    return getChartQueryRangeFromShortcut(fallbackShortcut, new Date(), options)
  }

  const period = options?.periodOverride ?? getPeriodFromDateRange(range)
  return buildChartQueryRange(period, range.from, range.to)
}

export const formatPeriodLabelForPeriod = (periodStart: string, period: Period, language: string, rangeHint?: ChartLabelRangeHint) => {
  const fromShortcut = rangeHint?.shortcut ? getShortcutMeta(rangeHint.shortcut) : {}
  const option: PeriodOption = {
    label: period,
    value: period,
    period,
    hours: rangeHint?.hours ?? ('hours' in fromShortcut ? fromShortcut.hours : undefined),
    days: rangeHint?.days ?? ('days' in fromShortcut ? fromShortcut.days : undefined),
    months: rangeHint?.months ?? ('months' in fromShortcut ? fromShortcut.months : undefined),
    allTime: rangeHint?.allTime ?? ('allTime' in fromShortcut ? fromShortcut.allTime : undefined),
  }

  return formatPeriodLabel(periodStart, option, language, rangeHint)
}

export const pickStatsArray = <T extends UsageStatWithPeriodStart>(stats: Record<string, T[]> | T[] | undefined, preferredKeys: string[] = ['-1']): T[] => {
  if (!stats) return []

  if (Array.isArray(stats)) {
    return stats
  }

  for (const key of preferredKeys) {
    const candidate = stats[key]
    if (Array.isArray(candidate)) {
      return candidate
    }
  }

  const firstKey = Object.keys(stats)[0]
  if (!firstKey) return []
  return Array.isArray(stats[firstKey]) ? stats[firstKey] : []
}

export const toStatsRecord = <T extends UsageStatWithPeriodStart>(stats: Record<string, T[]> | T[] | undefined): Record<string, T[]> => {
  if (!stats) return {}
  if (Array.isArray(stats)) return { '-1': stats }
  return stats
}
