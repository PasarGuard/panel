import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from 'react-i18next'

export type TimeUnit = 'seconds' | 'minutes' | 'hours' | 'days' | 'months'

export const TIME_UNIT_SECONDS: Record<TimeUnit, number> = {
  seconds: 1,
  minutes: 60,
  hours: 60 * 60,
  days: 24 * 60 * 60,
  months: 30 * 24 * 60 * 60,
}

export const secondsToTimeUnit = (seconds: unknown, unit: TimeUnit) => {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value <= 0) return ''
  return String(value / TIME_UNIT_SECONDS[unit])
}

const capitalize = (value: string) => (value ? value.charAt(0).toLocaleUpperCase() + value.slice(1) : value)

interface TimeUnitSelectProps {
  value: TimeUnit
  onValueChange: (value: TimeUnit) => void
  triggerClassName?: string
}

export function TimeUnitSelect({ value, onValueChange, triggerClassName }: TimeUnitSelectProps) {
  const { t } = useTranslation()
  const labels: Record<TimeUnit, string> = {
    seconds: capitalize(t('time.seconds', { defaultValue: 'Seconds' })),
    minutes: capitalize(t('time.mins', { defaultValue: 'Minutes' })),
    hours: capitalize(t('time.hours', { defaultValue: 'Hours' })),
    days: capitalize(t('time.days', { defaultValue: 'Days' })),
    months: capitalize(t('time.months', { defaultValue: 'Months' })),
  }

  return (
    <Select value={value} onValueChange={v => onValueChange(v as TimeUnit)}>
      <SelectTrigger className={triggerClassName}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="seconds">{labels.seconds}</SelectItem>
        <SelectItem value="minutes">{labels.minutes}</SelectItem>
        <SelectItem value="hours">{labels.hours}</SelectItem>
        <SelectItem value="days">{labels.days}</SelectItem>
        <SelectItem value="months">{labels.months}</SelectItem>
      </SelectContent>
    </Select>
  )
}
