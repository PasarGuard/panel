import { DateInput, NumberInputMode, parseDateInput } from './dateTimeParsing'

type UtcParseOptions = {
  numberInputMode?: NumberInputMode
}

const UTC_DATE_TIME_FORMAT = 'YYYY-MM-DDTHH:mm:ss[Z]'

export const formatUtcDateTime = (value: DateInput, options: UtcParseOptions = {}) => {
  return parseDateInput(value, options).utc().format(UTC_DATE_TIME_FORMAT)
}

export const formatUtcStartOfDay = (value: DateInput, options: UtcParseOptions = {}) => {
  return parseDateInput(value, options).utc().startOf('day').format(UTC_DATE_TIME_FORMAT)
}
