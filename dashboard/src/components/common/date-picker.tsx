'use client'

import * as React from 'react'
import { addDays } from 'date-fns'
import { Calendar as CalendarIcon, X } from 'lucide-react'
import { DateRange } from 'react-day-picker'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { useTranslation } from 'react-i18next'
import { Calendar as PersianCalendar } from '@/components/ui/persian-calendar'
import { formatDateByLocale, formatDateShort, isDateDisabled } from '@/utils/datePickerUtils'

export type DatePickerMode = 'single' | 'range'

export interface DatePickerProps {
  /**
   * Mode of the date picker: 'single' for single date selection, 'range' for date range selection
   */
  mode: DatePickerMode
  /**
   * Callback when date or range changes
   */
  onDateChange: (date: Date | undefined) => void
  onRangeChange?: (range: DateRange | undefined) => void
  /**
   * Initial/controlled date value (for single mode)
   */
  date?: Date | null
  /**
   * Initial/controlled range value (for range mode)
   */
  range?: DateRange | undefined
  /**
   * Whether to show time input (only for single mode)
   */
  showTime?: boolean
  /**
   * Whether to use UTC timestamp (only for single mode with showTime)
   */
  useUtcTimestamp?: boolean
  /**
   * Label for the date picker
   */
  label?: string
  /**
   * Placeholder text
   */
  placeholder?: string
  /**
   * Minimum selectable date
   */
  minDate?: Date
  /**
   * Maximum selectable date
   */
  maxDate?: Date
  /**
   * Default range for range mode (defaults to last 7 days)
   */
  defaultRange?: DateRange
  /**
   * Whether dates after a certain date should be disabled (for range mode, typically today)
   */
  disableAfter?: Date
  /**
   * Number of months to show in calendar
   */
  numberOfMonths?: number
  /**
   * Custom className
   */
  className?: string
  /**
   * Whether the picker is open (controlled)
   */
  open?: boolean
  /**
   * Callback when open state changes
   */
  onOpenChange?: (open: boolean) => void
  /**
   * Custom date formatter function
   */
  formatDate?: (date: Date) => string
  /**
   * Field name for form integration
   */
  fieldName?: string
  /**
   * Callback for field change (for form integration)
   */
  onFieldChange?: (fieldName: string, value: any) => void
}

/**
 * Helper function to get local ISO time string with timezone offset
 */
