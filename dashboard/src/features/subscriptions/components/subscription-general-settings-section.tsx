import type { SubscriptionFormData } from '@/features/subscriptions/components/subscription-settings-schema'
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { VariablesPopover } from '@/components/ui/variables-popover'
import {
  Clock,
  ExternalLink,
  FileCode2,
  Globe,
  HelpCircle,
  Link,
  Megaphone,
  Shuffle,
  User,
} from 'lucide-react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SubscriptionGeneralSettingsSectionProps {
  form: UseFormReturn<SubscriptionFormData>
}

export function SubscriptionGeneralSettingsSection({ form }: SubscriptionGeneralSettingsSectionProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <h3 className="text-base font-semibold sm:text-lg">{t('settings.subscriptions.general.title')}</h3>
        <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.description')}</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:gap-4 lg:grid-cols-2">
        <FormField
          control={form.control}
          name="url_prefix"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                <Link className="h-4 w-4 shrink-0" />
                {t('settings.subscriptions.general.urlPrefix')}
              </FormLabel>
              <FormControl>
                <Input placeholder="https://example.com" {...field} className="font-mono text-xs sm:text-sm" />
              </FormControl>
              <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.urlPrefixDescription')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="update_interval"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                <Clock className="h-4 w-4" />
                {t('settings.subscriptions.general.updateInterval')}
              </FormLabel>
              <FormControl>
                <div className="relative">
                  <Input type="number" min="1" max="168" {...field} onChange={e => field.onChange(parseInt(e.target.value) || 24)} className="pr-16 text-xs sm:text-sm" />
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
                    <span className="text-xs text-muted-foreground sm:text-sm">hours</span>
                  </div>
                </div>
              </FormControl>
              <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.updateIntervalDescription')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="support_url"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                <HelpCircle className="h-4 w-4" />
                {t('settings.subscriptions.general.supportUrl')}
              </FormLabel>
              <FormControl>
                <Input type="url" placeholder={t('settings.subscriptions.general.supportUrlPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
              </FormControl>
              <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.supportUrlDescription')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="profile_title"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <div className="flex items-center gap-1.5">
                <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                  <User className="h-4 w-4" />
                  {t('settings.subscriptions.general.profileTitle')}
                </FormLabel>
                <VariablesPopover />
              </div>
              <FormControl>
                <Input placeholder={t('settings.subscriptions.general.profileTitlePlaceholder')} {...field} className="text-xs sm:text-sm" />
              </FormControl>
              <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.profileTitleDescription')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="announce"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <div className="flex items-center gap-1.5">
                <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                  <Megaphone className="h-4 w-4" />
                  {t('settings.subscriptions.general.announce')}
                </FormLabel>
                <VariablesPopover />
              </div>
              <FormControl>
                <Textarea maxLength={128} placeholder={t('settings.subscriptions.general.announcePlaceholder')} rows={3} className="resize-none text-xs sm:text-sm" {...field} />
              </FormControl>
              <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.announceDescription')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="announce_url"
          render={({ field }) => (
            <FormItem className="space-y-2">
              <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                <ExternalLink className="h-4 w-4" />
                {t('settings.subscriptions.general.announceUrl')}
              </FormLabel>
              <FormControl>
                <Input type="url" placeholder={t('settings.subscriptions.general.announceUrlPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
              </FormControl>
              <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.announceUrlDescription')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="allow_browser_config"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4 lg:col-span-2">
              <div className="flex-1 space-y-0.5 pr-4">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <Globe className="h-4 w-4 shrink-0" />
                  <span className="break-words">{t('settings.subscriptions.general.allowBrowserConfig')}</span>
                </FormLabel>
                <FormDescription className="text-xs leading-relaxed text-muted-foreground sm:leading-normal">
                  {t('settings.subscriptions.general.allowBrowserConfigDescription')}
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
          name="disable_sub_template"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4 lg:col-span-2">
              <div className="flex-1 space-y-0.5 pr-4">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <FileCode2 className="h-4 w-4 shrink-0" />
                  <span className="break-words">{t('settings.subscriptions.general.disableSubTemplate')}</span>
                </FormLabel>
                <FormDescription className="text-xs leading-relaxed text-muted-foreground sm:leading-normal">
                  {t('settings.subscriptions.general.disableSubTemplateDescription')}
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
          name="randomize_order"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4 lg:col-span-2">
              <div className="flex-1 space-y-0.5 pr-4">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <Shuffle className="h-4 w-4 shrink-0" />
                  <span className="break-words">{t('settings.subscriptions.general.randomizeOrder')}</span>
                </FormLabel>
                <FormDescription className="text-xs leading-relaxed text-muted-foreground sm:leading-normal">
                  {t('settings.subscriptions.general.randomizeOrderDescription')}
                </FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} className="shrink-0" />
              </FormControl>
            </FormItem>
          )}
        />
      </div>
    </div>
  )
}
