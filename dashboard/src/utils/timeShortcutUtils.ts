import { DateRange } from 'react-day-picker'
import { parseDateInput } from './dateTimeParsing'

const SHORTCUT_PATTERN = /^(\d+)([hdwm])$/
const HOUR_IN_MS = 60 * 60 * 1000

const getTotalDays = (amount: number, unit: 'd' | 'w' | 'm') => {
  if (unit === 'd') return amount
  if (unit === 'w') return amount * 7
  return amount * 30
}

export const getDateRangeFromShortcut = (shortcut: string, now = new Date()): DateRange | undefined => {
  if (shortcut.trim().toLowerCase() === 'all') {
    const endOfDay = parseDateInput(now).endOf('day')
    return {
      from: new Date(2000, 0, 1, 0, 0, 0, 0),
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
  const endOfDay = parseDateInput(now).endOf('day')
  const startOfRange = endOfDay.subtract(Math.max(totalDays - 1, 0), 'day').startOf('day')

  return {
    from: startOfRange.toDate(),
    to: endOfDay.toDate(),
  }
}
