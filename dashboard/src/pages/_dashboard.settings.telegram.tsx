import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useTranslation } from 'react-i18next'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/ui/password-input'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Bot, Webhook, Shield, Globe, Smartphone, Send, Users, Settings } from 'lucide-react'
import { useSettingsContext } from './_dashboard.settings'
import { toast } from 'sonner'

// Telegram settings validation schema
const telegramSettingsSchema = z.object({
  enable: z.boolean().default(false),
  token: z.string().optional(),
  method: z.enum(['webhook', 'long-polling']).default('webhook'),
  webhook_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')).refine((url) => {
    if (!url || url === '') return true; // Allow empty URLs
    try {
      const parsedUrl = new URL(url);
      const allowedPorts = ['443', '80', '88', '8443'];
      const port = parsedUrl.port || (parsedUrl.protocol === 'https:' ? '443' : '80');
      return allowedPorts.includes(port);
    } catch {
      return false;
    }
  }, {
    message: 'Telegram webhook URL must use ports 443, 80, 88, or 8443'
  })
  .refine((url) => {
    if (!url || url === '') return true;
    return !url.endsWith('/');
  }, {
    message: 'Telegram webhook URL must not end with a slash (/).'
  }),
  webhook_secret: z.string().optional(),
  proxy_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  mini_app_login: z.boolean().default(false),
  mini_app_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  for_admins_only: z.boolean().default(true),
})

type TelegramSettingsForm = z.infer<typeof telegramSettingsSchema>

// Helper to map frontend Telegram form data to backend payload
function mapTelegramFormToPayload(data: TelegramSettingsForm) {
  const mapped = {
    ...data,
    token: data.token?.trim() || undefined,
    webhook_url: data.webhook_url?.trim() || undefined,
    webhook_secret: data.webhook_secret?.trim() || undefined,
    proxy_url: data.proxy_url?.trim() || undefined,
    mini_app_web_url: data.mini_app_url?.trim() || undefined,
    for_admins_only: data.for_admins_only,
  };
  delete mapped.mini_app_url;
  return { telegram: mapped };
}

