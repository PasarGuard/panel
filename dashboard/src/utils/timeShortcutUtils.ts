import { DateRange } from 'react-day-picker'
import { dateUtils } from '@/utils/dateFormatter'

const SHORTCUT_PATTERN = /^(\d+)([hdwm])$/
const HOUR_IN_MS = 60 * 60 * 1000

const getTotalDays = (amount: number, unit: 'd' | 'w' | 'm') => {
  if (unit === 'd') return amount
  if (unit === 'w') return amount * 7
  return amount * 30
}

export const getDateRangeFromShortcut = (shortcut: string, now = new Date()): DateRange | undefined => {
  if (shortcut.trim().toLowerCase() === 'all') {
    const endOfDay = dateUtils.toSystemTimezoneDayjs(now).endOf('day')
    return {
      from: dateUtils.toSystemTimezoneDayjs('2000-01-01T00:00:00Z').toDate(),
      to: endOfDay.toDate(),
    }
  }

  const match = shortcut.trim().match(SHORTCUT_PATTERN)
  if (!match) return undefined

  const amount = Number.parseInt(match[1], 10)
  const unit = match[2] as 'h' | 'd' | 'w' | 'm'

  if (!Number.isFinite(amount) || amount <= 0) return undefined

  if (unit === 'h') {
    return {
      from: new Date(now.getTime() - amount * HOUR_IN_MS),
      to: now,
    }
  }

  const totalDays = getTotalDays(amount, unit)
  const endOfDay = dateUtils.toSystemTimezoneDayjs(now).endOf('day')
  const startOfRange = endOfDay.subtract(Math.max(totalDays - 1, 0), 'day').startOf('day')

  return {
    from: startOfRange.toDate(),
    to: endOfDay.toDate(),
  }
}
