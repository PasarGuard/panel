import dayjs from '@/lib/dayjs'
import { useTranslation } from 'react-i18next'
import { formatUtcStartOfDay } from './utcDateTime'

// Helper function to convert timestamp to ISO string
function timestampToISO(timestamp: number): string {
  return new Date(timestamp * 1000).toISOString()
}

// Helper function to convert ISO string to timestamp
function isoToTimestamp(isoString: string): number {
  return Math.floor(new Date(isoString).getTime() / 1000)
}

export const useRelativeExpiryDate = (expiryDate: string | number | null | undefined, referenceStatus?: string | null) => {
  const { t } = useTranslation()
  const dateInfo: { status: '' | 'expires' | 'expired'; time: string } = { status: '', time: '' }

  if (!expiryDate) return dateInfo

  const target = dateUtils.toDayjs(expiryDate)
  const now = dayjs()
  const rawDiffSeconds = target.diff(now, 'second', true)
  const shouldClampExpiredSkew = referenceStatus === 'expired' && rawDiffSeconds > 0 && rawDiffSeconds <= 300

  const isAfter = shouldClampExpiredSkew ? false : target.isAfter(now)
  dateInfo.status = isAfter ? 'expires' : 'expired'

  // Nearest-unit duration for concise "time left" text.
  const diffSeconds = shouldClampExpiredSkew ? 0 : Math.abs(rawDiffSeconds)
  const daySeconds = 24 * 60 * 60
  const hourSeconds = 60 * 60
  const minuteSeconds = 60

  if (diffSeconds < 1) {
    dateInfo.time = t('time.justNow')
  } else {
    let value = 0
    let unitKey: 'day' | 'days' | 'hour' | 'hours' | 'min' | 'mins' | 'second' | 'seconds' = 'seconds'
    let text = ''

    if (diffSeconds >= daySeconds) {
      value = Math.round(diffSeconds / daySeconds)
      unitKey = value === 1 ? 'day' : 'days'
      text = `${value} ${t(`time.${unitKey}`)}`
    } else if (diffSeconds >= hourSeconds) {
      const totalSeconds = Math.max(1, Math.round(diffSeconds))
      const hours = Math.floor(totalSeconds / hourSeconds)
      const minutes = Math.floor((totalSeconds % hourSeconds) / minuteSeconds)
      const hourKey = hours === 1 ? 'hour' : 'hours'
      text = `${hours} ${t(`time.${hourKey}`)}`
      if (minutes > 0) {
        const minuteKey = minutes === 1 ? 'min' : 'mins'
        text += `, ${minutes} ${t(`time.${minuteKey}`)}`
      }
    } else if (diffSeconds >= minuteSeconds) {
      const totalSeconds = Math.max(1, Math.round(diffSeconds))
      const minutes = Math.floor(totalSeconds / minuteSeconds)
      const seconds = totalSeconds % minuteSeconds
      unitKey = minutes === 1 ? 'min' : 'mins'
      text = `${minutes} ${t(`time.${unitKey}`)}`
      if (seconds > 0) {
        const secondKey = seconds === 1 ? 'second' : 'seconds'
        text += `, ${seconds} ${t(`time.${secondKey}`)}`
      }
    } else {
      value = Math.round(diffSeconds)
      unitKey = value === 1 ? 'second' : 'seconds'
      text = `${value} ${t(`time.${unitKey}`)}`
    }

    dateInfo.time = `${text}${isAfter ? '' : ` ${t('time.ago')}`}`
  }
  return dateInfo
}

// Export helper functions for use in other components
export const dateUtils = {
  timestampToISO,
  isoToTimestamp,

  getCurrentISOTime: () => {
    return dayjs().toISOString() // ISO in UTC (standard)
  },

  getSystemTimeZone: () => {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || dayjs.tz.guess()
  },

  toSystemTimezoneDayjs: (date: string | number | Date) => {
    const systemTimezone = dateUtils.getSystemTimeZone()
    if (typeof date === 'string') return dayjs.utc(date).tz(systemTimezone)
    if (typeof date === 'number') return dayjs.unix(date).tz(systemTimezone)
    return dayjs(date).tz(systemTimezone)
  },

  toSystemTimezoneISO: (date: string | number | Date) => {
    return dateUtils.toSystemTimezoneDayjs(date).format('YYYY-MM-DDTHH:mm:ssZ')
  },

  // UTC conversions are kept in utcDateTime helpers to avoid mixing conversion concerns.
  toUTCDayStartISO: (date: string | number | Date) => {
    return formatUtcStartOfDay(date)
  },

  formatDate: (date: string | number | Date) => {
    const d = typeof date === 'string' ? dayjs.utc(date).local() : typeof date === 'number' ? dayjs.unix(date).local() : dayjs(date).local()

    return d.format('YYYY-MM-DD HH:mm:ss')
  },

  toDayjs: (date: string | number | Date) => {
    return typeof date === 'string' ? dayjs.utc(date).local() : typeof date === 'number' ? dayjs.unix(date).local() : dayjs(date).local()
  },

  isValidDate: (date: string | number | Date) => {
    const d = typeof date === 'string' ? new Date(date) : typeof date === 'number' ? new Date(date * 1000) : date

    return !isNaN(d.getTime())
  },

  daysToSeconds: (days: number | undefined): number | undefined => {
    if (days === undefined || days === null || days === 0) return undefined
    return Math.round(Number(days) * 24 * 60 * 60)
  },

  secondsToDays: (seconds: number | undefined): number | undefined => {
    if (seconds === undefined || seconds === null || seconds === 0) return undefined
    return Math.round(Number(seconds) / (24 * 60 * 60))
  },
}
