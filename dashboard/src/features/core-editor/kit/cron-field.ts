import { CronPattern } from 'croner'

export const cronHourIntervals = [1, 2, 3, 4, 6, 8, 12]

export type CronFieldState =
  { mode: 'disabled' } | { mode: 'daily'; time: string } | { mode: 'weekly'; time: string; day: number } | { mode: 'hours'; hours: number } | { mode: 'custom'; expression: string }

export function parse(value: string): CronFieldState {
  const expression = value.trim().replace(/\s+/g, ' ')
  if (!expression) return { mode: 'disabled' }

  const hourly = /^0 \*\/(\d+) \* \* \*$/.exec(expression)
  if (hourly && cronHourIntervals.includes(Number(hourly[1]))) return { mode: 'hours', hours: Number(hourly[1]) }

  const timed = /^(\d{1,2}) (\d{1,2}) \* \* (\*|[0-6])$/.exec(expression)
  if (timed && Number(timed[1]) < 60 && Number(timed[2]) < 24) {
    const [, minute, hour, day] = timed
    const time = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
    return day === '*' ? { mode: 'daily', time } : { mode: 'weekly', time, day: Number(day) }
  }

  return { mode: 'custom', expression: value }
}

export function build(state: CronFieldState): string {
  switch (state.mode) {
    case 'disabled':
      return ''
    case 'hours':
      return `0 */${state.hours} * * *`
    case 'custom':
      return state.expression.trim()
    case 'daily':
    case 'weekly': {
      const [hour, minute] = state.time.split(':').map(Number)
      return `${minute} ${hour} * * ${state.mode === 'daily' ? '*' : state.day}`
    }
  }
}

export function validateCronExpression(expression: string): boolean {
  const fields = expression.trim().split(/\s+/)
  if (fields.length !== 5) return false

  // Xray treats '?' as a wildcard. Croner substitutes the current date or time.
  const [minute, hour, date, month, weekday] = fields.map(field => field.replace(/(^|[,/-])\+(?=\d)/g, '$1').replace(/\?/g, '*'))
  const months = /\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b/gi
  const weekdays = /\b(?:SUN|MON|TUE|WED|THU|FRI|SAT)\b/gi
  const hasExtendedSyntax = ![minute, hour, date, month.replace(months, '1'), weekday.replace(weekdays, '1')].every(field => /^[\d*,/-]+$/.test(field))
  if (hasExtendedSyntax || /(^|[,-])0*7(?=[,/-]|$)/.test(weekday)) return false

  try {
    new CronPattern([minute, hour, date, month, weekday].join(' '), undefined, { mode: '5-part' })
    return true
  } catch {
    return false
  }
}
