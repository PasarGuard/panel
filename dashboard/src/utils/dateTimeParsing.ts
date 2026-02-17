import dayjs from '@/lib/dayjs'

export type DateInput = string | number | Date

export type NumberInputMode = 'seconds' | 'milliseconds'

const ISO_OFFSET_SUFFIX_PATTERN = /(Z|[+-]\d{2}:\d{2})$/i
const OFFSET_DATE_TIME_FORMAT = 'YYYY-MM-DDTHH:mm:ssZ'

type ParseDateInputOptions = {
  numberInputMode?: NumberInputMode
}

const parseOffsetMinutes = (value: string): number | undefined => {
  const offsetMatch = value.trim().match(ISO_OFFSET_SUFFIX_PATTERN)
  if (!offsetMatch) return undefined

  const rawOffset = offsetMatch[1].toUpperCase()
  if (rawOffset === 'Z') return 0

  const sign = rawOffset.startsWith('-') ? -1 : 1
  const [hours, minutes] = rawOffset.slice(1).split(':').map(part => Number.parseInt(part, 10))

  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return undefined

  return sign * (hours * 60 + minutes)
}

const parseStringDate = (value: string) => {
  const parsed = dayjs(value)
  if (!parsed.isValid()) return parsed

  // Preserve explicit source offsets (e.g. +03:30) so chart labels stay aligned with API buckets.
  const offsetMinutes = parseOffsetMinutes(value)
  return offsetMinutes === undefined ? parsed : parsed.utcOffset(offsetMinutes)
}

export const parseDateInput = (value: DateInput, options: ParseDateInputOptions = {}) => {
  const { numberInputMode = 'seconds' } = options

  if (typeof value === 'string') {
    return parseStringDate(value)
  }

  if (typeof value === 'number') {
    return numberInputMode === 'milliseconds' ? dayjs(value) : dayjs.unix(value)
  }

  return dayjs(value)
}

export const formatOffsetDateTime = (value: DateInput, options: ParseDateInputOptions = {}) => parseDateInput(value, options).format(OFFSET_DATE_TIME_FORMAT)

export const toLocalOffsetDateTime = (value: DateInput, options: ParseDateInputOptions = {}) => parseDateInput(value, options).local().format(OFFSET_DATE_TIME_FORMAT)

export const formatOffsetStartOfDay = (value: DateInput, options: ParseDateInputOptions = {}) => parseDateInput(value, options).startOf('day').format(OFFSET_DATE_TIME_FORMAT)

export const formatOffsetEndOfDay = (value: DateInput, options: ParseDateInputOptions = {}) => parseDateInput(value, options).endOf('day').format(OFFSET_DATE_TIME_FORMAT)

export const toUnixSeconds = (value: DateInput, options: ParseDateInputOptions = {}) => parseDateInput(value, options).unix()

export const toDisplayDate = (value: DateInput, options: ParseDateInputOptions = {}) => {
  const parsed = parseDateInput(value, options)
  return new Date(parsed.year(), parsed.month(), parsed.date(), parsed.hour(), parsed.minute(), parsed.second(), parsed.millisecond())
}
