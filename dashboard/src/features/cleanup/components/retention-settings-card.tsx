import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import type { CleanupSettings } from '@/service/api'
import { Activity, AlertTriangle, CalendarClock, ChartNoAxesCombined, Loader2, RotateCcw, Save, Trash2, UserRoundX } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

type RetentionKey = keyof CleanupSettings
type RetentionValue = number | null | ''
type RetentionDraft = Record<RetentionKey, RetentionValue>

interface RetentionSettingsCardProps {
  value?: CleanupSettings | null
  isLoading: boolean
  isSaving: boolean
  onSave: (value: CleanupSettings) => Promise<void>
}

const DEFAULT_RETENTION: Required<CleanupSettings> = {
  expired_users_retention_days: null,
  usage_history_retention_days: 90,
  node_stats_retention_days: 30,
}

const ENABLE_DEFAULTS: Record<RetentionKey, number> = {
  expired_users_retention_days: 30,
  usage_history_retention_days: 90,
  node_stats_retention_days: 30,
}

/** Render and validate the independent cleanup-retention controls. */
export function RetentionSettingsCard({ value, isLoading, isSaving, onSave }: RetentionSettingsCardProps) {
  const { t } = useTranslation()
  const initialValue = value ?? DEFAULT_RETENTION
  const [draft, setDraft] = useState<RetentionDraft>({
    expired_users_retention_days: initialValue.expired_users_retention_days ?? null,
    usage_history_retention_days: initialValue.usage_history_retention_days ?? null,
    node_stats_retention_days: initialValue.node_stats_retention_days ?? null,
  })
  const [validationError, setValidationError] = useState<string | null>(null)

  const savedValue = useMemo(() => {
    const persistedValue = value ?? DEFAULT_RETENTION
    return {
      expired_users_retention_days: persistedValue.expired_users_retention_days ?? null,
      usage_history_retention_days: persistedValue.usage_history_retention_days ?? null,
      node_stats_retention_days: persistedValue.node_stats_retention_days ?? null,
    }
  }, [value])

  useEffect(() => {
    setDraft(savedValue)
    setValidationError(null)
  }, [savedValue])

  const retentionItems = [
    {
      key: 'expired_users_retention_days' as const,
      icon: UserRoundX,
      title: t('settings.cleanup.retention.expiredUsers.title'),
      description: t('settings.cleanup.retention.expiredUsers.description'),
      minimum: 0,
      tone: 'text-amber-600 dark:text-amber-400',
      surface: 'bg-amber-500/10',
    },
    {
      key: 'usage_history_retention_days' as const,
      icon: ChartNoAxesCombined,
      title: t('settings.cleanup.retention.usageHistory.title'),
      description: t('settings.cleanup.retention.usageHistory.description'),
      minimum: 1,
      tone: 'text-sky-600 dark:text-sky-400',
      surface: 'bg-sky-500/10',
    },
    {
      key: 'node_stats_retention_days' as const,
      icon: Activity,
      title: t('settings.cleanup.retention.nodeStats.title'),
      description: t('settings.cleanup.retention.nodeStats.description'),
      minimum: 1,
      tone: 'text-emerald-600 dark:text-emerald-400',
      surface: 'bg-emerald-500/10',
    },
  ]

  const isDirty = JSON.stringify(draft) !== JSON.stringify(savedValue)

  /** Enable a rule with its default or disable it indefinitely. */
  const setEnabled = (key: RetentionKey, enabled: boolean) => {
    setDraft(current => ({ ...current, [key]: enabled ? ENABLE_DEFAULTS[key] : null }))
    setValidationError(null)
  }

  /** Validate and persist the complete retention-policy draft. */
  const handleSave = async () => {
    const entries = Object.entries(draft) as [RetentionKey, RetentionValue][]
    const hasInvalidValue = entries.some(([key, days]) => {
      if (days === '') return true
      if (days === null) return false
      const minimum = key === 'expired_users_retention_days' ? 0 : 1
      return !Number.isInteger(days) || days < minimum || days > 36_500
    })
    if (hasInvalidValue) {
      setValidationError(t('settings.cleanup.retention.validation'))
      return
    }
    try {
      await onSave({
        expired_users_retention_days: draft.expired_users_retention_days === '' ? null : draft.expired_users_retention_days,
        usage_history_retention_days: draft.usage_history_retention_days === '' ? null : draft.usage_history_retention_days,
        node_stats_retention_days: draft.node_stats_retention_days === '' ? null : draft.node_stats_retention_days,
      })
    } catch {
      // The shared settings mutation already surfaces the API error as a toast.
      // Keep the draft intact so the user can correct or retry it.
    }
  }

  if (isLoading) {
    return <Skeleton className="h-[430px] w-full rounded-xl" />
  }

  return (
    <Card className="border-primary/20 from-primary/5 overflow-hidden bg-gradient-to-br via-transparent to-transparent">
      <CardHeader className="border-border/70 border-b p-4 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2 text-base font-semibold sm:text-lg">
              <span className="bg-primary/10 text-primary flex h-9 w-9 items-center justify-center rounded-lg">
                <CalendarClock className="h-5 w-5" />
              </span>
              {t('settings.cleanup.retention.title')}
            </CardTitle>
            <CardDescription className="max-w-2xl text-xs leading-relaxed sm:text-sm">{t('settings.cleanup.retention.description')}</CardDescription>
          </div>
          <div className="border-primary/20 bg-background/80 text-muted-foreground hidden shrink-0 rounded-full border px-3 py-1 text-xs font-medium backdrop-blur sm:block">
            {t('settings.cleanup.retention.hourly')}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 p-4 sm:p-6">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {retentionItems.map(item => {
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
                    min={item.minimum}
                    max={36_500}
                    step={1}
                    value={enabled ? days : t('settings.cleanup.retention.forever')}
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
                    {enabled ? <Trash2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <CalendarClock className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
                    <span>{enabled ? t('settings.cleanup.retention.cutoff', { days }) : t('settings.cleanup.retention.disabledHint')}</span>
                  </div>
                </div>
              </section>
            )
          })}
        </div>

        <Alert className="border-amber-500/25 bg-amber-500/5 rtl:[&>svg]:right-4 rtl:[&>svg]:left-auto rtl:[&>svg~*]:pr-7 rtl:[&>svg~*]:pl-0">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertDescription className="text-xs leading-relaxed sm:text-sm">{t('settings.cleanup.retention.cascadeWarning')}</AlertDescription>
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
            {isSaving ? t('settings.cleanup.retention.saving') : t('settings.cleanup.retention.save')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
