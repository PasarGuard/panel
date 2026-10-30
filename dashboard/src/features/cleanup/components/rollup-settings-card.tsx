import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import type { CleanupSettings } from '@/service/api'
import { CalendarDays, Clock, Combine, Info, Layers, Loader2, RotateCcw, Save, SunMoon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

type RollupKey = 'usage_rollup_hourly_after_days' | 'usage_rollup_half_day_after_days' | 'usage_rollup_daily_after_days'
type RollupDraft = Record<RollupKey, number | null | ''>

interface RollupSettingsCardProps {
  value?: CleanupSettings | null
  isLoading: boolean
  isSaving: boolean
  onSave: (value: Pick<CleanupSettings, RollupKey>) => Promise<void>
}

// Finest step first; the backend requires enabled values to increase in this order
const ROLLUP_KEYS: RollupKey[] = ['usage_rollup_hourly_after_days', 'usage_rollup_half_day_after_days', 'usage_rollup_daily_after_days']

const ENABLE_DEFAULTS: Record<RollupKey, number> = {
  usage_rollup_hourly_after_days: 7,
  usage_rollup_half_day_after_days: 30,
  usage_rollup_daily_after_days: 90,
}

/** Render and validate the usage-history rollup steps. */
export function RollupSettingsCard({ value, isLoading, isSaving, onSave }: RollupSettingsCardProps) {
  const { t } = useTranslation()
  const savedValue = useMemo<RollupDraft>(
    () => ({
      usage_rollup_hourly_after_days: value?.usage_rollup_hourly_after_days ?? null,
      usage_rollup_half_day_after_days: value?.usage_rollup_half_day_after_days ?? null,
      usage_rollup_daily_after_days: value?.usage_rollup_daily_after_days ?? null,
    }),
    // Saving the other cleanup card must not reset an unsaved draft here
    [value?.usage_rollup_hourly_after_days, value?.usage_rollup_half_day_after_days, value?.usage_rollup_daily_after_days],
  )
  const [draft, setDraft] = useState<RollupDraft>(savedValue)
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    setDraft(savedValue)
    setValidationError(null)
  }, [savedValue])

  const rollupItems = [
    {
      key: 'usage_rollup_hourly_after_days' as const,
      icon: Clock,
      title: t('settings.cleanup.rollup.hourlyStep.title'),
      description: t('settings.cleanup.rollup.hourlyStep.description'),
      tone: 'text-sky-600 dark:text-sky-400',
      surface: 'bg-sky-500/10',
    },
    {
      key: 'usage_rollup_half_day_after_days' as const,
      icon: SunMoon,
      title: t('settings.cleanup.rollup.halfDayStep.title'),
      description: t('settings.cleanup.rollup.halfDayStep.description'),
      tone: 'text-violet-600 dark:text-violet-400',
      surface: 'bg-violet-500/10',
    },
    {
      key: 'usage_rollup_daily_after_days' as const,
      icon: CalendarDays,
      title: t('settings.cleanup.rollup.dailyStep.title'),
      description: t('settings.cleanup.rollup.dailyStep.description'),
      tone: 'text-emerald-600 dark:text-emerald-400',
      surface: 'bg-emerald-500/10',
    },
  ]

  const isDirty = JSON.stringify(draft) !== JSON.stringify(savedValue)

  /** Enable a step with its default or turn it off. */
  const setEnabled = (key: RollupKey, enabled: boolean) => {
    setDraft(current => ({ ...current, [key]: enabled ? ENABLE_DEFAULTS[key] : null }))
    setValidationError(null)
  }

  /** Validate and persist the rollup steps. */
  const handleSave = async () => {
    const hasInvalidValue = ROLLUP_KEYS.some(key => {
      const days = draft[key]
      if (days === '') return true
      if (days === null) return false
      return !Number.isInteger(days) || days < 1 || days > 36_500
    })
    if (hasInvalidValue) {
      setValidationError(t('settings.cleanup.rollup.validation'))
      return
    }
    const enabledDays = ROLLUP_KEYS.map(key => draft[key]).filter((days): days is number => typeof days === 'number')
    if (enabledDays.some((days, index) => index > 0 && days <= enabledDays[index - 1])) {
      setValidationError(t('settings.cleanup.rollup.orderValidation'))
      return
    }
    try {
      await onSave({
        usage_rollup_hourly_after_days: draft.usage_rollup_hourly_after_days || null,
        usage_rollup_half_day_after_days: draft.usage_rollup_half_day_after_days || null,
        usage_rollup_daily_after_days: draft.usage_rollup_daily_after_days || null,
      })
    } catch {
      // The shared settings mutation already surfaces the API error as a toast.
      // Keep the draft intact so the user can correct or retry it.
    }
  }

  if (isLoading) {
    return <Skeleton className="h-[380px] w-full rounded-xl" />
  }

  return (
    <Card className="border-primary/20 from-primary/5 overflow-hidden bg-gradient-to-br via-transparent to-transparent">
      <CardHeader className="border-border/70 border-b p-4 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2 text-base font-semibold sm:text-lg">
              <span className="bg-primary/10 text-primary flex h-9 w-9 items-center justify-center rounded-lg">
                <Layers className="h-5 w-5" />
              </span>
              {t('settings.cleanup.rollup.title')}
            </CardTitle>
            <CardDescription className="max-w-2xl text-xs leading-relaxed sm:text-sm">{t('settings.cleanup.rollup.description')}</CardDescription>
          </div>
          <div className="border-primary/20 bg-background/80 text-muted-foreground hidden shrink-0 rounded-full border px-3 py-1 text-xs font-medium backdrop-blur sm:block">
            {t('settings.cleanup.retention.hourly')}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 p-4 sm:p-6">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {rollupItems.map(item => {
            const days = draft[item.key]
            const enabled = days !== null && days !== undefined
            const Icon = item.icon

            return (
              <section key={item.key} className="border-border/80 bg-background/75 grid min-w-0 gap-4 rounded-xl border p-4 shadow-sm xl:row-span-4 xl:grid-rows-subgrid">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className={`${item.surface} ${item.tone} flex h-9 w-9 shrink-0 items-center justify-center rounded-lg`}>
                      <Icon className="h-4.5 w-4.5" />
                    </span>
                    <h3 className="min-w-0 text-sm font-semibold">{item.title}</h3>
                  </div>
                  <Switch checked={enabled} onCheckedChange={checked => setEnabled(item.key, checked)} aria-label={item.title} />
                </div>
                <p id={`${item.key}-description`} className="text-muted-foreground text-xs leading-relaxed">
                  {item.description}
                </p>

                <div className="flex items-center gap-2">
                  <Input
                    type={enabled ? 'number' : 'text'}
                    min={1}
                    max={36_500}
                    step={1}
                    value={enabled ? days : t('settings.cleanup.rollup.off')}
                    onChange={event => {
                      const rawValue = event.target.value
                      const parsedValue = rawValue.trim() === '' ? '' : Number(rawValue)
                      const nextValue = typeof parsedValue === 'number' && Number.isFinite(parsedValue) ? parsedValue : ''
                      setDraft(current => ({ ...current, [item.key]: nextValue }))
                      setValidationError(null)
                    }}
                    disabled={!enabled}
                    className="h-10 min-w-0 text-sm tabular-nums"
                    aria-label={`${item.title}: ${t('settings.cleanup.retention.days')}`}
                    aria-describedby={`${item.key}-description`}
                  />
                  {enabled && <span className="text-muted-foreground shrink-0 text-xs font-medium">{t('settings.cleanup.retention.days')}</span>}
                </div>

                <div className="border-border/60 border-t pt-3">
                  <div className="text-muted-foreground flex items-start gap-2 text-xs leading-relaxed">
                    {enabled ? <Combine className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
                    <span>{enabled ? t('settings.cleanup.rollup.cutoff', { days }) : t('settings.cleanup.rollup.disabledHint')}</span>
                  </div>
                </div>
              </section>
            )
          })}
        </div>

        <Alert className="border-sky-500/25 bg-sky-500/5 rtl:[&>svg]:right-4 rtl:[&>svg]:left-auto rtl:[&>svg~*]:pr-7 rtl:[&>svg~*]:pl-0">
          <Info className="h-4 w-4 text-sky-600 dark:text-sky-400" />
          <AlertDescription className="text-xs leading-relaxed sm:text-sm">{t('settings.cleanup.rollup.note')}</AlertDescription>
        </Alert>

        {validationError && (
          <p role="alert" className="text-destructive text-xs font-medium">
            {validationError}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="outline"
            type="button"
            disabled={!isDirty || isSaving}
            onClick={() => {
              setDraft(savedValue)
              setValidationError(null)
            }}
          >
            <RotateCcw className="me-2 h-4 w-4" />
            {t('settings.cleanup.retention.reset')}
          </Button>
          <Button type="button" disabled={!isDirty || isSaving} onClick={handleSave}>
            {isSaving ? <Loader2 className="me-2 h-4 w-4 animate-spin" /> : <Save className="me-2 h-4 w-4" />}
            {isSaving ? t('settings.cleanup.retention.saving') : t('settings.cleanup.rollup.save')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
