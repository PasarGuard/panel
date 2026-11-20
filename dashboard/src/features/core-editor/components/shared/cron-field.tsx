import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TimePicker } from '@/components/ui/time-picker'
import { build, cronHourIntervals, parse, validateCronExpression } from '@/features/core-editor/kit/cron-field'
import type { CronFieldState } from '@/features/core-editor/kit/cron-field'
import useDirDetection from '@/hooks/use-dir-detection'
import cronstrue from 'cronstrue/i18n.js'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface CronFieldProps {
  value: string
  onChange: (value: string) => void
  id?: string
  'aria-describedby'?: string
}

const modes = ['disabled', 'daily', 'weekly', 'hours', 'custom'] as const
const weekdays = [0, 1, 2, 3, 4, 5, 6]

function describeCron(expression: string, language: string): string | undefined {
  const baseLanguage = language.toLowerCase().split(/[-_]/)[0]
  const locale = baseLanguage === 'zh' ? 'zh_CN' : baseLanguage
  const options = { use24HourTimeFormat: true, verbose: true }
  try {
    return cronstrue.toString(expression, { ...options, locale })
  } catch {
    try {
      return cronstrue.toString(expression, { ...options, locale: 'en' })
    } catch {
      return undefined
    }
  }
}

export function CronField({ value, onChange, id, 'aria-describedby': describedBy }: CronFieldProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const language = i18n.resolvedLanguage || i18n.language || 'en'
  const [state, setState] = useState(() => parse(value))
  const lastEmitted = useRef(value)

  useEffect(() => {
    if (value === lastEmitted.current) return
    lastEmitted.current = value
    setState(parse(value))
  }, [value])

  const change = (next: CronFieldState) => {
    setState(next)
    const result = build(next)
    if (result !== lastEmitted.current) {
      lastEmitted.current = result
      onChange(result)
    }
  }

  const expression = build(state)
  const time = state.mode === 'daily' || state.mode === 'weekly' ? state.time : '04:00'
  const invalid = !validateCronExpression(expression)
  const prefix = /^(?:CRON_TZ|TZ)=(\S+) +/.exec(expression)
  const schedule = expression.slice(prefix?.[0].length ?? 0).trim()
  const timeZone = prefix?.[1]
  const description = schedule && !invalid ? describeCron(schedule, language) : undefined
  const frequent = schedule !== '' && !invalid && !schedule.startsWith('@') && !/^\+?\d+$/.test(schedule.split(/\s+/)[0])

  return (
    <div className="grid min-w-0 gap-2">
      <Select
        dir={dir}
        value={state.mode}
        onValueChange={mode => {
          switch (mode) {
            case 'disabled':
              change({ mode })
              break
            case 'daily':
              change({ mode, time })
              break
            case 'weekly':
              change({ mode, time, day: 1 })
              break
            case 'hours':
              change({ mode, hours: 1 })
              break
            case 'custom':
              change({ mode, expression })
              break
          }
        }}
      >
        <SelectTrigger id={id} aria-label={id ? undefined : t('coreEditor.geodata.cron')} aria-describedby={describedBy}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {modes.map(mode => (
            <SelectItem key={mode} value={mode}>
              {t(`coreEditor.geodata.cronMode.${mode}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {(state.mode === 'daily' || state.mode === 'weekly') && (
        <div className="flex flex-wrap items-end gap-2">
          {state.mode === 'weekly' && (
            <Select dir={dir} value={String(state.day)} onValueChange={day => change({ ...state, day: Number(day) })}>
              <SelectTrigger className="w-auto flex-1" aria-label={t('coreEditor.geodata.cronDay')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {weekdays.map(day => (
                  <SelectItem key={day} value={String(day)}>
                    {new Date(Date.UTC(2024, 0, 7 + day)).toLocaleDateString(language, { weekday: 'long', timeZone: 'UTC' })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <TimePicker
            label={t('coreEditor.geodata.cronTime')}
            hourLabel={t('coreEditor.geodata.cronHour')}
            minuteLabel={t('coreEditor.geodata.cronMinute')}
            value={state.time}
            onChange={time => change({ ...state, time })}
          />
        </div>
      )}
      {state.mode === 'hours' && (
        <Select dir={dir} value={String(state.hours)} onValueChange={hours => change({ mode: 'hours', hours: Number(hours) })}>
          <SelectTrigger aria-label={t('coreEditor.geodata.cronMode.hours')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {cronHourIntervals.map(count => (
              <SelectItem key={count} value={String(count)}>
                {t('coreEditor.geodata.cronEveryHours', { count })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {state.mode === 'custom' && (
        <Input
          className="font-mono"
          dir="ltr"
          aria-label={t('coreEditor.geodata.cronMode.custom')}
          aria-invalid={invalid}
          placeholder="0 4 * * *"
          value={state.expression}
          onChange={event => change({ mode: 'custom', expression: event.target.value })}
        />
      )}
      <div aria-live="polite" className="space-y-1 text-xs">
        {expression && (
          <div className="text-muted-foreground flex flex-wrap items-center gap-2">
            <code dir="ltr" className="bg-muted max-w-full rounded px-1.5 py-0.5 break-all">
              {expression}
            </code>
            {description && (
              <span>
                {description} · {timeZone && timeZone !== 'Local' ? timeZone : t('coreEditor.geodata.cronServerTime')}
              </span>
            )}
          </div>
        )}
        {invalid && (
          <p role="alert" className="text-destructive">
            {t('coreEditor.geodata.cronInvalid')}
          </p>
        )}
        {frequent && <p className="text-amber-700 dark:text-amber-300">{t('coreEditor.geodata.cronFrequentWarning')}</p>}
      </div>
    </div>
  )
}
