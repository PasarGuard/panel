import { useTranslation } from 'react-i18next'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Button } from '@/components/ui/button'
import { useEffect, useState } from 'react'
import { z } from 'zod'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Form, FormControl, FormField, FormItem, FormLabel } from '@/components/ui/form'
import { useSettingsContext } from './_dashboard.settings'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'
import { MessageSquare, FileText, Bot, Webhook, ChevronDown, Settings, Users, Shield, Globe, RotateCcw, UserCog, Users2, ListTodo, Share2Icon, LayoutTemplate, Calendar, ArrowUpDown } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import type { NotificationEnable, NotificationChannels } from '@/service/api'
import { Select, SelectItem, SelectContent, SelectTrigger, SelectValue } from '@/components/ui/select'
const notificationChannelSchema = z.object({
  telegram_chat_id: z.number().optional(),
  telegram_topic_id: z.number().optional(),
  discord_webhook_url: z.string().optional(),
})

const notificationChannelsSchema = z.object({
  admin: notificationChannelSchema.optional(),
  core: notificationChannelSchema.optional(),
  group: notificationChannelSchema.optional(),
  host: notificationChannelSchema.optional(),
  node: notificationChannelSchema.optional(),
  user: notificationChannelSchema.optional(),
  user_template: notificationChannelSchema.optional(),
})

// Validation schema matching the new API structure
const notificationSettingsSchema = z.object({
  notification_enable: z
    .object({
      admin: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
          reset_usage: z.boolean().optional(),
          login: z.boolean().optional(),
        })
        .optional(),
      core: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
        })
        .optional(),
      group: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
        })
        .optional(),
      host: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
          modify_hosts: z.boolean().optional(),
        })
        .optional(),
      node: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
          connect: z.boolean().optional(),
          error: z.boolean().optional(),
        })
        .optional(),
      user: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
          status_change: z.boolean().optional(),
          reset_data_usage: z.boolean().optional(),
          data_reset_by_next: z.boolean().optional(),
          subscription_revoked: z.boolean().optional(),
        })
        .optional(),
      user_template: z
        .object({
          create: z.boolean().optional(),
          modify: z.boolean().optional(),
          delete: z.boolean().optional(),
        })
        .optional(),
      days_left: z.boolean().optional(),
      percentage_reached: z.boolean().optional(),
    })
    .optional(),
  notification_settings: z
    .object({
      notify_telegram: z.boolean().optional(),
      notify_discord: z.boolean().optional(),
      telegram_api_token: z.string().optional(),
      telegram_admin_id: z.number().optional(),
      telegram_channel_id: z.number().optional(),
      telegram_topic_id: z.number().optional(),
      discord_webhook_url: z.string().optional(),
      proxy_url: z.string().optional(),
      max_retries: z.number().min(1).max(10),
      channels: notificationChannelsSchema.optional(),
    })
    .optional(),
})

type NotificationSettingsForm = z.infer<typeof notificationSettingsSchema>

// Define notification permission types with their sub-permissions
type NotificationPermissionConfig = {
  key: keyof NotificationEnable
  translationKey: string
  icon: React.ComponentType<{ className?: string }>
  subPermissions?: Array<{
    key: string
    translationKey: string
  }>
}

const notificationConfigs: NotificationPermissionConfig[] = [
  {
    key: 'admin',
    translationKey: 'admin',
    icon: UserCog,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
      { key: 'reset_usage', translationKey: 'resetUsage' },
      { key: 'login', translationKey: 'login' },
    ],
  },
  {
    key: 'core',
    translationKey: 'core',
    icon: Settings,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
    ],
  },
  {
    key: 'group',
    translationKey: 'group',
    icon: Users2,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
    ],
  },
  {
    key: 'host',
    translationKey: 'host',
    icon: ListTodo,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
      { key: 'modify_hosts', translationKey: 'modifyHosts' },
    ],
  },
  {
    key: 'node',
    translationKey: 'node',
    icon: Share2Icon,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
      { key: 'connect', translationKey: 'connect' },
      { key: 'error', translationKey: 'error' },
    ],
  },
  {
    key: 'user',
    translationKey: 'user',
    icon: Users,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
      { key: 'status_change', translationKey: 'statusChange' },
      { key: 'reset_data_usage', translationKey: 'resetDataUsage' },
      { key: 'data_reset_by_next', translationKey: 'dataResetByNext' },
      { key: 'subscription_revoked', translationKey: 'subscriptionRevoked' },
    ],
  },
  {
    key: 'user_template',
    translationKey: 'userTemplate',
    icon: LayoutTemplate,
    subPermissions: [
      { key: 'create', translationKey: 'create' },
      { key: 'modify', translationKey: 'modify' },
      { key: 'delete', translationKey: 'delete' },
    ],
  },
  {
    key: 'days_left',
    translationKey: 'daysLeft',
    icon: Calendar,
  },
  {
    key: 'percentage_reached',
    translationKey: 'percentageReached',
    icon: ArrowUpDown,
  },
]

