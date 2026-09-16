import { useTranslation } from 'react-i18next'
import type { UseFormReturn } from 'react-hook-form'
import { Bot, Eye, Globe } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import type { McpSettingsFormInput } from '../forms/mcp-settings-form'

interface McpServerCardProps {
  form: UseFormReturn<McpSettingsFormInput>
  disabled?: boolean
  forApiKey?: boolean
  toolsEnabled?: number
  toolsTotal?: number
}

export function McpServerCard({ form, disabled = false, forApiKey = false, toolsEnabled = 0, toolsTotal = 0 }: McpServerCardProps) {
  const { t } = useTranslation()
  const enabled = form.watch('enable')

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-base font-semibold sm:text-lg">{t('mcp.server.title')}</h3>
          <p className="text-muted-foreground text-xs sm:text-sm">{t('mcp.server.description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={enabled ? 'green' : 'secondary'}>{enabled ? t('mcp.server.enabled') : t('mcp.server.disabled')}</Badge>
          <Badge variant="outline">{t('mcp.server.toolsEnabled', { enabled: toolsEnabled, total: toolsTotal })}</Badge>
        </div>
      </div>

      <FormField
        control={form.control}
        name="enable"
        render={({ field }) => (
          <FormItem className="bg-card hover:bg-accent/50 flex flex-row items-center justify-between space-y-0 gap-x-3 rounded-lg border p-3 transition-colors sm:p-4">
            <div className="space-y-0.5">
              <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                <Bot className="h-4 w-4" />
                {t('mcp.server.enable')}
              </FormLabel>
              <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t(forApiKey ? 'mcp.server.enableKeyDescription' : 'mcp.server.enableDescription')}</FormDescription>
            </div>
            <FormControl>
              <Switch checked={!!field.value} onCheckedChange={field.onChange} disabled={disabled} />
            </FormControl>
          </FormItem>
        )}
      />

      {!forApiKey && (
        <FormField
          control={form.control}
          name="oauth"
          render={({ field }) => (
            <FormItem className="bg-card hover:bg-accent/50 flex flex-row items-center justify-between space-y-0 gap-x-3 rounded-lg border p-3 transition-colors sm:p-4">
              <div className="space-y-0.5">
                <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                  <Globe className="h-4 w-4" />
                  {t('mcp.server.oauth')}
                </FormLabel>
                <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t('mcp.server.oauthDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} disabled={disabled} />
              </FormControl>
            </FormItem>
          )}
        />
      )}

      <FormField
        control={form.control}
        name="read_only"
        render={({ field }) => (
          <FormItem className="bg-card hover:bg-accent/50 flex flex-row items-center justify-between space-y-0 gap-x-3 rounded-lg border p-3 transition-colors sm:p-4">
            <div className="space-y-0.5">
              <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                <Eye className="h-4 w-4" />
                {t('mcp.server.readOnly')}
              </FormLabel>
              <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t('mcp.server.readOnlyDescription')}</FormDescription>
            </div>
            <FormControl>
              <Switch checked={!!field.value} onCheckedChange={field.onChange} disabled={disabled} />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}
