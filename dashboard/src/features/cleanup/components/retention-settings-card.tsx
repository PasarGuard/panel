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

function normalizeSettings(value?: CleanupSettings | null): CleanupSettings {
  return {
    expired_users_retention_days: value?.expired_users_retention_days ?? null,
    usage_history_retention_days: value?.usage_history_retention_days ?? null,
    node_stats_retention_days: value?.node_stats_retention_days ?? null,
  }
}

export function RetentionSettingsCard({ value, isLoading, isSaving, onSave }: RetentionSettingsCardProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<CleanupSettings>(() => normalizeSettings(value ?? DEFAULT_RETENTION))
  const [validationError, setValidationError] = useState<string | null>(null)

  const savedValue = useMemo(() => normalizeSettings(value ?? DEFAULT_RETENTION), [value])

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

  const setEnabled = (key: RetentionKey, enabled: boolean) => {
    setDraft(current => ({ ...current, [key]: enabled ? ENABLE_DEFAULTS[key] : null }))
    setValidationError(null)
  }

  const setDays = (key: RetentionKey, rawValue: string) => {
    const days = Number(rawValue)
    setDraft(current => ({ ...current, [key]: Number.isFinite(days) ? days : 0 }))
    setValidationError(null)
  }

  const handleSave = async () => {
    const entries = Object.entries(draft) as [RetentionKey, number | null | undefined][]
    const hasInvalidValue = entries.some(([key, days]) => {
      if (days === null || days === undefined) return false
      const minimum = key === 'expired_users_retention_days' ? 0 : 1
      return !Number.isInteger(days) || days < minimum || days > 36_500
    })
    if (hasInvalidValue) {
      setValidationError(t('settings.cleanup.retention.validation'))
      return
    }
    try {
      await onSave(draft)
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
          <div className="border-primary/20 bg-background/80 text-muted-foreground hidden rounded-full border px-3 py-1 text-xs font-medium backdrop-blur sm:block">
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
              <section key={item.key} className="border-border/80 bg-background/75 flex min-h-64 flex-col rounded-xl border p-4 shadow-sm backdrop-blur-sm transition-shadow hover:shadow-md">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className={`${item.surface} ${item.tone} flex h-9 w-9 shrink-0 items-center justify-center rounded-lg`}>
                      <Icon className="h-4.5 w-4.5" />
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold">{item.title}</h3>
                      <p className="text-muted-foreground mt-1 text-xs leading-relaxed">{item.description}</p>
                    </div>
                  </div>
                  <Switch checked={enabled} onCheckedChange={checked => setEnabled(item.key, checked)} aria-label={item.title} />
                </div>

                <div className="mt-5 flex items-center gap-2">
                  <Input
                    type="number"
                    min={item.minimum}
                    max={36_500}
                    step={1}
                    value={enabled ? days : ENABLE_DEFAULTS[item.key]}
                    onChange={event => setDays(item.key, event.target.value)}
                    disabled={!enabled}
                    className="h-10 font-mono text-sm tabular-nums"
                    aria-label={`${item.title}: ${t('settings.cleanup.retention.days')}`}
                  />
                  <span className="text-muted-foreground shrink-0 text-xs font-medium">{t('settings.cleanup.retention.days')}</span>
                </div>

                <div className="mt-auto pt-5" dir="ltr">
                  <div className="text-muted-foreground mb-2 flex items-center justify-between text-[10px] font-medium tracking-wide uppercase">
                    <span>{enabled ? t('settings.cleanup.retention.purge') : t('settings.cleanup.retention.forever')}</span>
                    <span>{t('settings.cleanup.retention.today')}</span>
                  </div>
                  <div className="bg-muted relative h-2 overflow-hidden rounded-full">
                    <div className={`absolute inset-y-0 right-0 rounded-full transition-all ${enabled ? 'bg-primary/70 w-3/4' : 'bg-primary/35 w-full'}`} />
                    {enabled && <div className="border-background bg-primary absolute top-1/2 left-1/4 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 shadow-sm" />}
                  </div>
                  <div className="text-muted-foreground mt-2 flex items-center gap-1.5 text-[11px]">
                    {enabled ? <Trash2 className="h-3 w-3" /> : <CalendarClock className="h-3 w-3" />}
                    <span>{enabled ? t('settings.cleanup.retention.cutoff', { days }) : t('settings.cleanup.retention.disabledHint')}</span>
                  </div>
                </div>
              </section>
            )
          })}
        </div>

        <Alert className="border-amber-500/25 bg-amber-500/5">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertDescription className="text-xs leading-relaxed sm:text-sm">{t('settings.cleanup.retention.cascadeWarning')}</AlertDescription>
        </Alert>

        {validationError && <p className="text-destructive text-xs font-medium">{validationError}</p>}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" type="button" disabled={!isDirty || isSaving} onClick={() => setDraft(savedValue)}>
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