type ChannelTargetKey = keyof NotificationChannels

type NotificationChannelFormState = {
  telegram_chat_id?: number
  telegram_topic_id?: number
  discord_webhook_url?: string
}

const channelTargets: Array<{
  key: ChannelTargetKey
  translationKey: string
  icon: React.ComponentType<{ className?: string }>
}> = [
    { key: 'admin', translationKey: 'admin', icon: UserCog },
    { key: 'core', translationKey: 'core', icon: Settings },
    { key: 'group', translationKey: 'group', icon: Users2 },
    { key: 'host', translationKey: 'host', icon: ListTodo },
    { key: 'node', translationKey: 'node', icon: Share2Icon },
    { key: 'user', translationKey: 'user', icon: Users },
    { key: 'user_template', translationKey: 'userTemplate', icon: LayoutTemplate },
  ]

const createDefaultChannelValues = (): Record<ChannelTargetKey, NotificationChannelFormState> =>
  channelTargets.reduce((acc, target) => {
    acc[target.key] = {
      telegram_chat_id: undefined,
      telegram_topic_id: undefined,
      discord_webhook_url: '',
    }
    return acc
  }, {} as Record<ChannelTargetKey, NotificationChannelFormState>)

const populateChannelValues = (channels?: NotificationChannels | null): Record<ChannelTargetKey, NotificationChannelFormState> => {
  const defaults = createDefaultChannelValues()
  channelTargets.forEach(target => {
    const channel = channels?.[target.key]
    defaults[target.key] = {
      telegram_chat_id: channel?.telegram_chat_id ?? undefined,
      telegram_topic_id: channel?.telegram_topic_id ?? undefined,
      discord_webhook_url: channel?.discord_webhook_url ?? '',
    }
  })
  return defaults
}