export default function TelegramSettings() {
  const { t } = useTranslation()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()

  const form = useForm<TelegramSettingsForm>({
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
    }
  })

  // Watch the enable, method, and mini_app_login fields for conditional rendering
  const enableTelegram = form.watch('enable')
  const method = form.watch('method')

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

  const onSubmit = async (data: TelegramSettingsForm) => {
    try {
      // Use the mapping helper
      const filteredData = mapTelegramFormToPayload(data);
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

  // Check if save button should be disabled
  const isSaveDisabled = isSaving

  if (isLoading) {
    return (
      <div className="w-full  p-4 sm:py-6 lg:py-8">
        <div className="space-y-6 sm:space-y-8 lg:space-y-10">
          {/* General Settings Skeleton */}
          <div className="space-y-4">
            <div className="space-y-2">
              <div className="h-6 bg-muted rounded w-48 animate-pulse"></div>
              <div className="h-4 bg-muted rounded w-96 animate-pulse"></div>
            </div>
            <div className="h-16 bg-muted rounded animate-pulse"></div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <div className="h-4 bg-muted rounded w-24 animate-pulse"></div>
                  <div className="h-10 bg-muted rounded animate-pulse"></div>
                  <div className="h-3 bg-muted rounded w-64 animate-pulse"></div>
                </div>
              ))}
            </div>
            <div className="h-16 bg-muted rounded animate-pulse"></div>
          </div>
          
          {/* Action Buttons Skeleton */}
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-4">
            <div className="flex-1"></div>
            <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:shrink-0">
              <div className="h-10 bg-muted rounded w-24 animate-pulse"></div>
              <div className="h-10 bg-muted rounded w-20 animate-pulse"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[400px] p-4 sm:py-6 lg:py-8">
        <div className="text-center space-y-3">
          <div className="text-red-500 text-lg">⚠️</div>
          <p className="text-sm text-red-500">Error loading settings</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full min-h-[calc(100vh-200px)] flex flex-col">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col flex-1 p-4 sm:py-6 lg:py-8">
          <div className="flex-1 space-y-6 sm:space-y-8 lg:space-y-10">
          
          {/* General Settings */}
          <div className="space-y-4">
            <div className="space-y-2">
              <h3 className="text-lg font-semibold tracking-tight">
                {t('settings.telegram.general.title')}
              </h3>
              <p className="text-sm text-muted-foreground">{t('settings.telegram.general.description')}</p>
            </div>

            {/* Enable Telegram */}
            <FormField
              control={form.control}
              name="enable"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between space-y-0 gap-x-2 p-3 sm:p-4 rounded-lg border bg-card hover:bg-accent/50 transition-colors">
                  <div className="space-y-0.5">
                    <FormLabel className="text-sm font-medium flex items-center gap-2 cursor-pointer">
                      <Send className="h-4 w-4" />
                      {t('settings.telegram.general.enable')}
                    </FormLabel>
                    <FormDescription className="text-sm text-muted-foreground">
                      {t('settings.telegram.general.enableDescription')}
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
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
                    <FormLabel className="text-sm font-medium flex items-center gap-2">
                      <Settings className="h-4 w-4" />
                      {t('settings.telegram.general.method')}
                    </FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder={t('settings.telegram.general.methodPlaceholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="webhook">
                          <div className="flex items-center gap-2">
                            <Webhook className="h-4 w-4" />
                            {t('settings.telegram.general.webhook')}
                          </div>
                        </SelectItem>
                        <SelectItem value="long-polling">
                          <div className="flex items-center gap-2">
                            <Send className="h-4 w-4" />
                            {t('settings.telegram.general.longPolling')}
                          </div>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription className="text-sm text-muted-foreground">
                      {t('settings.telegram.general.methodDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {/* Configuration Fields - Only show when Telegram is enabled */}
            {enableTelegram && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="token"
                  render={({ field }) => (
                    <FormItem className="space-y-2">
                      <FormLabel className="text-sm font-medium flex items-center gap-2">
                        <Bot className="h-4 w-4" />
                        {t('settings.telegram.general.token')}
                      </FormLabel>
                      <FormControl>
                        <PasswordInput
                          placeholder={t('settings.telegram.general.tokenPlaceholder')}
                          {...field}
                          className="font-mono"
                        />
                      </FormControl>
                      <FormDescription className="text-sm text-muted-foreground">
                        {t('settings.telegram.general.tokenDescription')}
                      </FormDescription>
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
                        <FormLabel className="text-sm font-medium flex items-center gap-2">
                          <Webhook className="h-4 w-4" />
                          {t('settings.telegram.general.webhookUrl')}
                        </FormLabel>
                        <FormControl>
                          <Input
                            type="url"
                            placeholder={t('settings.telegram.general.webhookUrlPlaceholder')}
                            {...field}
                            className="font-mono"
                          />
                        </FormControl>
                        <FormDescription className="text-sm text-muted-foreground">
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
                        <FormLabel className="text-sm font-medium flex items-center gap-2">
                          <Shield className="h-4 w-4" />
                          {t('settings.telegram.general.webhookSecret')}
                        </FormLabel>
                        <FormControl>
                          <PasswordInput
                            placeholder={t('settings.telegram.general.webhookSecretPlaceholder')}
                            {...field}
                            className="font-mono"
                          />
                        </FormControl>
                        <FormDescription className="text-sm text-muted-foreground">
                          {t('settings.telegram.general.webhookSecretDescription')}
                        </FormDescription>
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
                      <FormLabel className="text-sm font-medium flex items-center gap-2">
                        <Globe className="h-4 w-4" />
                        {t('settings.telegram.general.proxyUrl')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          type="url"
                          placeholder={t('settings.telegram.general.proxyUrlPlaceholder')}
                          {...field}
                          className="font-mono"
                        />
                      </FormControl>
                      <FormDescription className="text-sm text-muted-foreground">
                        {t('settings.telegram.general.proxyUrlDescription')}
                      </FormDescription>
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
              <Separator className="my-4" />

              <div className="space-y-4">
                <div className="space-y-2">
                  <h3 className="text-lg font-semibold tracking-tight">
                    {t('settings.telegram.advanced.title')}
                  </h3>
                  <p className="text-sm text-muted-foreground">{t('settings.telegram.advanced.description')}</p>
                </div>

                {/* Mini App Login */}
                <FormField
                  control={form.control}
                  name="mini_app_login"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between space-y-0 p-3 sm:p-4 rounded-lg border bg-card hover:bg-accent/50 transition-colors">
                      <div className="space-y-0.5">
                        <FormLabel className="text-sm font-medium flex items-center gap-2 cursor-pointer">
                          <Smartphone className="h-4 w-4" />
                          {t('settings.telegram.advanced.miniAppLogin')}
                        </FormLabel>
                        <FormDescription className="text-sm text-muted-foreground">
                          {t('settings.telegram.advanced.miniAppLoginDescription')}
                        </FormDescription>
                      </div>
                      <FormControl>
                        <Switch
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
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
                        <FormLabel className="text-sm font-medium flex items-center gap-2">
                          <Smartphone className="h-4 w-4" />
                          {t('settings.telegram.advanced.miniAppUrl')}
                        </FormLabel>
                        <FormControl>
                          <Input
                            type="url"
                            placeholder={t('settings.telegram.advanced.miniAppUrlPlaceholder')}
                            {...field}
                            className="font-mono"
                          />
                        </FormControl>
                        <FormDescription className="text-sm text-muted-foreground">
                          {t('settings.telegram.advanced.miniAppUrlDescription')}
                        </FormDescription>
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
                    <FormItem className="flex items-center justify-between space-y-0 p-3 sm:p-4 rounded-lg border bg-card hover:bg-accent/50 transition-colors">
                      <div className="space-y-0.5">
                        <FormLabel className="text-sm font-medium flex items-center gap-2 cursor-pointer">
                          <Users className="h-4 w-4" />
                          {t('settings.telegram.advanced.forAdminsOnly')}
                        </FormLabel>
                        <FormDescription className="text-sm text-muted-foreground">
                          {t('settings.telegram.advanced.forAdminsOnlyDescription')}
                        </FormDescription>
                      </div>
                      <FormControl>
                        <Switch
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            </>
          )}
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-6 mt-6 border-t">
            <div className="flex-1"></div>
            <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:shrink-0">
              <Button 
                type="button" 
                variant="outline" 
                onClick={handleCancel}
                className="w-full sm:w-auto min-w-[100px]"
                disabled={isSaving}
              >
                {t('cancel')}
              </Button>
              <Button 
                type="submit" 
                disabled={isSaveDisabled}
                className="w-full sm:w-auto min-w-[100px]"
              >
                {isSaving ? (
                  <div className="flex items-center gap-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    {t('saving')}
                  </div>
                ) : (
                  t('save')
                )}
              </Button>
            </div>
          </div>
        </form>
      </Form>
    </div>
  )
}
