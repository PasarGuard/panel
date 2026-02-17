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
  { key: '30d', period: Period.day, amount: 30, unit: 'day' },
  { key: '1m', period: Period.day, amount: 1, unit: 'month' },
  { key: '3m', period: Period.day, amount: 3, unit: 'month' },
] as const

export const TRAFFIC_SHORTCUT_KEYS = ['1h', '2h', '4h', '6h', '12h', '24h', '2d', '3d', '5d', '1w', '2w', '1m', 'all'] as const
export type TrafficShortcutKey = (typeof TRAFFIC_SHORTCUT_KEYS)[number]

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

export const formatPeriodLabel = (periodStart: string, periodOption: PeriodOption, language: string): string => {
  const locale = getLocale(language)
  const d = toChartPeriodStart(periodStart)

  if (periodOption.hours) {
    return d.format('HH:mm')
  }

  if (periodOption.period === Period.day) {
    const localDate = toChartDisplayDate(periodStart, false)
    return localDate.toLocaleString(locale, {
      month: '2-digit',
      day: '2-digit',
    })
  }

  return toChartDisplayDate(periodStart, true).toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
  })
}

export const formatTooltipDate = (periodStart: string | Date, period: Period, language: string): string => {
  const locale = getLocale(language)

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

type UsageStatWithPeriodStart = {
  period_start: string
}

const SHORTCUT_PATTERN = /^(\d+)([hdwm])$/

type ShortcutPeriodOptions = {
  minuteForOneHour?: boolean
}

export const getShortcutPeriod = (shortcut: string, options?: ShortcutPeriodOptions): Period => {
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
  const startDate = period === Period.day ? formatOffsetStartOfDay(from) : formatOffsetDateTime(from)
  const endDate = period === Period.day ? formatOffsetEndOfDay(to) : formatOffsetDateTime(to)

  return { period, startDate, endDate }
}

export const getChartQueryRangeFromShortcut = (shortcut: string, now = new Date(), options?: ShortcutPeriodOptions): ChartQueryRange => {
  const safeRange = getDateRangeFromShortcut(shortcut, now)
  const from = safeRange?.from ?? now
  const to = safeRange?.to ?? now
  const period = getShortcutPeriod(shortcut, options)

  return buildChartQueryRange(period, from, to)
}

export const getChartQueryRangeFromDateRange = (range: DateRange, fallbackShortcut: string = '1w'): ChartQueryRange => {
  if (!range.from || !range.to) {
    return getChartQueryRangeFromShortcut(fallbackShortcut)
  }

  const period = getPeriodFromDateRange(range)
  return buildChartQueryRange(period, range.from, range.to)
}

export const formatPeriodLabelForPeriod = (periodStart: string, period: Period, language: string) => {
  const option: PeriodOption = {
    label: period,
    value: period,
    period,
    ...(period === Period.hour || period === Period.minute ? { hours: 1 } : {}),
  }

  return formatPeriodLabel(periodStart, option, language)
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
