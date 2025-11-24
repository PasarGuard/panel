import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { DEFAULT_SHADOWSOCKS_METHOD } from '@/constants/Proxies'
import { ShadowsocksMethods, XTLSFlows, useReconnectAllNode } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, RefreshCcw, XIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { useSettingsContext } from './_dashboard.settings'

// general settings validation schema
const generalSettingsSchema = z.object({
  default_flow: z.string().default(''),
  default_method: z.string().default(''),
})

type GeneralSettingsForm = z.infer<typeof generalSettingsSchema>

export default function General() {
  const { t } = useTranslation()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()
  const [isReconnectAllDialogOpen, setIsReconnectAllDialogOpen] = useState(false)
  const reconnectAllNodeMutation = useReconnectAllNode()

  const form = useForm<GeneralSettingsForm>({
    resolver: zodResolver(generalSettingsSchema),
    defaultValues: {
      default_flow: '',
      default_method: '',
    },
  })

  useEffect(() => {
    form.reset({
      default_flow: settings?.general?.default_flow || '',
      default_method: settings?.general?.default_method || DEFAULT_SHADOWSOCKS_METHOD,
    })
  }, [settings])

  const onSubmit = async (data: GeneralSettingsForm) => {
    try {
      // Filter out empty values and prepare the payload
      const filteredData: any = {
        general: {
          ...data,
          default_flow: data.default_flow || undefined,
          default_method: data.default_method || DEFAULT_SHADOWSOCKS_METHOD,
        },
      }

      await updateSettings(filteredData)
    } catch (error) {
      // Error handling is done in the parent context
    }
  }

  const handleCancel = () => {
    if (settings?.general) {
      form.reset({
        default_flow: '',
        default_method: DEFAULT_SHADOWSOCKS_METHOD,
      })
      toast.success(t('settings.general.cancelSuccess'))
    }
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

      setIsReconnectAllDialogOpen(false)
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('nodes.reconnectAllFailed', {
          defaultValue: 'Failed to reconnect all nodes',
        }),
      })
    }
  }

  // Check if save button should be disabled
  const isSaveDisabled = isSaving

  // TODO: skeleton needs to be improved
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

  const clearField = (field: keyof GeneralSettingsForm) => {
    return (e: React.MouseEvent<HTMLButtonElement>) => {
      e.preventDefault()
      e.stopPropagation()
      form.setValue(field, '')
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-200px)] w-full flex-col">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-1 flex-col p-4 sm:py-6 lg:py-8">
          <div className="mb-4 sm:mb-6 lg:mb-8">
            {/* General Settings */}
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <FormField
                control={form.control}
                name="default_flow"
                render={({ field }) => (
                  <FormItem className="relative space-y-2">
                    <FormLabel className="flex items-center gap-2 text-sm font-medium">{t('settings.general.defaultFlow.title')}</FormLabel>
                    <FormControl>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        {field.value && (
                          <Button size="icon" variant="ghost" className="absolute right-8 top-6" onClick={clearField('default_flow')}>
                            <XIcon />
                          </Button>
                        )}
                        <SelectContent>
                          {Object.values(XTLSFlows)
                            .filter(Boolean)
                            .map(flow => {
                              return (
                                <SelectItem value={flow} key={flow}>
                                  {flow}
                                </SelectItem>
                              )
                            })}
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormDescription className="text-sm text-muted-foreground">{t('settings.general.defaultFlow.description')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="default_method"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-sm font-medium">{t('settings.general.defaultMethod.title')}</FormLabel>
                    <FormControl>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.values(ShadowsocksMethods)
                            .filter(Boolean)
                            .map(flow => {
                              return (
                                <SelectItem value={flow} key={flow}>
                                  {flow}
                                </SelectItem>
                              )
                            })}
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormDescription className="text-sm text-muted-foreground">{t('settings.general.defaultMethod.description')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </div>

          <Separator className="my-4" />

          {/* Reconnect All Nodes Section */}
          <div className="flex flex-col md:flex-row gap-4 py-3 md:items-start md:justify-between">
            <div className="space-y-1">
              <h3 className="text-sm font-medium">{t('nodes.title', { defaultValue: 'Reconnect All Nodes' })}</h3>
              <p className="text-xs text-muted-foreground">{t('nodes.reconnectinfo', { defaultValue: 'Refresh all nodes connections' })}</p>
            </div>
            <Button variant="destructive" size="sm" type="button" onClick={() => setIsReconnectAllDialogOpen(true)} disabled={reconnectAllNodeMutation.isPending} className="shrink-0 gap-2">
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
                <AlertDialogTitle>{t('nodes.reconnectAll', { defaultValue: 'Reconnect All Nodes' })}</AlertDialogTitle>
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

          {/* Action Buttons */}
          <div className="mt-auto flex flex-col gap-3 pt-6 sm:flex-row sm:gap-4">
            <div className="flex-1"></div>
            <div className="flex flex-col gap-3 sm:shrink-0 sm:flex-row sm:gap-4">
              <Button type="button" variant="outline" onClick={handleCancel} className="w-full min-w-[100px] sm:w-auto" disabled={isSaving}>
                {t('cancel')}
              </Button>
              <Button type="submit" disabled={isSaveDisabled} isLoading={isSaving} loadingText={t('saving')} className="w-full min-w-[100px] sm:w-auto">
                {t('save')}
              </Button>
            </div>
          </div>
        </form>
      </Form>
    </div>
  )
}
