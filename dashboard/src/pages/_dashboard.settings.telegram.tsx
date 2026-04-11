import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import { useEffect } from 'react'
import { SubscriptionFormActions } from '@/components/subscriptions/subscription-form-actions'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Bot, Webhook, Shield, Globe, Smartphone, Send, Users, Settings, RefreshCcw } from 'lucide-react'
import { useSettingsContext } from './_dashboard.settings'
import { toast } from 'sonner'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useState } from 'react'
import { useGetWorkersHealth } from '@/service/api'

// Telegram settings validation schema
const telegramSettingsSchema = z.object({
  enable: z.boolean().default(false),
  token: z.string().optional(),
  method: z.enum(['webhook', 'long-polling']).default('webhook'),
  webhook_url: z
    .string()
    .url('Please enter a valid URL')
    .optional()
    .or(z.literal(''))
    .refine(
      url => {
        if (!url || url === '') return true // Allow empty URLs
        try {
          const parsedUrl = new URL(url)
          const allowedPorts = ['443', '80', '88', '8443']
          const port = parsedUrl.port || (parsedUrl.protocol === 'https:' ? '443' : '80')
          return allowedPorts.includes(port)
        } catch {
          return false
        }
      },
      {
        message: 'Telegram webhook URL must use ports 443, 80, 88, or 8443',
      },
    )
    .refine(
      url => {
        if (!url || url === '') return true
        return !url.endsWith('/')
      },
      {
        message: 'Telegram webhook URL must not end with a slash (/).',
      },
    ),
  webhook_secret: z.string().optional(),
  proxy_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  mini_app_login: z.boolean().default(false),
  mini_app_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  for_admins_only: z.boolean().default(true),
})

type TelegramSettingsFormInput = z.input<typeof telegramSettingsSchema>

// Helper function to get current panel URL
const getCurrentPanelUrl = () => {
  const protocol = window.location.protocol
  const host = window.location.host
  return `${protocol}//${host}`
}

// Helper to map frontend Telegram form data to backend payload
function mapTelegramFormToPayload(data: TelegramSettingsFormInput) {
  const mapped = {
    ...data,
    enable: data.enable ?? false,
    method: data.method ?? 'webhook',
    mini_app_login: data.mini_app_login ?? false,
    for_admins_only: data.for_admins_only ?? true,
    token: data.token?.trim() || undefined,
    webhook_url: data.webhook_url?.trim() || undefined,
    webhook_secret: data.webhook_secret?.trim() || undefined,
    proxy_url: data.proxy_url?.trim() || undefined,
    mini_app_web_url: data.mini_app_url?.trim() || undefined,
  }
  delete mapped.mini_app_url
  return { telegram: mapped }
}

