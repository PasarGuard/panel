import { validateXrayGeodata } from './xray-geodata'

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
  return expression === '' || validateXrayGeodata({ cron: expression }).length === 0
}
