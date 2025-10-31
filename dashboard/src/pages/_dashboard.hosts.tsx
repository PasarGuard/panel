import MainSection, { HostFormValues } from '@/components/hosts/Hosts'
import PageHeader from '@/components/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { BaseHost, createHost, CreateHost, getHosts, modifyHost, MultiplexProtocol, ProxyHostALPN, ProxyHostFingerprint, Xudp } from '@/service/api'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

export default function HostsPage() {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingHost, setEditingHost] = useState<BaseHost | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['getGetHostsQueryKey'],
    queryFn: () => getHosts(),
  })
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const handleDialogOpen = (open: boolean) => {
    setIsDialogOpen(open)
    if (!open) {
      setEditingHost(null)
    }
  }

  const handleCreateClick = () => {
    setEditingHost(null)
    setIsDialogOpen(true)
  }

  const onAddHost = (open: boolean) => {
    setIsDialogOpen(open)
  }

  const handleSubmit = async (formData: HostFormValues) => {
    try {
      // Check if all protocols are set to none
      const allProtocolsNone =
        formData.mux_settings &&
        (!formData.mux_settings.sing_box?.protocol || formData.mux_settings.sing_box.protocol === 'none') &&
        (!formData.mux_settings.clash?.protocol || formData.mux_settings.clash.protocol === 'none') &&
        !formData.mux_settings.xray?.concurrency

      // If creating a new host, set priority to max+1
      let priority = formData.priority
      if (!editingHost?.id && data && data.length > 0) {
        const priorities = data.map(h => h.priority ?? 0)
        const maxPriority = Math.max(...priorities)
        priority = maxPriority + 1
      }

      // Convert HostFormValues to CreateHost type
      const hostData: CreateHost = {
        ...formData,
        priority,
        alpn: formData.alpn as ProxyHostALPN[] | undefined,
        fingerprint: formData.fingerprint as ProxyHostFingerprint | undefined,
        ech_config_list: formData.ech_config_list || undefined,
        transport_settings: formData.transport_settings
          ? {
              ...formData.transport_settings,
              xhttp_settings: formData.transport_settings.xhttp_settings
                ? {
                    ...formData.transport_settings.xhttp_settings,
                    xmux: formData.transport_settings.xhttp_settings.xmux
                      ? {
                          ...formData.transport_settings.xhttp_settings.xmux,
                          h_keep_alive_period: formData.transport_settings.xhttp_settings.xmux.h_keep_alive_period || undefined,
                        }
                      : undefined,
                  }
                : undefined,
            }
          : undefined,
        mux_settings: allProtocolsNone
          ? undefined
          : formData.mux_settings
            ? {
                ...formData.mux_settings,
                sing_box: formData.mux_settings.sing_box
                  ? {
                      enable: formData.mux_settings.sing_box.enable || false,
                      protocol: formData.mux_settings.sing_box.protocol === 'none' ? undefined : (formData.mux_settings.sing_box.protocol as MultiplexProtocol),
                      max_connections: formData.mux_settings.sing_box.max_connections || undefined,
                      max_streams: formData.mux_settings.sing_box.max_streams || undefined,
                      min_streams: formData.mux_settings.sing_box.min_streams || undefined,
                      padding: formData.mux_settings.sing_box.padding || undefined,
                      brutal: formData.mux_settings.sing_box.brutal || undefined,
                    }
                  : undefined,
                clash: formData.mux_settings.clash
                  ? {
                      enable: formData.mux_settings.clash.enable || false,
                      protocol: formData.mux_settings.clash.protocol === 'none' ? undefined : (formData.mux_settings.clash.protocol as MultiplexProtocol),
                      max_connections: formData.mux_settings.clash.max_connections || undefined,
                      max_streams: formData.mux_settings.clash.max_streams || undefined,
                      min_streams: formData.mux_settings.clash.min_streams || undefined,
                      padding: formData.mux_settings.clash.padding || undefined,
                      brutal: formData.mux_settings.clash.brutal || undefined,
                      statistic: formData.mux_settings.clash.statistic || undefined,
                      only_tcp: formData.mux_settings.clash.only_tcp || undefined,
                    }
                  : undefined,
                xray: formData.mux_settings.xray
                  ? {
                      enabled: formData.mux_settings.xray.enabled || false,
                      concurrency: formData.mux_settings.xray.concurrency || undefined,
                      xudp_concurrency: formData.mux_settings.xray.xudp_concurrency || undefined,
                      xudp_proxy_udp_443: formData.mux_settings.xray.xudp_proxy_443 === 'none' ? undefined : (formData.mux_settings.xray.xudp_proxy_443 as Xudp),
                    }
                  : undefined,
              }
            : undefined,
        fragment_settings: (() => {
          const xraySettings = formData.fragment_settings?.xray
            ? {
                packets: formData.fragment_settings.xray.packets || '',
                length: formData.fragment_settings.xray.length || '',
                interval: formData.fragment_settings.xray.interval || '',
              }
            : undefined

          const singboxSettings = formData.fragment_settings?.sing_box?.fragment
            ? {
                fragment: formData.fragment_settings.sing_box.fragment,
                fragment_fallback_delay: formData.fragment_settings.sing_box.fragment_fallback_delay || undefined,
                record_fragment: formData.fragment_settings.sing_box.record_fragment || undefined,
              }
            : undefined

          if (xraySettings || singboxSettings) {
            return {
              xray: xraySettings,
              sing_box: singboxSettings,
            }
          }
          return undefined
        })(),
        noise_settings: formData.noise_settings?.xray
          ? {
              xray: formData.noise_settings.xray.map(noise => ({
                type: noise.type,
                packet: noise.packet,
                delay: noise.delay,
                apply_to: noise.apply_to,
              })),
            }
          : undefined,
        ss2022_relay_inbound_tags:
          formData.ss2022_relay_inbound_tags && formData.ss2022_relay_inbound_tags.length > 0
            ? formData.ss2022_relay_inbound_tags
            : undefined,
      }

      if (editingHost?.id) {
        // This is an edit operation
        await modifyHost(editingHost.id, hostData)
        return { status: 200 }
      } else {
        // This is a new host
        await createHost(hostData)
        return { status: 200 }
      }
    } catch (error: any) {
      console.error('Error submitting host:', error)
      console.error('Error response:', error?.response)
      console.error('Error data:', error?.response?._data)

      let errorMessage = ''
      let errorField = ''

      if (error?.response?._data) {
        const apiError = error.response._data

        if (typeof apiError === 'string') {
          errorMessage = apiError
        } else if (apiError?.detail) {
          if (Array.isArray(apiError.detail)) {
            // Get first error message from array
            const firstError = apiError.detail[0]
            errorField = firstError?.loc?.[1] || ''
            errorMessage = firstError?.msg || 'Validation error'
          } else if (typeof apiError.detail === 'string') {
            errorMessage = apiError.detail
          } else if (typeof apiError.detail === 'object') {
            // Get first error message from object
            const firstError = Object.entries(apiError.detail)[0]
            errorField = firstError[0]
            errorMessage = typeof firstError[1] === 'string' ? firstError[1] : t('validation.invalid', { field: firstError[0] })
          } else if (typeof apiError.detail === 'string' && !Array.isArray(apiError.detail)) {
            toast.error(apiError.detail)
          } else {
            errorMessage = 'Validation error'
          }
        } else if (apiError?.message) {
          errorMessage = apiError.message
        } else {
          errorMessage = t('hosts.genericError', { defaultValue: 'An unexpected error occurred' })
        }
      } else {
        errorMessage = error?.message || t('hosts.genericError', { defaultValue: 'An error occurred' })
      }

      // Show error message in toast with field name if available
      const toastMessage = errorField ? `${errorField}: ${errorMessage}` : errorMessage
      toast.error(toastMessage)
      return { status: 500 }
    } finally {
      // Refresh the hosts data
      queryClient.invalidateQueries({
        queryKey: ['/api/hosts'],
      })
    }
  }

  return (
    <div className="flex w-full flex-col items-start gap-2 pb-8">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <PageHeader title="hosts" description="manageHosts" buttonIcon={Plus} buttonText="hostsDialog.addHost" onButtonClick={handleCreateClick} />
        <Separator />
      </div>

      <div className="w-full px-4 pt-6">
        {isLoading ? (
          <div className="grid w-full grid-cols-1 gap-4 py-6 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Card key={index} className="animate-pulse">
                <CardContent className="p-4">
                  <div className="flex flex-col gap-2">
                    <div className="h-5 w-2/3 rounded-md bg-muted"></div>
                    <div className="h-3 w-full rounded-md bg-muted"></div>
                    <div className="h-3 w-4/5 rounded-md bg-muted"></div>
                    <div className="mt-2 flex justify-between">
                      <div className="h-6 w-1/4 rounded-md bg-muted"></div>
                      <div className="h-6 w-1/4 rounded-md bg-muted"></div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <MainSection
            data={data || []}
            isDialogOpen={isDialogOpen}
            onDialogOpenChange={handleDialogOpen}
            onAddHost={onAddHost}
            onSubmit={handleSubmit}
            editingHost={editingHost}
            setEditingHost={setEditingHost}
          />
        )}
      </div>
    </div>
  )
}
