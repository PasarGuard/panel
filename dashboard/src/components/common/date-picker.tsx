'use client'

import { addDays } from 'date-fns'
import { useState, useEffect, useCallback, ChangeEvent, KeyboardEvent, MouseEvent } from 'react'
import { Calendar as CalendarIcon, X } from 'lucide-react'
import { DateRange } from 'react-day-picker'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { useTranslation } from 'react-i18next'
import { Calendar as PersianCalendar } from '@/components/ui/persian-calendar'
import { formatDateByLocale, formatDateShort, isDateDisabled, isPersianLocaleLanguage } from '@/utils/datePickerUtils'
import { formatOffsetDateTime, parseDateInput, toUnixSeconds } from '@/utils/dateTimeParsing'
import { useTheme } from '@/components/common/theme-provider'
import { DATE_PICKER_PREFERENCE_KEY, getDatePickerPreference, type DatePickerPreference } from '@/utils/userPreferenceStorage'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'

export type DatePickerMode = 'single' | 'range'

export type DatePickerAlign = 'start' | 'center' | 'end'

export type DatePickerSide = 'top' | 'right' | 'bottom' | 'left'

interface BaseDatePickerProps {
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
  /**
   * Alignment of the popover (overrides responsive defaults when set)
   */
  align?: DatePickerAlign
  /**
   * Side of the popover (overrides responsive defaults when set)
   */
  side?: DatePickerSide
  /**
   * When `align` is unset: alignment on viewports wider than mobile (mobile uses `end`).
   * @default 'end'
   */
  popoverAlignDesktop?: DatePickerAlign
  /**
   * When `side` is unset: side on viewports wider than mobile (mobile uses `bottom`).
   * @default 'left'
   */
  popoverSideDesktop?: DatePickerSide
}

export type SingleDatePickerProps = BaseDatePickerProps & {
  /**
   * Mode of the date picker: 'single' for single date selection
   */
  mode: 'single'
  /**
   * Callback when date changes
   */
  onDateChange: (date: Date | undefined) => void
  onRangeChange?: (range: DateRange | undefined) => void
  /**
   * Initial/controlled date value (for single mode)
   */
  date?: Date | null
  range?: never
  /**
   * Initial/controlled range value (for range mode)
   */
  showTime?: boolean
  /**
   * Whether to use UTC timestamp (only for single mode with showTime)
   */
  useUtcTimestamp?: boolean
}

export type RangeDatePickerProps = BaseDatePickerProps & {
  /**
   * Mode of the date picker: 'range' for date range selection
   */
  mode: 'range'
  /**
   * Callback when range changes
   */
  onDateChange?: never
  onRangeChange: (range: DateRange | undefined) => void
  /**
   * Initial/controlled date value (for single mode)
   */
  date?: never
  /**
   * Initial/controlled range value (for range mode)
   */
  range?: DateRange | undefined
  showTime?: never
  useUtcTimestamp?: never
}

