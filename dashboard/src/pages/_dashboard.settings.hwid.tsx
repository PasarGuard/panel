import { DecimalInput } from '@/components/common/decimal-input'
import { SubscriptionFormActions } from '@/features/subscriptions/components/subscription-form-actions'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { useSettingsContext } from './_dashboard.settings'

const hwidSettingsSchema = z
  .object({
    enabled: z.boolean().default(false),
    forced: z.boolean().default(false),
    fallback_limit: z.number().min(0).default(0),
    min_limit: z.number().min(0).default(0),
    max_limit: z.number().min(0).default(0),
  })
  .superRefine((data, ctx) => {
    if (data.max_limit > 0 && data.min_limit > data.max_limit) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'settings.hwid.validation.minMax',
        path: ['min_limit'],
      })
    }
  })

type HwidSettingsFormInput = z.input<typeof hwidSettingsSchema>

const defaultValues: HwidSettingsFormInput = {
  enabled: false,
  forced: false,
  fallback_limit: 0,
  min_limit: 0,
  max_limit: 0,
}

export default function HwidSettings() {
  const { t } = useTranslation()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()

  const formValues = useMemo<HwidSettingsFormInput>(() => {
    const hwid = settings?.hwid
    if (!hwid) return defaultValues
    return {
      enabled: hwid.enabled ?? false,
      forced: hwid.forced ?? false,
      fallback_limit: hwid.fallback_limit ?? 0,
      min_limit: hwid.min_limit ?? 0,
      max_limit: hwid.max_limit ?? 0,
    }
  }, [settings?.hwid])

  const form = useForm<HwidSettingsFormInput>({
    resolver: zodResolver(hwidSettingsSchema),
    values: formValues,
  })

  const onSubmit = async (data: HwidSettingsFormInput) => {
    try {
      await updateSettings({
        hwid: {
          enabled: data.enabled,
          forced: data.enabled ? data.forced : false,
          fallback_limit: Math.floor(data.fallback_limit ?? 0),
          min_limit: Math.floor(data.min_limit ?? 0),
          max_limit: Math.floor(data.max_limit ?? 0),
        },
      })
    } catch {
      // Error handling is done in the parent context.
    }
  }

  const handleCancel = () => {
    form.reset(formValues)
    toast.success(t('settings.hwid.cancelSuccess', { defaultValue: 'Changes cancelled and original HWID settings restored' }))
  }

  const hwidEnabled = form.watch('enabled')

  if (isLoading) {
    return (
      <div className="w-full p-4 sm:py-6 lg:py-8">
        <div className="space-y-6">
          <Skeleton className="h-16 w-full" />
          <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-[400px] items-center justify-center p-4 sm:py-6 lg:py-8">
        <p className="text-sm text-destructive">{t('settings.hwid.loadError', { defaultValue: 'Failed to load HWID settings' })}</p>
      </div>
    )
  }

  return (
    <div className="w-full">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 p-4 sm:py-6 lg:py-8">
          <section className="space-y-4">
            <div className="space-y-1.5">
              <h3 className="text-base font-semibold sm:text-lg">
                {t('settings.hwid.policy.title', { defaultValue: 'Device registration policy' })}
              </h3>
              <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground sm:text-sm">
                {t('settings.hwid.policy.description', { defaultValue: 'Control subscription access by registered hardware IDs.' })}
              </p>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <FormField
                control={form.control}
                name="enabled"
                render={({ field }) => (
                  <FormItem className="flex-row items-center justify-between gap-4 rounded-md border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="min-w-0 flex-1 space-y-1">
                      <FormLabel className="cursor-pointer text-sm font-medium">{t('settings.hwid.enabled.title', { defaultValue: 'Enable HWID checks' })}</FormLabel>
                      <FormDescription className="text-xs leading-relaxed sm:text-sm">
                        {t('settings.hwid.enabled.description', { defaultValue: 'Register and enforce device IDs on subscription requests.' })}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} className="shrink-0" />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="forced"
                render={({ field }) => (
                  <FormItem className="flex-row items-center justify-between gap-4 rounded-md border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="min-w-0 flex-1 space-y-1">
                      <FormLabel className="cursor-pointer text-sm font-medium">{t('settings.hwid.forced.title', { defaultValue: 'Require HWID header' })}</FormLabel>
                      <FormDescription className="text-xs leading-relaxed sm:text-sm">
                        {t('settings.hwid.forced.description', { defaultValue: 'Reject subscription requests that do not send X-HWID.' })}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} disabled={!hwidEnabled} className="shrink-0" />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
          </section>

          <section className="space-y-4">
            <div className="space-y-1.5">
              <h3 className="text-base font-semibold sm:text-lg">{t('settings.hwid.limits.title', { defaultValue: 'Device limits' })}</h3>
              <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground sm:text-sm">
                {t('settings.hwid.limits.description', { defaultValue: 'Set the default device count and optional bounds for per-user HWID limits.' })}
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <FormField
                control={form.control}
                name="fallback_limit"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-sm font-medium">{t('settings.hwid.fallbackLimit.title', { defaultValue: 'Fallback limit' })}</FormLabel>
                    <FormControl>
                      <DecimalInput placeholder="0" value={field.value} emptyValue={0} zeroValue={0} normalizeDisplayValueOnBlur={Math.floor} onValueChange={value => field.onChange(value ?? 0)} />
                    </FormControl>
                    <FormDescription className="text-xs leading-relaxed sm:text-sm">
                      {t('settings.hwid.fallbackLimit.description', { defaultValue: 'Used when a user does not have an explicit HWID limit.' })}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="min_limit"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-sm font-medium">{t('settings.hwid.minLimit.title', { defaultValue: 'Minimum limit' })}</FormLabel>
                    <FormControl>
                      <DecimalInput placeholder="0" value={field.value} emptyValue={0} zeroValue={0} normalizeDisplayValueOnBlur={Math.floor} onValueChange={value => field.onChange(value ?? 0)} />
                    </FormControl>
                    <FormDescription className="text-xs leading-relaxed sm:text-sm">
                      {t('settings.hwid.minLimit.description', { defaultValue: 'Lower bound applied to per-user limits. Use 0 to disable.' })}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="max_limit"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-sm font-medium">{t('settings.hwid.maxLimit.title', { defaultValue: 'Maximum limit' })}</FormLabel>
                    <FormControl>
                      <DecimalInput placeholder="0" value={field.value} emptyValue={0} zeroValue={0} normalizeDisplayValueOnBlur={Math.floor} onValueChange={value => field.onChange(value ?? 0)} />
                    </FormControl>
                    <FormDescription className="text-xs leading-relaxed sm:text-sm">
                      {t('settings.hwid.maxLimit.description', { defaultValue: 'Upper bound applied to per-user limits. Use 0 to disable.' })}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </section>

          <SubscriptionFormActions onCancel={handleCancel} isSaving={isSaving} />
        </form>
      </Form>
    </div>
  )
}
