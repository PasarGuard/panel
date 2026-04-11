import type { SubscriptionFormData } from '@/components/subscriptions/subscription-settings-schema'
import { WireguardIcon, XrayIcon, SingboxIcon, MihomoIcon } from '@/components/icons/format-icons'
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Cat, Code, GlobeLock, ListTree } from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SubscriptionManualFormatsSectionProps {
  form: UseFormReturn<SubscriptionFormData>
}

export function SubscriptionManualFormatsSection({ form }: SubscriptionManualFormatsSectionProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="flex items-center gap-2 text-base font-semibold sm:text-lg">{t('settings.subscriptions.formats.title')}</h3>
        <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.formats.description')}</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 lg:gap-6">
        <FormField
          control={form.control}
          name="manual_sub_request.links"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <ListTree className="h-4 w-4" />
                  {t('settings.subscriptions.formats.links')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.linksDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.links_base64"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <Code className="h-4 w-4" />
                  {t('settings.subscriptions.formats.linksBase64')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.linksBase64Description')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.xray"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <XrayIcon className="h-4 w-4" />
                  {t('settings.subscriptions.formats.xray')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.xrayDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.wireguard"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <WireguardIcon className="h-4 w-4" />
                  {t('settings.subscriptions.formats.wireguard')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.wireguardDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.sing_box"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <SingboxIcon className="h-4 w-4" />
                  {t('settings.subscriptions.formats.singBox')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.singBoxDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.clash"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <Cat className="h-4 w-4" />
                  {t('settings.subscriptions.formats.clash')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.clashDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.clash_meta"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <MihomoIcon className="h-4 w-4" />
                  {t('settings.subscriptions.formats.clashMeta')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.clashMetaDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="manual_sub_request.outline"
          render={({ field }) => (
            <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <GlobeLock className="h-4 w-4" />
                  {t('settings.subscriptions.formats.outline')}
                </FormLabel>
                <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.outlineDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
      </div>
    </div>
  )
}