export type DatePickerProps = SingleDatePickerProps | RangeDatePickerProps

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
  align,
  side,
  popoverAlignDesktop = 'end',
  popoverSideDesktop = 'left',
}: DatePickerProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'
  const handleSingleDateChange = onDateChange ?? (() => undefined)
  const [datePreference, setDatePreference] = useState<DatePickerPreference>('locale')
  const isPersianCalendar =
    datePreference === 'persian' ||
    (datePreference === 'locale' && isPersianLocaleLanguage(i18n.resolvedLanguage ?? i18n.language))
  const isMobile = useIsMobile()
  const { resolvedTheme } = useTheme()
  const [internalOpen, setInternalOpen] = useState(false)
  const [internalDate, setInternalDate] = useState<Date | undefined>(date || undefined)
  const [internalRange, setInternalRange] = useState<DateRange | undefined>(range || defaultRange || (mode === 'range' ? { from: addDays(new Date(), -7), to: new Date() } : undefined))

  // Use controlled or internal state for open
  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen
  const setIsOpen = (open: boolean) => {
    if (controlledOpen === undefined) {
      setInternalOpen(open)
    }
    onOpenChange?.(open)
  }

  // Sync internal state with props
  useEffect(() => {
    if (date !== undefined) {
      setInternalDate(date || undefined)
    }
  }, [date])

  useEffect(() => {
    if (range !== undefined) {
      setInternalRange(range)
    }
  }, [range])

  useEffect(() => {
    if (mode === 'range' && internalRange && onRangeChange) {
      onRangeChange(internalRange)
    }
  }, [])

  useEffect(() => {
    const storedPreference = getDatePickerPreference()
    setDatePreference(storedPreference)

    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === DATE_PICKER_PREFERENCE_KEY) {
        setDatePreference(getDatePickerPreference())
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  const handleDateSelect = useCallback(
    (selectedDate: Date | undefined) => {
      if (!selectedDate) {
        setInternalDate(undefined)
        handleSingleDateChange(undefined)
        onFieldChange?.(fieldName, undefined)
        return
      }

      const now = new Date()
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      let selectedDateOnly = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate())

      if (minDate === undefined && selectedDateOnly < today) {
        selectedDate = new Date(now)
        selectedDateOnly = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate())
      }

      const isToday = selectedDateOnly.getTime() === today.getTime()

      if (isToday) {
        selectedDate.setHours(23, 59, 59, 999)
      } else if (internalDate) {
        // Preserve time from existing date (works for both showTime and !showTime)
        selectedDate.setHours(internalDate.getHours(), internalDate.getMinutes(), internalDate.getSeconds(), internalDate.getMilliseconds())
      } else {
        selectedDate.setHours(now.getHours(), now.getMinutes(), now.getSeconds(), now.getMilliseconds())
      }

      setInternalDate(selectedDate)
      const value = useUtcTimestamp ? toUnixSeconds(selectedDate) : formatOffsetDateTime(selectedDate)
      handleSingleDateChange(selectedDate)
      onFieldChange?.(fieldName, value)
      setTimeout(() => {
        setIsOpen(false)
      }, 0)
    },
    [handleSingleDateChange, onFieldChange, fieldName, useUtcTimestamp, minDate, internalDate],
  )

  const handleDateSelectWrapper = useCallback(
    (selectedDate: Date | undefined) => {
      handleDateSelect(selectedDate)
    },
    [handleDateSelect],
  )

  const handleTimeChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
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

        const value = useUtcTimestamp ? toUnixSeconds(newDate) : formatOffsetDateTime(newDate)
        setInternalDate(newDate)
        handleSingleDateChange(newDate)
        onFieldChange?.(fieldName, value)
      }
    },
    [internalDate, handleSingleDateChange, onFieldChange, fieldName, useUtcTimestamp],
  )

  const handleRangeSelect = useCallback(
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

  const formatDate = useCallback(
    (date: Date) => {
      if (customFormatDate) {
        return customFormatDate(date)
      }
      return formatDateByLocale(date, isPersianCalendar, showTime)
    },
    [customFormatDate, isPersianCalendar, showTime],
  )

  const dateDisabled = useCallback(
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
    const displayDate = internalDate || (date ? new Date(date) : undefined)
    const timeValue = displayDate ? `${String(displayDate.getHours()).padStart(2, '0')}:${String(displayDate.getMinutes()).padStart(2, '0')}` : ''

    const clearDate = useCallback(() => {
        setInternalDate(undefined)
        handleSingleDateChange(undefined)
        onFieldChange?.(fieldName, undefined)
      }, 
      [handleSingleDateChange, onFieldChange, fieldName],
    )

    const handleClearClick = useCallback(
      (e: MouseEvent<HTMLElement>) => {
        e.preventDefault()
        e.stopPropagation()
        clearDate()
      },
      [clearDate],
    )

    const handleClearKeyDown = useCallback(
      (e: KeyboardEvent<HTMLElement>) => {
        if (e.key !== 'Enter' && e.key !== ' ') return
        e.preventDefault()
        e.stopPropagation()
        clearDate()
      },
      [clearDate],
    )

    return (
      <div className={cn('grid gap-2', className)}>
        {label && <label className="text-sm font-medium">{label}</label>}
        <Popover open={isOpen} onOpenChange={setIsOpen}>
          <PopoverTrigger asChild>
            <Button
              dir="ltr"
              type="button"
              variant="outline"
              size="sm"
              className={cn('w-full justify-start font-normal', isRTL ? 'text-right' : 'text-left', !displayDate && 'text-muted-foreground')}
            >
              {displayDate ? formatDate(displayDate) : <span>{placeholder || label || t('timeSelector.pickDate')}</span>}
              <div className="flex items-center gap-1 ml-auto">
                {displayDate && (
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={handleClearClick}
                    onKeyDown={handleClearKeyDown}
                    className="rounded-sm opacity-50 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                    aria-label={t('clear', { defaultValue: 'Clear' })}
                  >
                    <X className="h-4 w-4" />
                  </span>
                )}
                <CalendarIcon className="h-4 w-4 opacity-50" />
              </div>
            </Button>
          </PopoverTrigger>
          <PopoverContent
            className={cn('w-auto p-0', isMobile && 'max-w-[calc(100vw-1.5rem)]')}
            align={align ? align : isMobile ? 'end' : popoverAlignDesktop}
            side={side ? side : isMobile ? 'bottom' : popoverSideDesktop}
            sideOffset={4}
            collisionPadding={isMobile ? 20 : 12}
            onInteractOutside={() => {
              setIsOpen(false)
            }}
            onEscapeKeyDown={() => setIsOpen(false)}
          >
            {isPersianCalendar ? (
              <PersianCalendar
                mode="single"
                selected={displayDate}
                onSelect={handleDateSelectWrapper}
                disabled={dateDisabled}
                captionLayout="dropdown"
                defaultMonth={displayDate || now}
                startMonth={minDate || new Date(now.getFullYear(), 0, 1)}
                endMonth={maxDate || new Date(now.getFullYear() + 15, 11, 31)}
                formatters={{
                  formatMonthDropdown: date => date.toLocaleString('fa-IR', { month: 'short' }),
                }}
              />
            ) : (
              <Calendar
                mode="single"
                selected={displayDate}
                onSelect={handleDateSelectWrapper}
                disabled={dateDisabled}
                captionLayout="dropdown"
                defaultMonth={displayDate || now}
                startMonth={minDate || new Date(now.getFullYear(), 0, 1)}
                endMonth={maxDate || new Date(now.getFullYear() + 15, 11, 31)}
                formatters={{
                  formatMonthDropdown: date => date.toLocaleString('default', { month: 'short' }),
                }}
              />
            )}
            {showTime && (
              <>
                <div dir="ltr" className="hidden flex-wrap items-center gap-1 border-t p-2 lg:flex">
                  {[
                    { label: '+7d', days: 7 },
                    { label: '+1m', days: 30 },
                    { label: '+2m', days: 60 },
                    { label: '+3m', days: 90 },
                    { label: '+1y', days: 365 },
                  ].map(({ label, days }) => {
                    const handleShortcut = () => {
                      const baseDate = displayDate || now
                      const targetDate = new Date(parseDateInput(baseDate).add(days, 'day').valueOf())
                      handleDateSelect(targetDate)
                    }
                    return (
                      <Button
                        key={label}
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-5 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
                        onClick={e => {
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
                    className={cn(
                      'w-full [&::-webkit-calendar-picker-indicator]:cursor-pointer [&::-webkit-calendar-picker-indicator]:opacity-100 [&::-webkit-calendar-picker-indicator]:brightness-0 [&::-webkit-calendar-picker-indicator]:hue-rotate-0 [&::-webkit-calendar-picker-indicator]:saturate-100',
                      resolvedTheme === 'dark' && '[&::-webkit-calendar-picker-indicator]:invert',
                    )}
                    style={{
                      colorScheme: resolvedTheme,
                    }}
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
          <Button id="date" type="button" variant="outline" size="sm" className={cn('w-full justify-start overflow-hidden text-left font-normal', !displayRange && 'text-muted-foreground')}>
            <CalendarIcon className="mr-2 h-4 w-4 flex-shrink-0" />
            {displayRange?.from ? (
              displayRange.to ? (
                <span className="truncate">
                  <span className="hidden sm:inline">
                    {formatDate(displayRange.from)} - {formatDate(displayRange.to)}
                  </span>
                  <span className="sm:hidden">
                    {formatDateShort(displayRange.from, isPersianCalendar)} - {formatDateShort(displayRange.to, isPersianCalendar)}
                  </span>
                </span>
              ) : (
                <span className="truncate">
                  <span className="hidden sm:inline">{formatDate(displayRange.from)}</span>
                  <span className="sm:hidden">{formatDateShort(displayRange.from, isPersianCalendar)}</span>
                </span>
              )
            ) : (
              <span className="truncate">{placeholder || t('timeSelector.pickDate')}</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align={align ? align : "start"} side={side ? side : "bottom"} sideOffset={4} collisionPadding={8}>
          {isPersianCalendar ? (
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
