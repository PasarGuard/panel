import { buildDefaultApplications } from '@/components/subscriptions/default-applications-catalog'
import { SubscriptionApplicationSheet } from '@/components/subscriptions/subscription-application-sheet'
import { SubscriptionApplicationsSection } from '@/components/subscriptions/subscription-applications-section'
import { SubscriptionFormActions } from '@/components/subscriptions/subscription-form-actions'
import { SubscriptionGeneralSettingsSection } from '@/components/subscriptions/subscription-general-settings-section'
import { SubscriptionManualFormatsSection } from '@/components/subscriptions/subscription-manual-formats-section'
import { SubscriptionRulesSection } from '@/components/subscriptions/subscription-rules-section'
import { SubscriptionSettingsSkeleton } from '@/components/subscriptions/subscription-settings-skeleton'
import {
  subscriptionSchema,
  type SubscriptionApplicationFormData,
  type SubscriptionFormData,
  defaultSubscriptionRules,
} from '@/components/subscriptions/subscription-settings-schema'
import { Form } from '@/components/ui/form'
import { Separator } from '@/components/ui/separator'
import { type SubRule as ApiSubRule } from '@/service/api'
import { DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { FieldErrors, useFieldArray, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useSettingsContext } from './_dashboard.settings'

export default function SubscriptionSettings() {
  const { t } = useTranslation()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()
  const [isAddAppOpen, setIsAddAppOpen] = useState(false)

  const form = useForm<SubscriptionFormData>({
    resolver: zodResolver(subscriptionSchema),
    defaultValues: {
      url_prefix: '',
      update_interval: 24,
      support_url: '',
      profile_title: '',
      announce: '',
      announce_url: '',
      allow_browser_config: true,
      disable_sub_template: false,
      randomize_order: false,
      rules: [],
      applications: [],
      manual_sub_request: {
        links: true,
        links_base64: true,
        xray: true,
        wireguard: true,
        sing_box: true,
        clash: true,
        clash_meta: true,
        outline: true,
      },
    },
  })

  const {
    fields: ruleFields,
    append: appendRule,
    remove: removeRule,
    move: moveRule,
  } = useFieldArray({
    control: form.control,
    name: 'rules',
  })

  const {
    fields: applicationFields,
    append: appendApplication,
    remove: removeApplication,
    move: moveApplication,
  } = useFieldArray({
    control: form.control,
    name: 'applications',
  })

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const ruleOldIndex = ruleFields.findIndex(field => field.id === active.id)
      const ruleNewIndex = ruleFields.findIndex(field => field.id === over.id)

      if (ruleOldIndex !== -1 && ruleNewIndex !== -1) {
        moveRule(ruleOldIndex, ruleNewIndex)
        return
      }

      const appOldIndex = applicationFields.findIndex(field => field.id === active.id)
      const appNewIndex = applicationFields.findIndex(field => field.id === over.id)

      if (appOldIndex !== -1 && appNewIndex !== -1) {
        const apps = (form.getValues('applications') || []) as SubscriptionApplicationFormData[]
        const oldPlatform = apps?.[appOldIndex]?.platform
        const newPlatform = apps?.[appNewIndex]?.platform
        if (oldPlatform && newPlatform && oldPlatform === newPlatform) {
          moveApplication(appOldIndex, appNewIndex)
        }
        return
      }
    }
  }

  useEffect(() => {
    if (settings?.subscription) {
      const subscriptionData = settings.subscription
      form.reset({
        url_prefix: subscriptionData.url_prefix || '',
        update_interval: subscriptionData.update_interval || 24,
        support_url: subscriptionData.support_url || '',
        profile_title: subscriptionData.profile_title || '',
        announce: subscriptionData.announce || '',
        announce_url: subscriptionData.announce_url || '',
        allow_browser_config: subscriptionData.allow_browser_config ?? true,
        disable_sub_template: subscriptionData.disable_sub_template ?? false,
        randomize_order: subscriptionData.randomize_order ?? false,
        rules:
          subscriptionData.rules?.map((rule: ApiSubRule) => ({
            pattern: rule.pattern,
            target: rule.target,
            response_headers: Object.fromEntries(
              Object.entries(rule.response_headers || {}).map(([key, value]) => [key, typeof value === 'string' ? value : JSON.stringify(value)]),
            ),
          })) || [],
        applications: subscriptionData.applications || [],
        manual_sub_request: {
          links: subscriptionData.manual_sub_request?.links ?? true,
          links_base64: subscriptionData.manual_sub_request?.links_base64 ?? true,
          xray: subscriptionData.manual_sub_request?.xray ?? true,
          wireguard: subscriptionData.manual_sub_request?.wireguard ?? true,
          sing_box: subscriptionData.manual_sub_request?.sing_box ?? true,
          clash: subscriptionData.manual_sub_request?.clash ?? true,
          clash_meta: subscriptionData.manual_sub_request?.clash_meta ?? true,
          outline: subscriptionData.manual_sub_request?.outline ?? true,
        },
      })
    }
  }, [settings, form])

  const onSubmit = async (data: SubscriptionFormData) => {
    try {
      const processedRules = (data.rules || []).map(rule => ({
        pattern: rule.pattern.trim(),
        target: rule.target,
        response_headers: Object.fromEntries(
          Object.entries(rule.response_headers || {})
            .map(([key, value]) => [key.trim(), value.trim()] as const)
            .filter(([key, value]) => key && value),
        ),
      }))

      const rawApps = (data.applications || [])
        .map(app => ({
          name: app.name?.trim() || '',
          icon_url: app.icon_url?.trim() || undefined,
          import_url: app.import_url?.trim() || undefined,
          description: app.description || {},
          recommended: app.recommended || false,
          platform: app.platform,
          download_links: (app.download_links || [])
            .map(link => ({
              name: link.name?.trim() || '',
              url: link.url?.trim() || '',
              language: link.language,
            }))
            .filter(link => link.name && link.url),
        }))
        .filter(app => app.name)

      const platformHasRecommended: Record<string, boolean> = {}
      const processedApplications = rawApps.map(app => {
        if (app.recommended) {
          if (platformHasRecommended[app.platform]) {
            return { ...app, recommended: false }
          }
          platformHasRecommended[app.platform] = true
        }
        return app
      })

      const filteredData = {
        subscription: {
          ...data,
          url_prefix: data.url_prefix?.trim() || undefined,
          support_url: data.support_url?.trim() || undefined,
          profile_title: data.profile_title?.trim() || undefined,
          announce: data.announce?.trim() || undefined,
          announce_url: data.announce_url?.trim() || undefined,
          rules: processedRules,
          applications: processedApplications,
        },
      }

      await updateSettings(filteredData)
    } catch {
      // Error handling is done in the parent context
    }
  }

  const onInvalid = (errors: FieldErrors<SubscriptionFormData>) => {
    const appsErrors = errors?.applications
    if (Array.isArray(appsErrors)) {
      for (let i = 0; i < appsErrors.length; i++) {
        const appErr = appsErrors[i]
        if (appErr?.name) {
          toast.error(t('validation.required', { field: t('settings.subscriptions.applications.name') }))
          return
        }
        if (appErr?.download_links?.message) {
          toast.error(t('settings.subscriptions.applications.downloadLinksRequired', { defaultValue: 'At least one download link is required' }))
          return
        }
        if (Array.isArray(appErr?.download_links)) {
          for (let j = 0; j < appErr.download_links.length; j++) {
            const linkErr = appErr.download_links[j]
            if (linkErr?.name) {
              toast.error(t('validation.required', { field: t('settings.subscriptions.applications.downloadLinkName', { defaultValue: 'Download link name' }) }))
              return
            }
            if (linkErr?.url) {
              toast.error(t('validation.url', { defaultValue: 'Please enter a valid URL' }))
              return
            }
          }
        }
      }
    }

    const extractFirstMessage = (errObj: unknown): string | undefined => {
      if (!errObj) return undefined
      if (Array.isArray(errObj)) {
        for (const item of errObj) {
          const msg = extractFirstMessage(item)
          if (msg) return msg
        }
      } else if (typeof errObj === 'object' && errObj !== null) {
        const errorRecord = errObj as Record<string, unknown>
        if (typeof errorRecord.message === 'string') return errorRecord.message
        for (const key of Object.keys(errorRecord)) {
          const msg = extractFirstMessage(errorRecord[key])
          if (msg) return msg
        }
      }
      return undefined
    }

    const firstMessage = extractFirstMessage(errors)
    toast.error(firstMessage || t('validation.formHasErrors', { defaultValue: 'Please fix the form errors before submitting' }))
  }

  const handleCancel = () => {
    if (settings?.subscription) {
      const subscriptionData = settings.subscription
      form.reset({
        url_prefix: subscriptionData.url_prefix || '',
        update_interval: subscriptionData.update_interval || 24,
        support_url: subscriptionData.support_url || '',
        profile_title: subscriptionData.profile_title || '',
        announce: subscriptionData.announce || '',
        announce_url: subscriptionData.announce_url || '',
        allow_browser_config: subscriptionData.allow_browser_config ?? true,
        disable_sub_template: subscriptionData.disable_sub_template ?? false,
        randomize_order: subscriptionData.randomize_order ?? false,
        rules:
          subscriptionData.rules?.map((rule: ApiSubRule) => ({
            pattern: rule.pattern,
            target: rule.target,
            response_headers: Object.fromEntries(
              Object.entries(rule.response_headers || {}).map(([key, value]) => [key, typeof value === 'string' ? value : JSON.stringify(value)]),
            ),
          })) || [],
        applications: subscriptionData.applications || [],
        manual_sub_request: {
          links: subscriptionData.manual_sub_request?.links ?? true,
          links_base64: subscriptionData.manual_sub_request?.links_base64 ?? true,
          xray: subscriptionData.manual_sub_request?.xray ?? true,
          wireguard: subscriptionData.manual_sub_request?.wireguard ?? true,
          sing_box: subscriptionData.manual_sub_request?.sing_box ?? true,
          clash: subscriptionData.manual_sub_request?.clash ?? true,
          clash_meta: subscriptionData.manual_sub_request?.clash_meta ?? true,
          outline: subscriptionData.manual_sub_request?.outline ?? true,
        },
      })
      toast.success(t('settings.subscriptions.cancelSuccess'))
    }
  }

  const handleResetToDefault = () => {
    form.setValue('rules', defaultSubscriptionRules)
    toast.success(t('settings.subscriptions.resetToDefaultSuccess', { defaultValue: 'Reset to default settings' }))
  }

  const handleLoadOrResetApplications = () => {
    const defaults = buildDefaultApplications()
    form.setValue('applications', defaults)
    toast.success(
      applicationFields.length === 0
        ? t('settings.subscriptions.applications.loadedDefaults', { defaultValue: 'Defaults loaded' })
        : t('settings.subscriptions.applications.resetToDefaultSuccess', { defaultValue: 'Applications reset to defaults' }),
    )
  }

  const addRule = () => {
    appendRule({ pattern: '', target: 'links', response_headers: {} })
  }

  const addApplication = () => {
    const hasEmptyApplication = applicationFields.some(field => !field.name || field.name.trim() === '')

    if (hasEmptyApplication) {
      toast.error(
        t('settings.subscriptions.applications.duplicateApplication', {
          defaultValue: 'Please fill in the existing application before adding a new one',
        }),
      )
      return
    }
    setIsAddAppOpen(true)
  }

  if (isLoading) {
    return <SubscriptionSettingsSkeleton />
  }

  if (error) {
    return (
      <div className="flex min-h-[400px] items-center justify-center p-4 sm:py-6 lg:py-8">
        <div className="space-y-3 text-center">
          <div className="text-lg text-red-500">⚠️</div>
          <p className="text-sm text-red-500">Error loading settings</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-6 p-4 sm:space-y-8 sm:py-6 lg:space-y-10 lg:py-8">
          <SubscriptionGeneralSettingsSection form={form} />

          <Separator className="my-3" />

          <SubscriptionRulesSection
            form={form}
            ruleFields={ruleFields}
            sensors={sensors}
            onDragEnd={handleDragEnd}
            onResetToDefault={handleResetToDefault}
            onAddRule={addRule}
            onRemoveRule={removeRule}
            isSaving={isSaving}
          />

          <Separator className="my-3" />

          <SubscriptionApplicationsSection
            form={form}
            applicationFields={applicationFields}
            sensors={sensors}
            onDragEnd={handleDragEnd}
            onLoadOrReset={handleLoadOrResetApplications}
            onAddApplication={addApplication}
            onRemoveApplication={removeApplication}
          />

          <Separator className="my-3" />

          <SubscriptionManualFormatsSection form={form} />

          <SubscriptionFormActions onCancel={handleCancel} isSaving={isSaving} />
        </form>
      </Form>

      <SubscriptionApplicationSheet
        variant="create"
        open={isAddAppOpen}
        onOpenChange={setIsAddAppOpen}
        onConfirm={app => {
          appendApplication(app)
          setIsAddAppOpen(false)
        }}
        isSaving={isSaving}
      />
    </div>
  )
}
