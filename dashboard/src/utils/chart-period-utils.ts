import dayjs from '@/lib/dayjs'
import { Period } from '@/service/api'
import { dateUtils } from '@/utils/dateFormatter'
import type { TFunction } from 'i18next'
import { DateRange } from 'react-day-picker'
import { getPeriodFromDateRange } from './datePickerUtils'
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
    start = dayjs('2000-01-01T00:00:00Z')
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
    startDate: dateUtils.toSystemTimezoneISO(start.toDate()),
    endDate: dateUtils.toSystemTimezoneISO(now.toDate()),
  }
}

export const toChartQueryEndDate = (endDate: string) => dateUtils.toSystemTimezoneISO(dateUtils.toSystemTimezoneDayjs(endDate).endOf('day').toDate())

export const toChartPeriodStart = (periodStart: string | Date) => dateUtils.toSystemTimezoneDayjs(periodStart)

export const formatPeriodLabel = (periodStart: string, periodOption: PeriodOption, language: string): string => {
  const locale = getLocale(language)
  const d = toChartPeriodStart(periodStart)

  if (periodOption.hours) {
    return d.format('HH:mm')
  }

  if (periodOption.period === Period.day) {
    const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
    return localDate.toLocaleString(locale, {
      month: '2-digit',
      day: '2-digit',
    })
  }

  return d.toDate().toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
  })
}

export const formatTooltipDate = (periodStart: string | Date, period: Period, language: string): string => {
  const locale = getLocale(language)
  const d = toChartPeriodStart(periodStart)

  if (period === Period.day) {
    const localDate = new Date(d.year(), d.month(), d.date(), 0, 0, 0)
    return localDate.toLocaleDateString(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  }

  return d
    .toDate()
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

export const getChartQueryRangeFromShortcut = (shortcut: string, now = new Date(), options?: ShortcutPeriodOptions): ChartQueryRange => {
  const safeRange = getDateRangeFromShortcut(shortcut, now)
  const from = safeRange?.from ?? now
  const to = safeRange?.to ?? now
  const period = getShortcutPeriod(shortcut, options)

  const startDate =
    period === Period.day
      ? dateUtils.toSystemTimezoneISO(dateUtils.toSystemTimezoneDayjs(from).startOf('day').toDate())
      : dateUtils.toSystemTimezoneISO(from)
  const endDate = period === Period.day ? dateUtils.toSystemTimezoneISO(dateUtils.toSystemTimezoneDayjs(to).endOf('day').toDate()) : dateUtils.toSystemTimezoneISO(to)

  return { period, startDate, endDate }
}

export const getChartQueryRangeFromDateRange = (range: DateRange, fallbackShortcut: string = '1w'): ChartQueryRange => {
  if (!range.from || !range.to) {
    return getChartQueryRangeFromShortcut(fallbackShortcut)
  }

  const period = getPeriodFromDateRange(range)
  const startDate =
    period === Period.day
      ? dateUtils.toSystemTimezoneISO(dateUtils.toSystemTimezoneDayjs(range.from).startOf('day').toDate())
      : dateUtils.toSystemTimezoneISO(range.from)
  const endDate = period === Period.day ? dateUtils.toSystemTimezoneISO(dateUtils.toSystemTimezoneDayjs(range.to).endOf('day').toDate()) : dateUtils.toSystemTimezoneISO(range.to)

  return { period, startDate, endDate }
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
