import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useId } from 'react'

interface TimePickerProps {
  value: string
  onChange: (value: string) => void
  label: string
  hourLabel: string
  minuteLabel: string
}

const hours = Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, '0'))
const minutes = Array.from({ length: 60 }, (_, minute) => String(minute).padStart(2, '0'))

export function TimePicker({ value, onChange, label, hourLabel, minuteLabel }: TimePickerProps) {
  const id = useId()
  const [hour, minute] = value.split(':')

  return (
    <div dir="ltr" role="group" aria-label={label} className="flex min-w-36 flex-1 items-end gap-2">
      <div className="grid flex-1 gap-1.5">
        <Label dir="auto" htmlFor={`${id}-hour`}>
          {hourLabel}
        </Label>
        <Select dir="ltr" value={hour} onValueChange={nextHour => onChange(`${nextHour}:${minute}`)}>
          <SelectTrigger id={`${id}-hour`} className="tabular-nums">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-64 tabular-nums">
            {hours.map(option => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <span aria-hidden className="text-muted-foreground flex h-9 items-center">
        :
      </span>
      <div className="grid flex-1 gap-1.5">
        <Label dir="auto" htmlFor={`${id}-minute`}>
          {minuteLabel}
        </Label>
        <Select dir="ltr" value={minute} onValueChange={nextMinute => onChange(`${hour}:${nextMinute}`)}>
          <SelectTrigger id={`${id}-minute`} className="tabular-nums">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-64 tabular-nums">
            {minutes.map(option => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