const getLocalISOTime = (date: Date): string => {
  // Create a properly formatted ISO string with timezone offset
  const tzOffset = -date.getTimezoneOffset()
  const offsetSign = tzOffset >= 0 ? '+' : '-'
  const pad = (num: number) => Math.abs(num).toString().padStart(2, '0')

  const offsetHours = pad(Math.floor(Math.abs(tzOffset) / 60))
  const offsetMinutes = pad(Math.abs(tzOffset) % 60)

  // Get the local date/time components without timezone conversion
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  const seconds = pad(date.getSeconds())

  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}${offsetSign}${offsetHours}:${offsetMinutes}`
}

/**
 * Centralized Date Picker Component
 * Supports both single date and date range selection modes
 * Includes Persian/Gregorian calendar support, time input, and validation
 */
export function DatePicker({
  mode,
  onDateChange,
  onRangeChange,
  date,
  range,
  showTime = false,
  useUtcTimestamp = false,
  label,
  placeholder,
  minDate,
  maxDate,
  defaultRange,
  disableAfter,
  numberOfMonths = mode === 'range' ? 2 : 1,
  className,
  open: controlledOpen,
  onOpenChange,
  formatDate: customFormatDate,
  fieldName = 'date',
  onFieldChange,
}: DatePickerProps) {
  const { t, i18n } = useTranslation()
  const isPersianLocale = i18n.language === 'fa'
  const [internalOpen, setInternalOpen] = React.useState(false)
  const [internalDate, setInternalDate] = React.useState<Date | undefined>(date || undefined)
  const [internalRange, setInternalRange] = React.useState<DateRange | undefined>(
    range || defaultRange || (mode === 'range' ? { from: addDays(new Date(), -7), to: new Date() } : undefined),
  )

  // Use controlled or internal state for open
  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen
  const setIsOpen = (open: boolean) => {
    if (controlledOpen === undefined) {
      setInternalOpen(open)
    }
    onOpenChange?.(open)
  }

  // Sync internal state with props
  React.useEffect(() => {
    if (date !== undefined) {
      setInternalDate(date || undefined)
    }
  }, [date])

  React.useEffect(() => {
    if (range !== undefined) {
      setInternalRange(range)
    }
  }, [range])

  // Propagate initial range for range mode
  React.useEffect(() => {
    if (mode === 'range' && internalRange && onRangeChange) {
      onRangeChange(internalRange)
    }
  }, []) // Only on mount

  const handleDateSelect = React.useCallback(
    (selectedDate: Date | undefined) => {
      if (!selectedDate) {
        setInternalDate(undefined)
        onDateChange(undefined)
        return
      }

      const now = new Date()
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      const selectedDateOnly = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate())

      // Ensure date is not in the past (for expiry dates)
      if (minDate === undefined && selectedDateOnly < today) {
        selectedDate = new Date(now)
      }

      // Always use current time (not end of day)
      selectedDate.setHours(now.getHours(), now.getMinutes(), now.getSeconds(), now.getMilliseconds())

      setInternalDate(selectedDate)
      const value = useUtcTimestamp ? Math.floor(selectedDate.getTime() / 1000) : getLocalISOTime(selectedDate)
      onDateChange(selectedDate)
      onFieldChange?.(fieldName, value)

      // Close popover when day is clicked
      setIsOpen(false)
    },
    [onDateChange, onFieldChange, fieldName, useUtcTimestamp, minDate],
  )

  const handleTimeChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      e.preventDefault()
      e.stopPropagation()
      if (internalDate && e.target.value) {
        const [hours, minutes] = e.target.value.split(':')
        const newDate = new Date(internalDate)
        newDate.setHours(parseInt(hours), parseInt(minutes))

        const now = new Date()
        if (newDate.toDateString() === now.toDateString() && newDate < now) {
          newDate.setTime(now.getTime())
        }

        const value = useUtcTimestamp ? Math.floor(newDate.getTime() / 1000) : getLocalISOTime(newDate)
        setInternalDate(newDate)
        onDateChange(newDate)
        onFieldChange?.(fieldName, value)
      }
    },
    [internalDate, onDateChange, onFieldChange, fieldName, useUtcTimestamp],
  )

  const handleRangeSelect = React.useCallback(
    (selectedRange: DateRange | undefined) => {
      setInternalRange(selectedRange)
      onRangeChange?.(selectedRange)
      
      // Close popover when both dates are selected
      if (selectedRange?.from && selectedRange?.to) {
        setIsOpen(false)
      }
    },
    [onRangeChange],
  )

  const formatDate = React.useCallback(
    (date: Date) => {
      if (customFormatDate) {
        return customFormatDate(date)
      }
      return formatDateByLocale(date, isPersianLocale, showTime)
    },
    [customFormatDate, isPersianLocale, showTime],
  )

  const dateDisabled = React.useCallback(
    (date: Date) => {
      if (mode === 'range' && disableAfter && date > disableAfter) {
        return true
      }
      if (mode === 'single' && (minDate || maxDate)) {
        return isDateDisabled(date, minDate, maxDate)
      }
      if (mode === 'single' && !minDate && !maxDate) {
        // Default validation for expiry dates: no past dates
        return isDateDisabled(date)
      }
      return false
    },
    [mode, disableAfter, minDate, maxDate],
  )

  const now = new Date()

  // Single date mode
  if (mode === 'single') {
    const displayDate = internalDate || (date ? new Date(date) : null)
    const timeValue = displayDate
      ? `${String(displayDate.getHours()).padStart(2, '0')}:${String(displayDate.getMinutes()).padStart(2, '0')}`
      : ''

    const handleClear = React.useCallback(
      (e: React.MouseEvent) => {
        e.preventDefault()
        e.stopPropagation()
        setInternalDate(undefined)
        onDateChange(undefined)
        onFieldChange?.(fieldName, undefined)
      },
      [onDateChange, onFieldChange, fieldName],
    )

    return (
      <div className={cn('grid gap-2', className)}>
        {label && <label className="text-sm font-medium">{label}</label>}
        <Popover open={isOpen} onOpenChange={setIsOpen}>
          <PopoverTrigger asChild>
            <Button
              dir="ltr"
              variant="outline"
              className={cn('w-full justify-start text-left font-normal', !displayDate && 'text-muted-foreground')}
              type="button"
            >
              {displayDate ? formatDate(displayDate) : <span>{placeholder || label || t('timeSelector.pickDate')}</span>}
              <div className="ml-auto flex items-center gap-1">
                {displayDate && (
                  <button
                    type="button"
                    onClick={handleClear}
                    className="rounded-sm opacity-50 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    aria-label={t('clear', { defaultValue: 'Clear' })}
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
                <CalendarIcon className="h-4 w-4 opacity-50" />
              </div>
            </Button>
          </PopoverTrigger>
          <PopoverContent
            className="w-auto p-0"
            align="start"
            onInteractOutside={(e: Event) => {
              e.preventDefault()
              setIsOpen(false)
            }}
            onEscapeKeyDown={() => setIsOpen(false)}
          >
            {isPersianLocale ? (
              <PersianCalendar
                mode="single"
                selected={displayDate || undefined}
                onSelect={handleDateSelect}
                disabled={dateDisabled}
                captionLayout="dropdown"
                defaultMonth={displayDate || now}
                startMonth={minDate || new Date(now.getFullYear(), now.getMonth(), 1)}
                endMonth={maxDate || new Date(now.getFullYear() + 15, 11, 31)}
                formatters={{
                  formatMonthDropdown: date => date.toLocaleString('fa-IR', { month: 'short' }),
                }}
              />
            ) : (
              <Calendar
                mode="single"
                selected={displayDate || undefined}
                onSelect={handleDateSelect}
                disabled={dateDisabled}
                captionLayout="dropdown"
                defaultMonth={displayDate || now}
                startMonth={minDate || new Date(now.getFullYear(), now.getMonth(), 1)}
                endMonth={maxDate || new Date(now.getFullYear() + 15, 11, 31)}
                formatters={{
                  formatMonthDropdown: date => date.toLocaleString('default', { month: 'short' }),
                }}
              />
            )}
            {showTime && (
              <>
                <div className="hidden lg:flex items-center gap-1.5 flex-wrap border-t p-3">
                  {[
                    { label: '7d', days: 7 },
                    { label: '1m', days: 30 },
                    { label: '2m', days: 60 },
                    { label: '3m', days: 90 },
                    { label: '1y', days: 365 },
                  ].map(({ label, days }) => {
                    const handleShortcut = () => {
                      const targetDate = new Date(now)
                      targetDate.setDate(now.getDate() + days)
                      // Use current time instead of end of day
                      handleDateSelect(targetDate)
                    }
                    return (
                      <Button
                        key={label}
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2.5 text-xs text-muted-foreground hover:text-foreground"
                        onClick={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          handleShortcut()
                        }}
                      >
                        {label}
                      </Button>
                    )
                  })}
                </div>
                <div className="flex items-center gap-4 border-t p-3">
                  <Input
                    type="time"
                    value={timeValue}
                    onChange={handleTimeChange}
                    className="w-full"
                    dir="ltr"
                  />
                </div>
              </>
            )}
          </PopoverContent>
        </Popover>
      </div>
    )
  }

  // Range mode
  const displayRange = internalRange || range
  return (
    <div className={cn('grid gap-2', className)}>
      {label && <label className="text-sm font-medium">{label}</label>}
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          <Button
            id="date"
            variant="outline"
            className={cn(
              'w-full justify-start text-left font-normal overflow-hidden',
              !displayRange && 'text-muted-foreground',
            )}
          >
            <CalendarIcon className="mr-2 h-4 w-4 flex-shrink-0" />
            {displayRange?.from ? (
              displayRange.to ? (
                <span className="truncate">
                  <span className="hidden sm:inline">
                    {formatDate(displayRange.from)} - {formatDate(displayRange.to)}
                  </span>
                  <span className="sm:hidden">
                    {formatDateShort(displayRange.from, isPersianLocale)} - {formatDateShort(displayRange.to, isPersianLocale)}
                  </span>
                </span>
              ) : (
                <span className="truncate">
                  <span className="hidden sm:inline">{formatDate(displayRange.from)}</span>
                  <span className="sm:hidden">{formatDateShort(displayRange.from, isPersianLocale)}</span>
                </span>
              )
            ) : (
              <span className="truncate">{placeholder || t('timeSelector.pickDate')}</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="end">
          {isPersianLocale ? (
            <PersianCalendar
              mode="range"
              defaultMonth={displayRange?.from}
              selected={displayRange}
              onSelect={handleRangeSelect}
              numberOfMonths={numberOfMonths}
              disabled={disableAfter ? { after: disableAfter } : undefined}
            />
          ) : (
            <Calendar
              mode="range"
              defaultMonth={displayRange?.from}
              selected={displayRange}
              onSelect={handleRangeSelect}
              numberOfMonths={numberOfMonths}
              disabled={disableAfter ? { after: disableAfter } : undefined}
            />
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}

