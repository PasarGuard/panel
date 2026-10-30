import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { SubscriptionFormActions } from '@/features/subscriptions/components/subscription-form-actions'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { DEFAULT_SHADOWSOCKS_METHOD } from '@/constants/Proxies'
import { type General as GeneralSettingsResponse, OnHoldTimeoutAction, ShadowsocksMethods, useGetGeneralSettings, useReconnectAllNode } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, RefreshCcw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { type FieldPath, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { useSettingsContext } from './_dashboard.settings'

// general settings validation schema
const generalSettingsSchema = z.object({
  default_method: z.string().default(''),
  on_hold_timeout_action: z.nativeEnum(OnHoldTimeoutAction).default(OnHoldTimeoutAction.activate),
  usage: z.object({
    record_node_usage: z.boolean(),
    record_node_stats: z.boolean(),
    reset_usage_clean_chart_data: z.boolean(),
  }),
  node_health: z.object({
    fail_threshold: z.number().int().min(1),
    recover_threshold: z.number().int().min(1),
    probe_timeout: z.number().int().min(1),
    max_backoff: z.number().int().min(0),
  }),
  stop_nodes_on_shutdown: z.boolean(),
})

type GeneralSettingsFormInput = z.input<typeof generalSettingsSchema>

const DEFAULT_GENERAL_FORM_VALUES: GeneralSettingsFormInput = {
  default_method: '',
  on_hold_timeout_action: OnHoldTimeoutAction.activate,
  usage: {
    record_node_usage: true,
    record_node_stats: false,
    reset_usage_clean_chart_data: false,
  },
  node_health: {
    fail_threshold: 3,
    recover_threshold: 2,
    probe_timeout: 5,
    max_backoff: 60,
  },
  stop_nodes_on_shutdown: true,
}

function toGeneralFormValues(settings?: GeneralSettingsResponse): GeneralSettingsFormInput {
  if (!settings) return DEFAULT_GENERAL_FORM_VALUES
  return {
    default_method: settings.default_method || DEFAULT_SHADOWSOCKS_METHOD,
    on_hold_timeout_action: settings.on_hold_timeout_action || OnHoldTimeoutAction.activate,
    usage: { ...DEFAULT_GENERAL_FORM_VALUES.usage, ...settings.usage },
    node_health: { ...DEFAULT_GENERAL_FORM_VALUES.node_health, ...settings.node_health },
    stop_nodes_on_shutdown: settings.stop_nodes_on_shutdown ?? DEFAULT_GENERAL_FORM_VALUES.stop_nodes_on_shutdown,
  }
}

type SwitchFieldName = 'usage.record_node_usage' | 'usage.record_node_stats' | 'usage.reset_usage_clean_chart_data' | 'stop_nodes_on_shutdown'
type NumberFieldName = Extract<FieldPath<GeneralSettingsFormInput>, `node_health.${string}`>

export default function General() {
  const { t } = useTranslation()
  const { isLoading, error, updateSettings, isSaving } = useSettingsContext()
  const { data: generalSettings, isLoading: isGeneralLoading, error: generalError } = useGetGeneralSettings()
  const [isReconnectAllDialogOpen, setIsReconnectAllDialogOpen] = useState(false)
  const reconnectAllNodeMutation = useReconnectAllNode()

  const generalFormValues = useMemo<GeneralSettingsFormInput>(() => toGeneralFormValues(generalSettings), [generalSettings])

  const form = useForm<GeneralSettingsFormInput>({
    resolver: zodResolver(generalSettingsSchema),
    values: generalFormValues,
  })

  const onSubmit = async (data: GeneralSettingsFormInput) => {
    try {
      // Filter out empty values and prepare the payload
      const filteredData: any = {
        general: {
          default_method: data.default_method || DEFAULT_SHADOWSOCKS_METHOD,
          on_hold_timeout_action: data.on_hold_timeout_action || OnHoldTimeoutAction.activate,
          usage: data.usage,
          node_health: data.node_health,
          stop_nodes_on_shutdown: data.stop_nodes_on_shutdown,
        },
      }

      await updateSettings(filteredData)
    } catch (error) {
      // Error handling is done in the parent context
    }
  }

  const handleCancel = () => {
    if (!generalSettings) return
    form.reset(toGeneralFormValues(generalSettings))
    toast.success(t('settings.general.cancelSuccess'))
  }

  const handleReconnectAll = async () => {
    try {
      await reconnectAllNodeMutation.mutateAsync({
        params: {},
      })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('nodes.reconnectAllSuccess', {
          defaultValue: 'All nodes have been reconnected successfully',
        }),
      })

      // Invalidate nodes queries to refresh data
      queryClient.invalidateQueries({
        queryKey: ['/api/nodes'],
      })
      queryClient.invalidateQueries({
        queryKey: ['/api/nodes/simple'],
      })

      setIsReconnectAllDialogOpen(false)
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('nodes.reconnectAllFailed', {
          defaultValue: 'Failed to reconnect all nodes',
        }),
      })
    }
  }

  const renderSwitchField = (name: SwitchFieldName, labelKey: string) => (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="bg-card hover:bg-accent/50 flex flex-row items-center justify-between gap-3 space-y-0 rounded-lg border p-3 transition-colors sm:p-4">
          <div className="space-y-0.5">
            <FormLabel className="cursor-pointer text-xs font-medium sm:text-sm">{t(`${labelKey}.title`)}</FormLabel>
            <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t(`${labelKey}.description`)}</FormDescription>
          </div>
          <FormControl>
            <Switch checked={field.value} onCheckedChange={field.onChange} />
          </FormControl>
        </FormItem>
      )}
    />
  )

  const renderNumberField = (name: NumberFieldName, labelKey: string, min: number) => (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="space-y-2">
          <FormLabel className="text-xs font-medium sm:text-sm">{t(`${labelKey}.title`)}</FormLabel>
          <FormControl>
            <Input
              type="number"
              step="1"
              min={min}
              {...field}
              value={field.value ?? ''}
              onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
              className="text-xs sm:text-sm"
            />
          </FormControl>
          <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t(`${labelKey}.description`)}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  )

  const loadError = error || generalError

  // TODO: skeleton needs to be improved
  if (isLoading || isGeneralLoading) {
    return (
      <div className="w-full p-4 sm:py-6 lg:py-8">
        <div className="space-y-6 sm:space-y-8 lg:space-y-10">
          {/* General Settings Skeleton */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-96" />
            </div>
            <Skeleton className="h-16" />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-10" />
                  <Skeleton className="h-3 w-64" />
                </div>
              ))}
            </div>
            <Skeleton className="h-16" />
          </div>

          {/* Action Buttons Skeleton */}
          <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:gap-4">
            <div className="flex-1"></div>
            <div className="flex flex-col gap-3 sm:shrink-0 sm:flex-row sm:gap-4">
              <Skeleton className="h-10 w-24" />
              <Skeleton className="h-10 w-20" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (loadError) {
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
          <div className="mb-4 sm:mb-6 lg:mb-8">
            {/* General Settings */}
            <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
              <FormField
                control={form.control}
                name="default_method"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">{t('settings.general.defaultMethod.title')}</FormLabel>
                    <FormControl>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="text-xs sm:text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.values(ShadowsocksMethods)
                            .filter(Boolean)
                            .map(flow => {
                              return (
                                <SelectItem value={flow} key={flow} className="text-xs sm:text-sm">
                                  {flow}
                                </SelectItem>
                              )
                            })}
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t('settings.general.defaultMethod.description')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="on_hold_timeout_action"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">{t('settings.general.onHoldTimeoutAction.title')}</FormLabel>
                    <FormControl>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger className="text-xs sm:text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={OnHoldTimeoutAction.activate} className="text-xs sm:text-sm">
                            {t('settings.general.onHoldTimeoutAction.activate')}
                          </SelectItem>
                          <SelectItem value={OnHoldTimeoutAction.disable} className="text-xs sm:text-sm">
                            {t('settings.general.onHoldTimeoutAction.disable')}
                          </SelectItem>
                          <SelectItem value={OnHoldTimeoutAction.delete} className="text-xs sm:text-sm">
                            {t('settings.general.onHoldTimeoutAction.delete')}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormDescription className="text-muted-foreground text-xs sm:text-sm">{t('settings.general.onHoldTimeoutAction.description')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </div>

          {/* Usage recording */}
          <div className="mb-4 space-y-3 sm:mb-6">
            <div className="space-y-1">
              <h3 className="text-base font-semibold sm:text-lg">{t('settings.general.usage.title')}</h3>
              <p className="text-muted-foreground text-xs sm:text-sm">{t('settings.general.usage.description')}</p>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
              {renderSwitchField('usage.record_node_usage', 'settings.general.usage.recordNodeUsage')}
              {renderSwitchField('usage.record_node_stats', 'settings.general.usage.recordNodeStats')}
              {renderSwitchField('usage.reset_usage_clean_chart_data', 'settings.general.usage.resetUsageCleanChartData')}
            </div>
          </div>

          {/* Node health checks */}
          <div className="mb-4 space-y-3 sm:mb-6">
            <div className="space-y-1">
              <h3 className="text-base font-semibold sm:text-lg">{t('settings.general.nodeHealth.title')}</h3>
              <p className="text-muted-foreground text-xs sm:text-sm">{t('settings.general.nodeHealth.description')}</p>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
              {renderNumberField('node_health.fail_threshold', 'settings.general.nodeHealth.failThreshold', 1)}
              {renderNumberField('node_health.recover_threshold', 'settings.general.nodeHealth.recoverThreshold', 1)}
              {renderNumberField('node_health.probe_timeout', 'settings.general.nodeHealth.probeTimeout', 1)}
              {renderNumberField('node_health.max_backoff', 'settings.general.nodeHealth.maxBackoff', 0)}
            </div>
            {renderSwitchField('stop_nodes_on_shutdown', 'settings.general.stopNodesOnShutdown')}
          </div>

          <Separator className="my-3" />

          {/* Reconnect All Nodes Section */}
          <div className="flex flex-col gap-3 py-3 sm:gap-4 md:flex-row md:items-start md:justify-between">
            <div className="space-y-1">
              <h3 className="text-base font-semibold sm:text-lg">{t('nodes.title', { defaultValue: 'Reconnect All Nodes' })}</h3>
              <p className="text-muted-foreground text-xs sm:text-sm">{t('nodes.reconnectinfo', { defaultValue: 'Refresh all nodes connections' })}</p>
            </div>
            <Button
              variant="destructive"
              size="sm"
              type="button"
              onClick={() => setIsReconnectAllDialogOpen(true)}
              disabled={reconnectAllNodeMutation.isPending}
              className="w-full shrink-0 gap-2 sm:w-auto"
            >
              {reconnectAllNodeMutation.isPending ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {t('nodes.reconnectingAll', { defaultValue: 'Reconnecting...' })}
                </>
              ) : (
                <>
                  <RefreshCcw className="h-3 w-3" />
                  {t('nodes.reconnectAll', { defaultValue: 'Reconnect All Nodes' })}
                </>
              )}
            </Button>
          </div>

          {/* Reconnect All Dialog */}
          <AlertDialog open={isReconnectAllDialogOpen} onOpenChange={setIsReconnectAllDialogOpen}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2">
                  <RefreshCcw className="h-5 w-5" />
                  {t('nodes.reconnectAll', { defaultValue: 'Reconnect All Nodes' })}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t('nodes.reconnectAllPrompt', {
                    defaultValue: 'Are you sure you want to reconnect all nodes? This will temporarily disconnect all active connections and may take a few moments to complete.',
                  })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={reconnectAllNodeMutation.isPending}>{t('cancel', { defaultValue: 'Cancel' })}</AlertDialogCancel>
                <AlertDialogAction onClick={handleReconnectAll} disabled={reconnectAllNodeMutation.isPending} className="gap-2">
                  {reconnectAllNodeMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t('nodes.reconnectingAll', { defaultValue: 'Reconnecting...' })}
                    </>
                  ) : (
                    t('nodes.reconnectAll', { defaultValue: 'Reconnect All Nodes' })
                  )}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <SubscriptionFormActions onCancel={handleCancel} isSaving={isSaving} className="mt-auto sm:mt-auto" />
        </form>
      </Form>
    </div>
  )
}
