import { DateRange } from 'react-day-picker'
import { Period } from '@/service/api'
import { format } from 'date-fns'

/**
 * Determines the appropriate period (hour or day) based on the date range
 * @param range - The date range to analyze
 * @returns Period.hour if range is <= 2 days, Period.day otherwise
 */
export const getPeriodFromDateRange = (range?: DateRange): Period => {
  if (!range?.from || !range?.to) {
    return Period.hour // Default to hour if no range
  }
  const diffTime = Math.abs(range.to.getTime() - range.from.getTime())
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
  if (diffDays <= 2) {
    return Period.hour
  }
  return Period.day
}

/**
 * Formats a date based on locale (Persian or Gregorian)
 * @param date - The date to format
 * @param isPersianLocale - Whether to use Persian locale
 * @param includeTime - Whether to include time in the format
 * @returns Formatted date string
 */
export const formatDateByLocale = (date: Date, isPersianLocale: boolean, includeTime: boolean = false): string => {
  if (isPersianLocale) {
    if (includeTime) {
      return (
        date.toLocaleDateString('fa-IR', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        }) +
        ' ' +
        date.toLocaleTimeString('fa-IR', {
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        })
      )
    }
    return new Intl.DateTimeFormat('fa-IR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(date)
  }

  if (includeTime) {
    return (
      date.toLocaleDateString('sv-SE', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }) +
      ' ' +
      date.toLocaleTimeString('sv-SE', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    )
  }

  // Use date-fns format for consistency with existing code
  return format(date, 'LLL dd, y')
}

/**
 * Formats a date in a shorter format for mobile/responsive display
 * @param date - The date to format
 * @param isPersianLocale - Whether to use Persian locale
 * @returns Short formatted date string (e.g., "Nov 06" or "06/11")
 */
export const formatDateShort = (date: Date, isPersianLocale: boolean): string => {
  if (isPersianLocale) {
    return date.toLocaleDateString('fa-IR', {
      month: '2-digit',
      day: '2-digit',
    })
  }
  return format(date, 'MMM dd')
}

/**
 * Formats a date for chart tooltips based on period and locale
 * @param date - The date to format
 * @param period - The period type ('hour' or 'day')
 * @param isPersianLocale - Whether to use Persian locale
 * @param isToday - Whether the date is today
 * @returns Formatted date string for tooltip
 */
export const formatDateForTooltip = (date: Date, period: 'hour' | 'day', isPersianLocale: boolean, isToday: boolean = false): string => {
  const locale = isPersianLocale ? 'fa-IR' : 'en-US'
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }

  if (period === 'day' && isToday) {
    return new Date().toLocaleString(locale, options).replace(',', '')
  } else if (period === 'day') {
    const localDate = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0)
    return localDate.toLocaleString(locale, options).replace(',', '')
  } else {
    // hourly or other: use actual time from data
    return date.toLocaleString(locale, options).replace(',', '')
  }
}

/**
 * Validates if a date should be disabled (for expiry date pickers)
 * @param date - The date to validate
 * @param minDate - Optional minimum date (defaults to today)
 * @param maxDate - Optional maximum date (defaults to 15 years from now)
 * @returns true if the date should be disabled
 */
export const isDateDisabled = (date: Date, minDate?: Date, maxDate?: Date): boolean => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const compareDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  // Use provided minDate or default to today
  const min = minDate || today
  const minCompare = new Date(min.getFullYear(), min.getMonth(), min.getDate())

  // Disable if the date is before min date
  if (compareDate < minCompare) {
    return true
  }

  // Use provided maxDate or default to 15 years from now
  const max = maxDate || new Date(now.getFullYear() + 15, 11, 31)
  const maxCompare = new Date(max.getFullYear(), max.getMonth(), max.getDate())

  // Disable if the date is after max date
  if (compareDate > maxCompare) {
    return true
  }

  // Only apply expiry date logic (disable past dates) if minDate is not explicitly provided
  // This allows cleanup settings to use dates in the past when minDate is provided
  if (!minDate) {
    // For current year, disable past months
    if (date.getFullYear() === now.getFullYear()) {
      // If the month is before current month, disable it
      if (date.getMonth() < now.getMonth()) {
        return true
      }
      // If it's the current month, disable past days
      if (date.getMonth() === now.getMonth() && compareDate < today) {
        return true
      }
    }
  }

  return false
}