export default function NotificationSettings() {
  const { t } = useTranslation()

  // Use settings context instead of direct API calls
  const { settings, error, updateSettings, isSaving } = useSettingsContext()

  const form = useForm<NotificationSettingsForm>({
    resolver: zodResolver(notificationSettingsSchema),
    defaultValues: {
      notification_enable: {
        admin: { create: false, modify: false, delete: false, reset_usage: false, login: false },
        core: { create: false, modify: false, delete: false },
        group: { create: false, modify: false, delete: false },
        host: { create: false, modify: false, delete: false, modify_hosts: false },
        node: { create: false, modify: false, delete: false, connect: false, error: false },
        user: {
          create: false,
          modify: false,
          delete: false,
          status_change: false,
          reset_data_usage: false,
          data_reset_by_next: false,
          subscription_revoked: false,
        },
        user_template: { create: false, modify: false, delete: false },
        days_left: false,
        percentage_reached: false,
      },
      notification_settings: {
        notify_telegram: false,
        notify_discord: false,
        telegram_api_token: '',
        telegram_admin_id: undefined,
        telegram_channel_id: undefined,
        telegram_topic_id: undefined,
        discord_webhook_url: '',
        proxy_url: '',
        max_retries: 3,
        channels: createDefaultChannelValues(),
      },
    },
  })

  // Track expanded state for each permission group
  const [expandedPermissions, setExpandedPermissions] = useState<Set<string>>(new Set())

  // Watch the telegram and discord switches to conditionally show/hide sections
  const watchTelegramEnabled = form.watch('notification_settings.notify_telegram')
  const watchDiscordEnabled = form.watch('notification_settings.notify_discord')
  const [activeChannelTab, setActiveChannelTab] = useState<ChannelTargetKey>(channelTargets[0].key)

  // Watch all notification enable fields to ensure switch/checkbox sync
  const watchedEnableFields = form.watch('notification_enable')

  // Helper to toggle all sub-permissions
  const toggleAllSubPermissions = (config: NotificationPermissionConfig, enabled: boolean) => {
    if (!config.subPermissions) return
    const currentData = form.getValues(`notification_enable.${config.key}` as any) || {}
    const updates: any = {}
    config.subPermissions.forEach(sub => {
      updates[sub.key] = enabled
    })
    form.setValue(`notification_enable.${config.key}` as any, {
      ...currentData,
      ...updates,
    })
  }

  // Update form when settings are loaded
  useEffect(() => {
    if (settings) {
      const enableData = settings.notification_enable || {}
      form.reset({
        notification_enable: {
          admin: enableData.admin || { create: false, modify: false, delete: false, reset_usage: false, login: false },
          core: enableData.core || { create: false, modify: false, delete: false },
          group: enableData.group || { create: false, modify: false, delete: false },
          host: enableData.host || { create: false, modify: false, delete: false, modify_hosts: false },
          node: enableData.node || { create: false, modify: false, delete: false, connect: false, error: false },
          user: enableData.user || {
            create: false,
            modify: false,
            delete: false,
            status_change: false,
            reset_data_usage: false,
            data_reset_by_next: false,
            subscription_revoked: false,
          },
          user_template: enableData.user_template || { create: false, modify: false, delete: false },
          days_left: enableData.days_left ?? false,
          percentage_reached: enableData.percentage_reached ?? false,
        },
        notification_settings: {
          notify_telegram: settings.notification_settings?.notify_telegram || false,
          notify_discord: settings.notification_settings?.notify_discord || false,
          telegram_api_token: settings.notification_settings?.telegram_api_token || '',
          telegram_admin_id: settings.notification_settings?.telegram_admin_id || undefined,
          telegram_channel_id: settings.notification_settings?.telegram_channel_id || undefined,
          telegram_topic_id: settings.notification_settings?.telegram_topic_id || undefined,
          discord_webhook_url: settings.notification_settings?.discord_webhook_url || '',
          proxy_url: settings.notification_settings?.proxy_url || '',
          max_retries: settings.notification_settings?.max_retries || 3,
          channels: populateChannelValues(settings.notification_settings?.channels),
        },
      })
    }
  }, [settings, form])

  const onSubmit = (data: NotificationSettingsForm) => {
    const telegramEnabled = Boolean(data.notification_settings?.notify_telegram)
    const discordEnabled = Boolean(data.notification_settings?.notify_discord)

    const channelPayload: NotificationChannels = channelTargets.reduce((acc, target) => {
      const channelData = data.notification_settings?.channels?.[target.key]
      const telegramChatId = telegramEnabled ? channelData?.telegram_chat_id ?? null : null
      const telegramTopicId = telegramEnabled ? channelData?.telegram_topic_id ?? null : null

      const rawWebhook = channelData?.discord_webhook_url ?? ''
      const trimmedWebhook = rawWebhook.trim()
      const discordWebhook = discordEnabled && trimmedWebhook !== '' ? trimmedWebhook : null

      acc[target.key] = {
        telegram_chat_id: telegramChatId,
        telegram_topic_id: telegramTopicId,
        discord_webhook_url: discordWebhook,
      }
      return acc
    }, {} as NotificationChannels)

    // Filter the payload based on enabled switches
    const filteredData = {
      notification_enable: data.notification_enable,
      notification_settings: {
        notify_telegram: telegramEnabled,
        notify_discord: discordEnabled,
        max_retries: data.notification_settings?.max_retries || 3,
        // Only include Telegram settings if Telegram is enabled
        ...(telegramEnabled
          ? {
            telegram_api_token: data.notification_settings?.telegram_api_token || '',
            telegram_admin_id: data.notification_settings?.telegram_admin_id ?? null,
            telegram_channel_id: data.notification_settings?.telegram_channel_id ?? null,
            telegram_topic_id: data.notification_settings?.telegram_topic_id ?? null,
          }
          : {
            telegram_api_token: null,
            telegram_admin_id: null,
            telegram_channel_id: null,
            telegram_topic_id: null,
          }),
        // Only include Discord settings if Discord is enabled
        ...(discordEnabled
          ? {
            discord_webhook_url: data.notification_settings?.discord_webhook_url?.trim() || null,
          }
          : { discord_webhook_url: null }),
        // Only include proxy if either Telegram or Discord is enabled AND proxy URL is not empty. If both disabled, clear the proxy.
        ...(telegramEnabled || discordEnabled
          ? data.notification_settings?.proxy_url && data.notification_settings.proxy_url.trim() !== ''
            ? { proxy_url: data.notification_settings.proxy_url.trim() }
            : {}
          : { proxy_url: null }),
        channels: channelPayload,
      },
    }

    updateSettings(filteredData)
  }

  const handleCancel = () => {
    if (settings) {
      const enableData = settings.notification_enable || {}
      form.reset({
        notification_enable: {
          admin: enableData.admin || { create: false, modify: false, delete: false, reset_usage: false, login: false },
          core: enableData.core || { create: false, modify: false, delete: false },
          group: enableData.group || { create: false, modify: false, delete: false },
          host: enableData.host || { create: false, modify: false, delete: false, modify_hosts: false },
          node: enableData.node || { create: false, modify: false, delete: false, connect: false, error: false },
          user: enableData.user || {
            create: false,
            modify: false,
            delete: false,
            status_change: false,
            reset_data_usage: false,
            data_reset_by_next: false,
            subscription_revoked: false,
          },
          user_template: enableData.user_template || { create: false, modify: false, delete: false },
          days_left: enableData.days_left ?? false,
          percentage_reached: enableData.percentage_reached ?? false,
        },
        notification_settings: {
          notify_telegram: settings.notification_settings?.notify_telegram || false,
          notify_discord: settings.notification_settings?.notify_discord || false,
          telegram_api_token: settings.notification_settings?.telegram_api_token || '',
          telegram_admin_id: settings.notification_settings?.telegram_admin_id || undefined,
          telegram_channel_id: settings.notification_settings?.telegram_channel_id || undefined,
          telegram_topic_id: settings.notification_settings?.telegram_topic_id || undefined,
          discord_webhook_url: settings.notification_settings?.discord_webhook_url || '',
          proxy_url: settings.notification_settings?.proxy_url || '',
          max_retries: settings.notification_settings?.max_retries || 3,
          channels: populateChannelValues(settings.notification_settings?.channels),
        },
      })
      toast.success(t('settings.notifications.cancelSuccess'))
    }
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
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 p-4 sm:space-y-8 sm:py-6 lg:space-y-10 lg:py-8">
          {/* Permissions Section */}
          <div className="space-y-3">
            <div className="space-y-1">
              <h3 className="text-base font-semibold sm:text-lg">{t('settings.notifications.filterTitle')}</h3>
              <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.notifications.filterDescription')}</p>
            </div>

            {/* Permissions List - Responsive Grid */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {/* Permissions with sub-permissions */}
              {notificationConfigs.map(config => {
                // Calculate state directly from watched values for better reactivity
                const permissionData = watchedEnableFields?.[config.key]
                const hasSubPermissions = config.subPermissions && config.subPermissions.length > 0

                let enabledCount = 0
                let anyEnabled = false

                if (hasSubPermissions && permissionData && typeof permissionData === 'object' && config.subPermissions) {
                  enabledCount = config.subPermissions.filter(sub => (permissionData as any)[sub.key]).length
                  anyEnabled = enabledCount > 0
                }

                const totalCount = config.subPermissions?.length || 0
                const isExpanded = expandedPermissions.has(config.key)

                return (
                  <Collapsible
                    key={config.key}
                    open={isExpanded}
                    onOpenChange={open => {
                      const newSet = new Set(expandedPermissions)
                      if (open) {
                        newSet.add(config.key)
                      } else {
                        newSet.delete(config.key)
                      }
                      setExpandedPermissions(newSet)
                    }}
                  >
                    <div
                      className={cn(
                        'group rounded-md border bg-card transition-all duration-200 ease-in-out',
                        isExpanded && 'border-primary/50 bg-accent/30',
                        'hover:border-primary/30 hover:bg-accent/20'
                      )}
                    >
                      <FormField
                        control={form.control}
                        name={`notification_enable.${config.key}` as any}
                        render={() => {
                          const isMainEnabled = hasSubPermissions
                            ? anyEnabled
                            : (typeof watchedEnableFields?.[config.key] === 'boolean' ? watchedEnableFields[config.key] as boolean : false)

                          return (
                            <FormItem>
                              <div className="flex w-full items-center justify-between px-3 py-2.5 transition-colors">
                                <CollapsibleTrigger asChild disabled={!hasSubPermissions}>
                                  <div
                                    className="flex flex-1 items-center gap-2 min-w-0 cursor-pointer"
                                    onClick={(e: React.MouseEvent) => {
                                      // Prevent any click in the trigger area from affecting the switch
                                      e.stopPropagation()
                                    }}
                                  >
                                    <config.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                                    {hasSubPermissions && (
                                      <button
                                        type="button"
                                        className={cn(
                                          'shrink-0 text-muted-foreground transition-all duration-200 hover:text-foreground rounded-sm p-1',
                                          isExpanded && 'rotate-180'
                                        )}
                                        onClick={e => {
                                          e.stopPropagation()
                                          const newSet = new Set(expandedPermissions)
                                          if (isExpanded) {
                                            newSet.delete(config.key)
                                          } else {
                                            newSet.add(config.key)
                                          }
                                          setExpandedPermissions(newSet)
                                        }}
                                      >
                                        <ChevronDown className="h-3.5 w-3.5" />
                                      </button>
                                    )}
                                    <FormLabel
                                      className={cn(
                                        "flex-1 truncate text-sm font-medium sm:text-base",
                                        hasSubPermissions ? "cursor-pointer" : "cursor-pointer"
                                      )}
                                      onClick={(e: React.MouseEvent) => {
                                        // Prevent the form label click from triggering switch toggle
                                        e.preventDefault()
                                        e.stopPropagation()
                                        if (hasSubPermissions) {
                                          // For collapsible items, toggle the accordion
                                          const newSet = new Set(expandedPermissions)
                                          if (isExpanded) {
                                            newSet.delete(config.key)
                                          } else {
                                            newSet.add(config.key)
                                          }
                                          setExpandedPermissions(newSet)
                                        } else {
                                          // For non-collapsible items, toggle the switch
                                          const newChecked = !isMainEnabled
                                          form.setValue(`notification_enable.${config.key}` as any, newChecked)
                                        }
                                      }}
                                    >
                                      {t(`settings.notifications.types.${config.translationKey}`)}
                                      {hasSubPermissions && totalCount > 0 && (
                                        <span className="mx-1.5 text-xs text-muted-foreground">
                                          {enabledCount}/{totalCount}
                                        </span>
                                      )}
                                    </FormLabel>
                                  </div>
                                </CollapsibleTrigger>
                                <FormControl>
                                  <Switch
                                    checked={isMainEnabled}
                                    onCheckedChange={checked => {
                                      if (hasSubPermissions) {
                                        // If toggling on, enable all. If toggling off, disable all.
                                        toggleAllSubPermissions(config, checked)
                                      } else {
                                        form.setValue(`notification_enable.${config.key}` as any, checked)
                                      }
                                    }}
                                    onClick={e => e.stopPropagation()}
                                    className="shrink-0"
                                  />
                                </FormControl>
                              </div>
                            </FormItem>
                          )
                        }}
                      />

                      {hasSubPermissions && (
                        <CollapsibleContent className="overflow-hidden transition-all duration-200 ease-in-out data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
                          <div className="space-y-1 border-t bg-muted/30 px-3 py-2">
                            <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                              {config.subPermissions?.map(sub => (
                                <FormField
                                  key={sub.key}
                                  control={form.control}
                                  name={`notification_enable.${config.key}.${sub.key}` as any}
                                  render={({ field }) => (
                                    <FormItem className="flex items-center gap-x-2 space-y-0 rounded-sm px-2 py-1.5 transition-colors hover:bg-background/50">
                                      <FormControl>
                                        <Checkbox
                                          checked={(permissionData as any)?.[sub.key] || false}
                                          onCheckedChange={(checked) => {
                                            field.onChange(checked)
                                          }}
                                          className="h-4 w-4"
                                        />
                                      </FormControl>
                                      <FormLabel className="cursor-pointer text-xs font-normal leading-none">
                                        {t(`settings.notifications.subPermissions.${sub.translationKey}`)}
                                      </FormLabel>
                                    </FormItem>
                                  )}
                                />
                              ))}
                            </div>
                          </div>
                        </CollapsibleContent>
                      )}
                    </div>
                  </Collapsible>
                )
              })}

            </div>
          </div>

          <Separator className="my-3" />

          {/* Telegram */}
          <div className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-0.5">
                <h3 className="text-base font-semibold sm:text-lg">{t('settings.notifications.telegram.title')}</h3>
                <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.notifications.telegram.description')}</p>
              </div>
              <FormField
                control={form.control}
                name="notification_settings.notify_telegram"
                render={({ field }) => (
                  <FormItem className="flex shrink-0 items-center gap-2 space-y-0">
                    <FormLabel className="text-xs font-medium sm:text-sm">{t('settings.notifications.title')}</FormLabel>
                    <FormControl>
                      <Switch checked={field.value || false} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            {/* Only show Telegram settings when enabled */}
            {watchTelegramEnabled && (
              <div className="space-y-3 rounded-md border bg-card p-3">
                <div className="space-y-1.5">
                  <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                    <Bot className="h-3.5 w-3.5" />
                    {t('settings.notifications.telegram.apiToken')}
                  </Label>
                  <FormField
                    control={form.control}
                    name="notification_settings.telegram_api_token"
                    render={({ field }) => (
                      <FormControl>
                        <PasswordInput {...field} className="h-9 text-xs font-mono sm:text-sm" placeholder="1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11" />
                      </FormControl>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                      <Shield className="h-3.5 w-3.5" />
                      {t('settings.notifications.telegram.adminId')}
                    </Label>
                    <FormField
                      control={form.control}
                      name="notification_settings.telegram_admin_id"
                      render={({ field }) => {
                        const [inputValue, setInputValue] = useState(field.value?.toString() ?? '')

                        useEffect(() => {
                          setInputValue(field.value?.toString() ?? '')
                        }, [field.value])

                        return (
                          <FormControl>
                            <Input
                              type="text"
                              name={field.name}
                              ref={field.ref}
                              value={inputValue}
                              onChange={e => {
                                const value = e.target.value
                                setInputValue(value)
                                if (value === '') {
                                  field.onChange(undefined)
                                } else if (/^-?\d+$/.test(value)) {
                                  field.onChange(parseInt(value))
                                }
                              }}
                              onBlur={() => {
                                if (inputValue !== '' && !/^-?\d+$/.test(inputValue)) {
                                  setInputValue(field.value?.toString() ?? '')
                                }
                                field.onBlur()
                              }}
                              className="h-9 text-xs sm:text-sm"
                              placeholder="123456789"
                            />
                          </FormControl>
                        )
                      }}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                      <MessageSquare className="h-3.5 w-3.5" />
                      {t('settings.notifications.telegram.channelId')}
                    </Label>
                    <FormField
                      control={form.control}
                      name="notification_settings.telegram_channel_id"
                      render={({ field }) => {
                        const [inputValue, setInputValue] = useState(field.value?.toString() ?? '')

                        useEffect(() => {
                          setInputValue(field.value?.toString() ?? '')
                        }, [field.value])

                        return (
                          <FormControl>
                            <Input
                              type="text"
                              name={field.name}
                              ref={field.ref}
                              value={inputValue}
                              onChange={e => {
                                const value = e.target.value
                                setInputValue(value)
                                if (value === '') {
                                  field.onChange(undefined)
                                } else if (/^-?\d+$/.test(value)) {
                                  field.onChange(parseInt(value))
                                }
                              }}
                              onBlur={() => {
                                if (inputValue !== '' && !/^-?\d+$/.test(inputValue)) {
                                  setInputValue(field.value?.toString() ?? '')
                                }
                                field.onBlur()
                              }}
                              className="h-9 text-xs sm:text-sm"
                              placeholder="-1001234567890"
                            />
                          </FormControl>
                        )
                      }}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                      <FileText className="h-3.5 w-3.5" />
                      {t('settings.notifications.telegram.topicId')}
                    </Label>
                    <FormField
                      control={form.control}
                      name="notification_settings.telegram_topic_id"
                      render={({ field }) => {
                        const [inputValue, setInputValue] = useState(field.value?.toString() ?? '')

                        useEffect(() => {
                          setInputValue(field.value?.toString() ?? '')
                        }, [field.value])

                        return (
                          <FormControl>
                            <Input
                              type="text"
                              name={field.name}
                              ref={field.ref}
                              value={inputValue}
                              onChange={e => {
                                const value = e.target.value
                                setInputValue(value)
                                if (value === '') {
                                  field.onChange(undefined)
                                } else if (/^-?\d+$/.test(value)) {
                                  field.onChange(parseInt(value))
                                }
                              }}
                              onBlur={() => {
                                if (inputValue !== '' && !/^-?\d+$/.test(inputValue)) {
                                  setInputValue(field.value?.toString() ?? '')
                                }
                                field.onBlur()
                              }}
                              className="h-9 text-xs sm:text-sm"
                              placeholder="123"
                            />
                          </FormControl>
                        )
                      }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <Separator className="my-3" />

          {/* Discord */}
          <div className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-0.5">
                <h3 className="text-base font-semibold sm:text-lg">{t('settings.notifications.discord.title')}</h3>
                <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.notifications.discord.description')}</p>
              </div>
              <FormField
                control={form.control}
                name="notification_settings.notify_discord"
                render={({ field }) => (
                  <FormItem className="flex shrink-0 items-center gap-2 space-y-0">
                    <FormLabel className="text-xs font-medium sm:text-sm">{t('settings.notifications.title')}</FormLabel>
                    <FormControl>
                      <Switch checked={field.value || false} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            {/* Only show Discord settings when enabled */}
            {watchDiscordEnabled && (
              <div className="space-y-1.5 rounded-md border bg-card p-3">
                <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                  <Webhook className="h-3.5 w-3.5" />
                  {t('settings.notifications.discord.webhookUrl')}
                </Label>
                <FormField
                  control={form.control}
                  name="notification_settings.discord_webhook_url"
                  render={({ field }) => (
                    <FormControl>
                      <PasswordInput {...field} className="h-9 text-xs font-mono sm:text-sm" placeholder="https://discord.com/api/webhooks/1234567890/ABC-DEF1234ghIkl-zyx57W2v1u123ew11" />
                    </FormControl>
                  )}
                />
              </div>
            )}
          </div>

          {/* Advanced Settings & Channel Overrides - Only show if either Telegram or Discord is enabled */}
          {(watchTelegramEnabled || watchDiscordEnabled) && (
            <div className="space-y-4">
              <Separator className="my-3" />
              <div className="space-y-0.5">
                <h3 className="text-base font-semibold sm:text-lg">{t('settings.notifications.advanced.title')}</h3>
                <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.notifications.advanced.description')}</p>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1.5 rounded-md border bg-card p-3">
                  <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                    <Globe className="h-3.5 w-3.5" />
                    {t('settings.notifications.advanced.proxyUrl')}
                  </Label>
                  <FormField
                    control={form.control}
                    name="notification_settings.proxy_url"
                    render={({ field }) => (
                      <FormControl>
                        <Input {...field} className="h-9 text-xs sm:text-sm" placeholder="https://proxy.example.com:8080" />
                      </FormControl>
                    )}
                  />
                </div>

                <div className="space-y-1.5 rounded-md border bg-card p-3">
                  <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                    <RotateCcw className="h-3.5 w-3.5" />
                    {t('settings.notifications.advanced.maxRetries')}
                  </Label>
                  <FormField
                    control={form.control}
                    name="notification_settings.max_retries"
                    render={({ field }) => (
                      <FormControl>
                        <Input
                          type="number"
                          min="1"
                          max="10"
                          name={field.name}
                          ref={field.ref}
                          value={field.value ?? ''}
                          onChange={e => {
                            const value = e.target.value
                            if (value === '') {
                              field.onChange(3)
                            } else if (/^\d+$/.test(value)) {
                              field.onChange(parseInt(value))
                            }
                          }}
                          onBlur={field.onBlur}
                          className="h-9 text-xs sm:text-sm"
                          placeholder="3"
                        />
                      </FormControl>
                    )}
                  />
                </div>
              </div>

              <Separator className="my-3" />
              <div className="space-y-0.5">
                <h3 className="text-base font-semibold sm:text-lg">{t('settings.notifications.channels.title')}</h3>
                <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.notifications.channels.description')}</p>
              </div>


              <div className="space-y-3">
                <FormItem>
                  <Select onValueChange={value => setActiveChannelTab(value as ChannelTargetKey)} value={activeChannelTab}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {channelTargets.map(target => (
                        <SelectItem key={target.key} value={target.key}>
                          <div className="flex items-center gap-1.5">
                            <target.icon className="h-3.5 w-3.5" />
                            {t(`settings.notifications.types.${target.translationKey}`)}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormItem>

                {(() => {
                  const target = channelTargets.find(target => target.key === activeChannelTab)
                  if (!target) return null
                  
                  return (
                    <div key={activeChannelTab} className="space-y-3 rounded-md border bg-card p-3">
                      <div className="space-y-1">
                        <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                          <target.icon className="h-3.5 w-3.5" />
                          {t(`settings.notifications.types.${target.translationKey}`)}
                        </Label>
                        <p className="text-xs text-muted-foreground">{t('settings.notifications.channels.hint')}</p>
                      </div>

                      {watchTelegramEnabled && (
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          <div className="space-y-1.5">
                            <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                              <MessageSquare className="h-3.5 w-3.5" />
                              {t('settings.notifications.telegram.channelId')}
                            </Label>
                            <FormField
                              key={`telegram_chat_id_${activeChannelTab}`}
                              control={form.control}
                              name={`notification_settings.channels.${activeChannelTab}.telegram_chat_id`}
                              render={({ field }) => {
                                const [inputValue, setInputValue] = useState(field.value?.toString() ?? '')

                                useEffect(() => {
                                  setInputValue(field.value?.toString() ?? '')
                                }, [field.value, activeChannelTab])

                                return (
                                  <FormControl>
                                    <Input
                                      type="text"
                                      name={field.name}
                                      ref={field.ref}
                                      value={inputValue}
                                      onChange={e => {
                                        const value = e.target.value
                                        setInputValue(value)
                                        if (value === '') {
                                          field.onChange(undefined)
                                        } else if (/^-?\d+$/.test(value)) {
                                          field.onChange(parseInt(value))
                                        }
                                      }}
                                      onBlur={() => {
                                        if (inputValue !== '' && !/^-?\d+$/.test(inputValue)) {
                                          setInputValue(field.value?.toString() ?? '')
                                        }
                                        field.onBlur()
                                      }}
                                      className="h-9 text-xs sm:text-sm"
                                      placeholder="-1001234567890"
                                    />
                                  </FormControl>
                                )
                              }}
                            />
                          </div>

                          <div className="space-y-1.5">
                            <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                              <FileText className="h-3.5 w-3.5" />
                              {t('settings.notifications.telegram.topicId')}
                            </Label>
                            <FormField
                              key={`telegram_topic_id_${activeChannelTab}`}
                              control={form.control}
                              name={`notification_settings.channels.${activeChannelTab}.telegram_topic_id`}
                              render={({ field }) => {
                                const [inputValue, setInputValue] = useState(field.value?.toString() ?? '')

                                useEffect(() => {
                                  setInputValue(field.value?.toString() ?? '')
                                }, [field.value, activeChannelTab])

                                return (
                                  <FormControl>
                                    <Input
                                      type="text"
                                      name={field.name}
                                      ref={field.ref}
                                      value={inputValue}
                                      onChange={e => {
                                        const value = e.target.value
                                        setInputValue(value)
                                        if (value === '') {
                                          field.onChange(undefined)
                                        } else if (/^-?\d+$/.test(value)) {
                                          field.onChange(parseInt(value))
                                        }
                                      }}
                                      onBlur={() => {
                                        if (inputValue !== '' && !/^-?\d+$/.test(inputValue)) {
                                          setInputValue(field.value?.toString() ?? '')
                                        }
                                        field.onBlur()
                                      }}
                                      className="h-9 text-xs sm:text-sm"
                                      placeholder="123"
                                    />
                                  </FormControl>
                                )
                              }}
                            />
                          </div>
                        </div>
                      )}

                      {watchDiscordEnabled && (
                        <div className="space-y-1.5">
                          <Label className="flex items-center gap-1.5 text-xs font-medium sm:text-sm">
                            <Webhook className="h-3.5 w-3.5" />
                            {t('settings.notifications.discord.webhookUrl')}
                          </Label>
                          <FormField
                            key={`discord_webhook_url_${activeChannelTab}`}
                            control={form.control}
                            name={`notification_settings.channels.${activeChannelTab}.discord_webhook_url`}
                            render={({ field }) => (
                              <FormControl>
                                <PasswordInput {...field} className="h-9 text-xs font-mono sm:text-sm" placeholder="https://discord.com/api/webhooks/1234567890/ABC-DEF1234ghIkl-zyx57W2v1u123ew11" />
                              </FormControl>
                            )}
                          />
                        </div>
                      )}

                      {!watchTelegramEnabled && !watchDiscordEnabled && (
                        <p className="text-xs text-muted-foreground">
                          {t('settings.notifications.channels.description')}
                        </p>
                      )}
                    </div>
                  )
                })()}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex flex-col gap-2 pt-3 sm:flex-row sm:justify-end sm:gap-3">
            <Button type="button" variant="outline" onClick={handleCancel} className="w-full sm:w-auto" disabled={isSaving}>
              {t('cancel')}
            </Button>
            <Button type="submit" disabled={isSaving} isLoading={isSaving} loadingText={t('saving')} className="w-full sm:w-auto">
              {t('save')}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