export default function TelegramSettings() {
  const { t } = useTranslation()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()
  const [popoverOpen, setPopoverOpen] = useState(false)
  const { data: workersHealth } = useGetWorkersHealth({
    query: {
      retry: false,
      refetchInterval: 30000,
      staleTime: 30000,
    },
  })

  const form = useForm<TelegramSettingsFormInput>({
    resolver: zodResolver(telegramSettingsSchema),
    defaultValues: {
      enable: false,
      token: '',
      method: 'webhook',
      webhook_url: '',
      webhook_secret: '',
      proxy_url: '',
      mini_app_login: false,
      mini_app_url: '',
      for_admins_only: true,
    },
  })

  // Watch the enable, method, and mini_app_login fields for conditional rendering
  const enableTelegram = form.watch('enable')
  const method = form.watch('method')
  const schedulerStatus = workersHealth?.scheduler?.status?.toLowerCase().trim()
  const nodeStatus = workersHealth?.node?.status?.toLowerCase().trim()
  const isMultiWorkerMode = !!workersHealth && !(schedulerStatus === 'disabled' && nodeStatus === 'disabled')

  // Update form when settings are loaded
  useEffect(() => {
    if (settings?.telegram) {
      const telegramData = settings.telegram
      form.reset({
        enable: telegramData.enable || false,
        token: telegramData.token || '',
        method: telegramData.method || 'webhook',
        webhook_url: telegramData.webhook_url || '',
        webhook_secret: telegramData.webhook_secret || '',
        proxy_url: telegramData.proxy_url || '',
        mini_app_login: telegramData.mini_app_login || false,
        mini_app_url: telegramData.mini_app_web_url || '',
        for_admins_only: telegramData.for_admins_only !== undefined ? telegramData.for_admins_only : true,
      })
    }
  }, [settings, form])

  const onSubmit = async (data: TelegramSettingsFormInput) => {
    try {
      // Use the mapping helper
      const filteredData = mapTelegramFormToPayload(data)
      await updateSettings(filteredData)
    } catch (error) {
      // Error handling is done in the parent context
    }
  }

  const handleCancel = () => {
    if (settings?.telegram) {
      const telegramData = settings.telegram
      form.reset({
        enable: telegramData.enable || false,
        token: telegramData.token || '',
        method: telegramData.method || 'webhook',
        webhook_url: telegramData.webhook_url || '',
        webhook_secret: telegramData.webhook_secret || '',
        proxy_url: telegramData.proxy_url || '',
        mini_app_login: telegramData.mini_app_login || false,
        mini_app_url: telegramData.mini_app_web_url || '',
        for_admins_only: telegramData.for_admins_only !== undefined ? telegramData.for_admins_only : true,
      })
      toast.success(t('settings.telegram.cancelSuccess'))
    }
  }

  if (isLoading) {
    return (
      <div className="w-full p-4 sm:py-6 lg:py-8">
        <div className="space-y-6 sm:space-y-8 lg:space-y-10">
          {/* General Settings Skeleton */}
          <div className="space-y-4">
            <div className="space-y-2">
              <div className="h-6 w-48 animate-pulse rounded bg-muted"></div>
              <div className="h-4 w-96 animate-pulse rounded bg-muted"></div>
            </div>
            <div className="h-16 animate-pulse rounded bg-muted"></div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <div className="h-4 w-24 animate-pulse rounded bg-muted"></div>
                  <div className="h-10 animate-pulse rounded bg-muted"></div>
                  <div className="h-3 w-64 animate-pulse rounded bg-muted"></div>
                </div>
              ))}
            </div>
            <div className="h-16 animate-pulse rounded bg-muted"></div>
          </div>

          {/* Action Buttons Skeleton */}
          <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:gap-4">
            <div className="flex-1"></div>
            <div className="flex flex-col gap-3 sm:shrink-0 sm:flex-row sm:gap-4">
              <div className="h-10 w-24 animate-pulse rounded bg-muted"></div>
              <div className="h-10 w-20 animate-pulse rounded bg-muted"></div>
            </div>
          </div>
        </div>
      </div>
    )
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
    <div className="flex min-h-[calc(100vh-200px)] w-full flex-col">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-1 flex-col p-4 sm:py-6 lg:py-8">
          <div className="flex-1 space-y-6 sm:space-y-8 lg:space-y-10">
            {/* General Settings */}
            <div className="space-y-3">
              <div className="space-y-2">
                <h3 className="text-base font-semibold sm:text-lg">{t('settings.telegram.general.title')}</h3>
                <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.general.description')}</p>
              </div>

              {/* Enable Telegram */}
              <FormField
                control={form.control}
                name="enable"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between gap-x-3 space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <Send className="h-4 w-4" />
                        {t('settings.telegram.general.enable')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.general.enableDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {/* Method Selection - Only show when Telegram is enabled */}
              {enableTelegram && (
                <FormField
                  control={form.control}
                  name="method"
                  render={({ field }) => (
                    <FormItem className="space-y-2">
                      <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                        <Settings className="h-4 w-4" />
                        {t('settings.telegram.general.method')}
                      </FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger className="w-full text-xs sm:text-sm">
                            <SelectValue placeholder={t('settings.telegram.general.methodPlaceholder')} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="webhook">
                            <div className="flex items-center gap-2 text-xs sm:text-sm">
                              <Webhook className="h-4 w-4" />
                              {t('settings.telegram.general.webhook')}
                            </div>
                          </SelectItem>
                          <SelectItem value="long-polling" disabled={isMultiWorkerMode}>
                            <div className="flex items-center gap-2 text-xs sm:text-sm">
                              <Send className="h-4 w-4" />
                              {t('settings.telegram.general.longPolling')}
                            </div>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription className="text-xs text-muted-foreground sm:text-sm">
                        {t('settings.telegram.general.methodDescription')}
                        {isMultiWorkerMode ? ` ${t('settings.telegram.general.longPollingDisabledInMultiWorker', { defaultValue: 'Long polling is disabled in multi-worker mode.' })}` : ''}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {/* Configuration Fields - Only show when Telegram is enabled */}
              {enableTelegram && (
                <div className="grid grid-cols-1 gap-3 sm:gap-4 lg:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="token"
                    render={({ field }) => (
                      <FormItem className="space-y-2">
                        <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                          <Bot className="h-4 w-4" />
                          {t('settings.telegram.general.token')}
                        </FormLabel>
                        <FormControl>
                          <PasswordInput placeholder={t('settings.telegram.general.tokenPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
                        </FormControl>
                        <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.general.tokenDescription')}</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {/* Webhook URL - Only show when method is webhook */}
                  {method === 'webhook' && (
                    <FormField
                      control={form.control}
                      name="webhook_url"
                      render={({ field }) => (
                        <FormItem className="space-y-2">
                          <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                            <Webhook className="h-4 w-4" />
                            {t('settings.telegram.general.webhookUrl')}
                          </FormLabel>
                          <div className="relative">
                            <FormControl>
                              <Input type="url" placeholder={t('settings.telegram.general.webhookUrlPlaceholder')} {...field} className="pr-10 font-mono text-xs sm:text-sm" />
                            </FormControl>
                            <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
                              <PopoverTrigger asChild>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="absolute right-1 top-1/2 h-8 w-8 -translate-y-1/2 hover:bg-accent"
                                  onClick={e => {
                                    e.preventDefault()
                                    const currentUrl = getCurrentPanelUrl()
                                    field.onChange(currentUrl)
                                    toast.success(t('settings.telegram.general.panelUrlApplied'))
                                    setPopoverOpen(false)
                                  }}
                                  onMouseEnter={() => setPopoverOpen(true)}
                                  onMouseLeave={() => setPopoverOpen(false)}
                                >
                                  <RefreshCcw className="h-3 w-3" />
                                </Button>
                              </PopoverTrigger>
                              <PopoverContent className="w-72 sm:w-80" side="top" align="end">
                                <div className="space-y-2">
                                  <p className="text-[11px] font-medium">{t('settings.telegram.general.usePanelUrl')}</p>
                                  <p className="text-[11px] text-muted-foreground">{t('settings.telegram.general.usePanelUrlDescription')}</p>
                                </div>
                              </PopoverContent>
                            </Popover>
                          </div>
                          <FormDescription className="text-xs text-muted-foreground sm:text-sm">
                            {t('settings.telegram.general.webhookUrlDescription')}
                            <br />
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  {/* Webhook Secret - Only show when method is webhook */}
                  {method === 'webhook' && (
                    <FormField
                      control={form.control}
                      name="webhook_secret"
                      render={({ field }) => (
                        <FormItem className="space-y-2">
                          <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                            <Shield className="h-4 w-4" />
                            {t('settings.telegram.general.webhookSecret')}
                          </FormLabel>
                          <FormControl>
                            <PasswordInput placeholder={t('settings.telegram.general.webhookSecretPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
                          </FormControl>
                          <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.general.webhookSecretDescription')}</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <FormField
                    control={form.control}
                    name="proxy_url"
                    render={({ field }) => (
                      <FormItem className="space-y-2">
                        <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                          <Globe className="h-4 w-4" />
                          {t('settings.telegram.general.proxyUrl')}
                        </FormLabel>
                        <FormControl>
                          <Input type="url" placeholder={t('settings.telegram.general.proxyUrlPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
                        </FormControl>
                        <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.general.proxyUrlDescription')}</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              )}
            </div>

            {/* Advanced Settings - Only show when Telegram is enabled */}
            {enableTelegram && (
              <>
                <Separator className="my-3" />

                <div className="space-y-3">
                  <div className="space-y-2">
                    <h3 className="text-base font-semibold sm:text-lg">{t('settings.telegram.advanced.title')}</h3>
                    <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.advanced.description')}</p>
                  </div>

                  {/* Mini App Login */}
                  <FormField
                    control={form.control}
                    name="mini_app_login"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                            <Smartphone className="h-4 w-4" />
                            {t('settings.telegram.advanced.miniAppLogin')}
                          </FormLabel>
                          <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.advanced.miniAppLoginDescription')}</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  {/* Mini App URL - only show when mini_app_login is enabled */}
                  {form.watch('mini_app_login') && (
                    <FormField
                      control={form.control}
                      name="mini_app_url"
                      render={({ field }) => (
                        <FormItem className="space-y-2">
                          <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                            <Smartphone className="h-4 w-4" />
                            {t('settings.telegram.advanced.miniAppUrl')}
                          </FormLabel>
                          <FormControl>
                            <Input type="url" placeholder={t('settings.telegram.advanced.miniAppUrlPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
                          </FormControl>
                          <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.advanced.miniAppUrlDescription')}</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  {/* For Admins Only */}
                  <FormField
                    control={form.control}
                    name="for_admins_only"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                            <Users className="h-4 w-4" />
                            {t('settings.telegram.advanced.forAdminsOnly')}
                          </FormLabel>
                          <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.telegram.advanced.forAdminsOnlyDescription')}</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              </>
            )}
          </div>

          <SubscriptionFormActions onCancel={handleCancel} isSaving={isSaving} />
        </form>
      </Form>
    </div>
  )
}
