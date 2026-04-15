import { Card, CardContent } from '@/components/ui/card'
import { type HostAdvanceSearchFormValues, hostAdvanceSearchFormSchema } from '@/components/forms/host-advance-search-form'
import { HostFormSchema, hostFormDefaultValues, type HostFormValues } from '@/components/forms/host-form'
import HostAdvanceSearchModal from '@/components/dialogs/host-advance-search-modal'
import { type HostListFilters, HostFilters } from '@/components/hosts/host-filters'
import { ListGenerator } from '@/components/common/list-generator'
import { useHostsListColumns } from '@/components/hosts/use-hosts-list-columns'
import { usePersistedViewMode } from '@/hooks/use-persisted-view-mode'
import { BaseHost, CreateHost, createHost, modifyHosts, useBulkDeleteHosts, useBulkDisableHosts, useBulkEnableHosts, useGetInboundDetails } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { closestCenter, DndContext, DragEndEvent, KeyboardSensor, PointerSensor, UniqueIdentifier, useSensor, useSensors } from '@dnd-kit/core'
import { arrayMove, rectSortingStrategy, SortableContext, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { Resolver, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Power, PowerOff, Trash2 } from 'lucide-react'
import HostModal from '../dialogs/host-modal'
import SortableHost from './sortable-host'
import { BulkActionItem, BulkActionsBar } from '@/components/users/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/components/users/bulk-action-alert-dialog'

export interface HostsListProps {
  data?: BaseHost[]
  isDialogOpen: boolean
  onDialogOpenChange: (open: boolean) => void
  onAddHost: (open: boolean) => void
  onSubmit: (data: HostFormValues) => Promise<{ status: number }>
  editingHost: BaseHost | null
  setEditingHost: (host: BaseHost | null) => void
  onRefresh?: () => Promise<unknown>
  isRefreshing?: boolean
}

type BulkHostActionType = 'delete' | 'disable' | 'enable'

interface BulkActionDialogConfig {
  title: string
  description: string
  actionLabel: string
  onConfirm: () => Promise<void>
  isPending: boolean
  destructive?: boolean
}

export default function HostsList({ data, onAddHost, isDialogOpen, onSubmit, editingHost, setEditingHost, onRefresh, isRefreshing: isRefreshingProp }: HostsListProps) {
  const [hosts, setHosts] = useState<BaseHost[] | undefined>(data)
  const [isUpdatingPriorities, setIsUpdatingPriorities] = useState(false)
  const [filters, setFilters] = useState<HostListFilters>({})
  const [isAdvanceSearchOpen, setIsAdvanceSearchOpen] = useState(false)
  const [viewMode, setViewMode] = usePersistedViewMode('view-mode:hosts')
  const [isManualRefreshing, setIsManualRefreshing] = useState(false)
  const [selectedHostIds, setSelectedHostIds] = useState<number[]>([])
  const [bulkAction, setBulkAction] = useState<BulkHostActionType | null>(null)
  const { t } = useTranslation()
  const bulkDeleteHostsMutation = useBulkDeleteHosts()
  const bulkDisableHostsMutation = useBulkDisableHosts()
  const bulkEnableHostsMutation = useBulkEnableHosts()

  // Set up hosts data from props
  useEffect(() => {
    if (data !== undefined) {
      setHosts(data)
    }
  }, [data])

  const form = useForm<HostFormValues>({
    resolver: zodResolver(HostFormSchema) as Resolver<HostFormValues>,
    defaultValues: hostFormDefaultValues,
  })
  const advanceSearchForm = useForm<HostAdvanceSearchFormValues>({
    resolver: zodResolver(hostAdvanceSearchFormSchema),
    defaultValues: {
      status: filters.status || [],
      inbound_tags: filters.inbound_tags || [],
      security: filters.security,
      is_disabled: filters.is_disabled,
    },
  })
  const { data: inbounds = [], isLoading: isLoadingInbounds } = useGetInboundDetails()

  const refreshHostsData = () => {
    // Just invalidate the main query key used in the dashboard
    return queryClient.invalidateQueries({
      queryKey: ['getGetHostsQueryKey'],
      exact: true, // Only invalidate this exact query
      refetchType: 'active', // Only refetch if the query is currently being rendered
    })
  }

  const handleRefreshClick = async () => {
    if (onRefresh) {
      await onRefresh()
      return
    }
    setIsManualRefreshing(true)
    try {
      await refreshHostsData()
    } finally {
      setIsManualRefreshing(false)
    }
  }

  const isRefreshing = isRefreshingProp ?? isManualRefreshing

  const clearSelection = () => {
    setSelectedHostIds([])
  }

  const handleFilterChange = (newFilters: Partial<HostListFilters>) => {
    setFilters(prev => ({
      ...prev,
      ...newFilters,
    }))
  }

  const handleAdvanceSearchSubmit = (values: HostAdvanceSearchFormValues) => {
    setFilters(prev => ({
      ...prev,
      status: values.status && values.status.length > 0 ? values.status : undefined,
      inbound_tags: values.inbound_tags && values.inbound_tags.length > 0 ? values.inbound_tags : undefined,
      security: values.security || undefined,
      is_disabled: values.is_disabled ?? undefined,
    }))
    setIsAdvanceSearchOpen(false)
  }

  const handleClearAdvanceSearch = () => {
    advanceSearchForm.reset({
      status: [],
      inbound_tags: [],
      security: undefined,
      is_disabled: undefined,
    })
    setFilters(prev => ({
      ...prev,
      status: undefined,
      inbound_tags: undefined,
      security: undefined,
      is_disabled: undefined,
    }))
  }

  const handleAdvanceSearchOpen = (open: boolean) => {
    if (open) {
      advanceSearchForm.reset({
        status: filters.status || [],
        inbound_tags: filters.inbound_tags || [],
        security: filters.security,
        is_disabled: filters.is_disabled,
      })
    }
    setIsAdvanceSearchOpen(open)
  }

  const handleEdit = (host: BaseHost) => {
    const formData: HostFormValues = {
      remark: host.remark || '',
      address: Array.isArray(host.address) ? host.address : host.address ? [host.address] : [],
      port: host.port ? Number(host.port) : undefined,
      inbound_tag: host.inbound_tag || '',
      status: host.status || [],
      host: Array.isArray(host.host) ? host.host : host.host ? [host.host] : [],
      sni: Array.isArray(host.sni) ? host.sni : host.sni ? [host.sni] : [],
      path: host.path || '',
      http_headers: host.http_headers || {},
      security: host.security || 'inbound_default',
      alpn: Array.isArray(host.alpn) ? host.alpn : host.alpn ? [host.alpn] : [],
      fingerprint: host.fingerprint || '',
      allowinsecure: host.allowinsecure || false,
      random_user_agent: host.random_user_agent || false,
      use_sni_as_host: host.use_sni_as_host || false,
      vless_route: host.vless_route || '',
      priority: host.priority || 0,
      is_disabled: host.is_disabled || false,
      ech_config_list: host.ech_config_list || undefined,
      ech_query_strategy: host.ech_query_strategy || undefined,
      pinned_peer_cert_sha256: host.pinned_peer_cert_sha256 || undefined,
      verify_peer_cert_by_name: host.verify_peer_cert_by_name || [],
      subscription_templates: host.subscription_templates
        ? {
            xray: host.subscription_templates.xray ?? undefined,
          }
        : undefined,
      fragment_settings: host.fragment_settings
        ? {
            xray: host.fragment_settings.xray ?? undefined,
            sing_box: host.fragment_settings.sing_box ?? undefined,
          }
        : undefined,
      noise_settings: host.noise_settings
        ? {
            xray:
              host.noise_settings.xray?.map(noise => ({
                type: noise.type,
                packet: noise.packet,
                delay: noise.delay,
                apply_to: (noise.apply_to as 'ip' | 'ipv4' | 'ipv6') || 'ip',
                rand_range: noise.rand_range ?? undefined,
              })) ?? undefined,
          }
        : undefined,
      mux_settings: host.mux_settings
        ? {
            xray: host.mux_settings.xray
              ? {
                  enabled: host.mux_settings.xray.enabled ?? false,
                  concurrency: host.mux_settings.xray.concurrency ?? null,
                  xudp_concurrency: host.mux_settings.xray.xudpConcurrency ?? null,
                  xudp_proxy_443: host.mux_settings.xray.xudpProxyUDP443 ?? 'reject',
                }
              : undefined,
            sing_box: host.mux_settings.sing_box
              ? {
                  enable: host.mux_settings.sing_box.enable ?? false,
                  protocol: host.mux_settings.sing_box.protocol ?? 'smux',
                  max_connections: host.mux_settings.sing_box.max_connections ?? null,
                  max_streams: host.mux_settings.sing_box.max_streams ?? null,
                  min_streams: host.mux_settings.sing_box.min_streams ?? null,
                  padding: host.mux_settings.sing_box.padding ?? null,
                  brutal: host.mux_settings.sing_box.brutal ?? null,
                }
              : undefined,
            clash: host.mux_settings.clash
              ? {
                  enable: host.mux_settings.clash.enable ?? false,
                  protocol: host.mux_settings.clash.protocol ?? 'smux',
                  max_connections: host.mux_settings.clash.max_connections ?? null,
                  max_streams: host.mux_settings.clash.max_streams ?? null,
                  min_streams: host.mux_settings.clash.min_streams ?? null,
                  padding: host.mux_settings.clash.padding ?? null,
                  brutal: host.mux_settings.clash.brutal ?? null,
                  statistic: host.mux_settings.clash.statistic ?? null,
                  only_tcp: host.mux_settings.clash.only_tcp ?? null,
                }
              : undefined,
          }
        : undefined,
      transport_settings: host.transport_settings
        ? {
            xhttp_settings: host.transport_settings.xhttp_settings
              ? {
                  mode: host.transport_settings.xhttp_settings.mode ?? undefined,
                  no_grpc_header: host.transport_settings.xhttp_settings.no_grpc_header === null ? undefined : !!host.transport_settings.xhttp_settings.no_grpc_header,
                  x_padding_bytes: host.transport_settings.xhttp_settings.x_padding_bytes ?? undefined,
                  x_padding_obfs_mode: host.transport_settings.xhttp_settings.x_padding_obfs_mode === null ? undefined : !!host.transport_settings.xhttp_settings.x_padding_obfs_mode,
                  x_padding_key: host.transport_settings.xhttp_settings.x_padding_key ?? undefined,
                  x_padding_header: host.transport_settings.xhttp_settings.x_padding_header ?? undefined,
                  x_padding_placement: host.transport_settings.xhttp_settings.x_padding_placement ?? undefined,
                  x_padding_method: host.transport_settings.xhttp_settings.x_padding_method ?? undefined,
                  uplink_http_method: host.transport_settings.xhttp_settings.uplink_http_method ?? undefined,
                  session_placement: host.transport_settings.xhttp_settings.session_placement ?? undefined,
                  session_key: host.transport_settings.xhttp_settings.session_key ?? undefined,
                  seq_placement: host.transport_settings.xhttp_settings.seq_placement ?? undefined,
                  seq_key: host.transport_settings.xhttp_settings.seq_key ?? undefined,
                  uplink_data_placement: host.transport_settings.xhttp_settings.uplink_data_placement ?? undefined,
                  uplink_data_key: host.transport_settings.xhttp_settings.uplink_data_key ?? undefined,
                  uplink_chunk_size: host.transport_settings.xhttp_settings.uplink_chunk_size ?? undefined,
                  sc_max_each_post_bytes: host.transport_settings.xhttp_settings.sc_max_each_post_bytes ?? undefined,
                  sc_min_posts_interval_ms: host.transport_settings.xhttp_settings.sc_min_posts_interval_ms ?? undefined,
                  download_settings: host.transport_settings.xhttp_settings.download_settings ?? undefined,
                  xmux: host.transport_settings.xhttp_settings.xmux
                    ? {
                        max_concurrency: host.transport_settings.xhttp_settings.xmux.maxConcurrency ?? undefined,
                        max_connections: host.transport_settings.xhttp_settings.xmux.maxConnections ?? undefined,
                        c_max_reuse_times: host.transport_settings.xhttp_settings.xmux.cMaxReuseTimes ?? undefined,
                        h_max_reusable_secs: host.transport_settings.xhttp_settings.xmux.hMaxReusableSecs ?? undefined,
                        h_max_request_times: host.transport_settings.xhttp_settings.xmux.hMaxRequestTimes ?? undefined,
                        h_keep_alive_period: host.transport_settings.xhttp_settings.xmux.hKeepAlivePeriod ?? undefined,
                      }
                    : undefined,
                }
              : undefined,
            grpc_settings: host.transport_settings.grpc_settings
              ? {
                  multi_mode: host.transport_settings.grpc_settings.multi_mode === null ? undefined : !!host.transport_settings.grpc_settings.multi_mode,
                  idle_timeout: host.transport_settings.grpc_settings.idle_timeout ?? undefined,
                  health_check_timeout: host.transport_settings.grpc_settings.health_check_timeout ?? undefined,
                  permit_without_stream: host.transport_settings.grpc_settings.permit_without_stream ?? undefined,
                  initial_windows_size: host.transport_settings.grpc_settings.initial_windows_size ?? undefined,
                }
              : undefined,
            kcp_settings: host.transport_settings.kcp_settings
              ? {
                  mtu: host.transport_settings.kcp_settings.mtu ?? undefined,
                  tti: host.transport_settings.kcp_settings.tti ?? undefined,
                  uplink_capacity: host.transport_settings.kcp_settings.uplink_capacity ?? undefined,
                  downlink_capacity: host.transport_settings.kcp_settings.downlink_capacity ?? undefined,
                  congestion: host.transport_settings.kcp_settings.congestion === null ? undefined : !!host.transport_settings.kcp_settings.congestion,
                  read_buffer_size: host.transport_settings.kcp_settings.read_buffer_size ?? undefined,
                  write_buffer_size: host.transport_settings.kcp_settings.write_buffer_size ?? undefined,
                }
              : undefined,
            tcp_settings: host.transport_settings.tcp_settings
              ? {
                  header: host.transport_settings.tcp_settings.header ?? undefined,
                  request: host.transport_settings.tcp_settings.request
                    ? {
                        version: host.transport_settings.tcp_settings.request.version ?? undefined,
                        method: host.transport_settings.tcp_settings.request.method ?? undefined,
                        headers: host.transport_settings.tcp_settings.request.headers ?? undefined,
                      }
                    : undefined,
                  response: host.transport_settings.tcp_settings.response
                    ? {
                        version: host.transport_settings.tcp_settings.response.version ?? undefined,
                        status: host.transport_settings.tcp_settings.response.status ?? undefined,
                        reason: host.transport_settings.tcp_settings.response.reason ?? undefined,
                        headers: host.transport_settings.tcp_settings.response.headers ?? undefined,
                      }
                    : undefined,
                }
              : undefined,
            websocket_settings: host.transport_settings.websocket_settings
              ? {
                  heartbeatPeriod: host.transport_settings.websocket_settings.heartbeatPeriod ?? undefined,
                }
              : undefined,
          }
        : undefined,
      wireguard_overrides: host.wireguard_overrides
        ? {
            allowed_ips: host.wireguard_overrides.allowed_ips ?? [],
            mtu: host.wireguard_overrides.mtu ?? undefined,
            reserved: host.wireguard_overrides.reserved ?? '',
            keepalive_seconds: host.wireguard_overrides.keepalive_seconds ?? undefined,
          }
        : undefined,
    }
    form.reset(formData)
    setEditingHost(host)
    onAddHost(true)
  }

  const handleDuplicate = async (host: BaseHost) => {
    if (!host) return

    try {
      // Create duplicate with slightly modified name and same priority
      // The priority will be handled by the drag-and-drop reordering system
      const newHost: CreateHost = {
        remark: `${host.remark || ''} (copy)`,
        address: host.address || [],
        port: host.port,
        inbound_tag: host.inbound_tag || '',
        status: host.status || [],
        host: host.host || [],
        sni: host.sni || [],
        path: host.path || '',
        security: host.security || 'inbound_default',
        alpn: !host.alpn || host.alpn.length === 0 ? undefined : host.alpn,
        fingerprint: host.fingerprint === '' ? undefined : host.fingerprint,
        allowinsecure: host.allowinsecure || false,
        is_disabled: host.is_disabled || false,
        random_user_agent: host.random_user_agent || false,
        use_sni_as_host: host.use_sni_as_host || false,
        vless_route: host.vless_route || undefined,
        priority: host.priority ?? 0, // Use the same priority as the original host
        ech_config_list: host.ech_config_list,
        ech_query_strategy: host.ech_query_strategy || undefined,
        pinned_peer_cert_sha256: host.pinned_peer_cert_sha256 || undefined,
        verify_peer_cert_by_name: host.verify_peer_cert_by_name || undefined,
        fragment_settings: host.fragment_settings,
        noise_settings: host.noise_settings,
        mux_settings: host.mux_settings,
        transport_settings: host.transport_settings as any, // Type cast needed due to Output/Input mismatch
        http_headers: host.http_headers || {},
        wireguard_overrides: host.wireguard_overrides ?? undefined,
        subscription_templates: host.subscription_templates ?? undefined,
      }

      await createHost(newHost)

      // Show success toast
      toast.success(t('host.duplicateSuccess', { name: host.remark || '' }))

      // Refresh the hosts data
      refreshHostsData()
    } catch (error) {
      // Show error toast
      toast.error(t('host.duplicateFailed', { name: host.remark || '' }))
    }
  }
  const cleanEmptyValues = (obj: any) => {
    if (!obj) return undefined
    const cleaned: any = {}
    for (const [key, value] of Object.entries(obj)) {
      if (value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0) || (typeof value === 'object' && Object.keys(value).length === 0)) {
        continue
      }
      if (typeof value === 'object') {
        const cleanedValue = cleanEmptyValues(value)
        if (cleanedValue !== undefined) {
          cleaned[key] = cleanedValue
        }
      } else {
        cleaned[key] = value
      }
    }
    return Object.keys(cleaned).length > 0 ? cleaned : undefined
  }

  const handleSubmit = async (data: HostFormValues) => {
    try {
      const response = await onSubmit(data)
      if (response.status === 200) {
        if (editingHost?.id) {
          toast.success(t('hostsDialog.editSuccess', { name: data.remark }))
        } else {
          toast.success(t('hostsDialog.createSuccess', { name: data.remark }))
        }

        // Refresh the hosts data
        refreshHostsData()
      }
      return response
    } catch (error) {
      console.error('Error submitting form:', error)
      throw error
    }
  }

  const handleBulkDelete = async () => {
    if (!selectedHostIds.length) return

    try {
      const response = await bulkDeleteHostsMutation.mutateAsync({
        data: {
          ids: selectedHostIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('deleteHost.bulkDeleteSuccess', {
          count: response.count,
          defaultValue: '{{count}} hosts deleted successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      await refreshHostsData()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description:
          error?.data?.detail ||
          error?.message ||
          t('deleteHost.bulkDeleteFailed', {
            defaultValue: 'Failed to delete selected hosts.',
          }),
      })
    }
  }

  const handleBulkDisable = async () => {
    if (!selectedDisableEligibleIds.length) return

    try {
      const response = await bulkDisableHostsMutation.mutateAsync({
        data: {
          ids: selectedDisableEligibleIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('host.bulkDisableSuccess', {
          count: response.count,
          defaultValue: '{{count}} hosts disabled successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      await refreshHostsData()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('host.bulkDisableFailed', { defaultValue: 'Failed to disable selected hosts.' }),
      })
    }
  }

  const handleBulkEnable = async () => {
    if (!selectedEnableEligibleIds.length) return

    try {
      const response = await bulkEnableHostsMutation.mutateAsync({
        data: {
          ids: selectedEnableEligibleIds,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('host.bulkEnableSuccess', {
          count: response.count,
          defaultValue: '{{count}} hosts enabled successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      await refreshHostsData()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('host.bulkEnableFailed', { defaultValue: 'Failed to enable selected hosts.' }),
      })
    }
  }

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event

    const hasSearchQuery = Boolean(filters.search?.trim())
    const hasActiveFilters = Boolean(
      (filters.status && filters.status.length > 0) || (filters.inbound_tags && filters.inbound_tags.length > 0) || filters.security || typeof filters.is_disabled === 'boolean',
    )
    if (hasSearchQuery || hasActiveFilters) return

    if (!over || active.id === over.id || !hosts) return

    const oldIndex = hosts.findIndex(item => item.id === active.id)
    const newIndex = hosts.findIndex(item => item.id === over.id)

    if (oldIndex === -1 || newIndex === -1) return

    // Optimistically update the UI first
    const reorderedHosts = arrayMove(hosts, oldIndex, newIndex)
    const updatedHosts = reorderedHosts.map((host, index) => ({
      ...host,
      priority: index,
    }))

    setHosts(updatedHosts)
    setIsUpdatingPriorities(true)

    try {
      // Prepare the hosts data for the API call with proper data transformation
      const hostsToUpdate: CreateHost[] = updatedHosts.map((host, index) => ({
        id: host.id,
        remark: host.remark || '',
        address: host.address || [],
        port: host.port,
        inbound_tag: host.inbound_tag || '',
        status: host.status || [],
        host: host.host || [],
        sni: host.sni || [],
        path: host.path || '',
        security: host.security || 'inbound_default',
        alpn: host.alpn || [],
        fingerprint: host.fingerprint || '',
        allowinsecure: host.allowinsecure || false,
        is_disabled: host.is_disabled || false,
        random_user_agent: host.random_user_agent || false,
        use_sni_as_host: host.use_sni_as_host || false,
        vless_route: host.vless_route || undefined,
        priority: index, // New priority based on position
        ech_config_list: host.ech_config_list,
        ech_query_strategy: host.ech_query_strategy || undefined,
        pinned_peer_cert_sha256: host.pinned_peer_cert_sha256 || undefined,
        verify_peer_cert_by_name: host.verify_peer_cert_by_name || undefined,
        subscription_templates: host.subscription_templates ?? undefined,
        fragment_settings: host.fragment_settings,
        noise_settings: host.noise_settings,
        mux_settings: host.mux_settings
          ? {
              xray: host.mux_settings.xray
                ? {
                    enabled: host.mux_settings.xray.enabled ?? false,
                    concurrency: host.mux_settings.xray.concurrency ?? null,
                    xudp_concurrency: host.mux_settings.xray.xudpConcurrency ?? null,
                    xudp_proxy_443: host.mux_settings.xray.xudpProxyUDP443 ?? 'reject',
                  }
                : undefined,
              sing_box: host.mux_settings.sing_box
                ? {
                    enable: host.mux_settings.sing_box.enable ?? false,
                    protocol: host.mux_settings.sing_box.protocol ?? 'smux',
                    max_connections: host.mux_settings.sing_box.max_connections ?? null,
                    max_streams: host.mux_settings.sing_box.max_streams ?? null,
                    min_streams: host.mux_settings.sing_box.min_streams ?? null,
                    padding: host.mux_settings.sing_box.padding ?? undefined,
                    brutal: host.mux_settings.sing_box.brutal ?? null,
                  }
                : undefined,
              clash: host.mux_settings.clash
                ? {
                    enable: host.mux_settings.clash.enable ?? false,
                    protocol: host.mux_settings.clash.protocol ?? 'smux',
                    max_connections: host.mux_settings.clash.max_connections ?? null,
                    max_streams: host.mux_settings.clash.max_streams ?? null,
                    min_streams: host.mux_settings.clash.min_streams ?? null,
                    padding: host.mux_settings.clash.padding ?? undefined,
                    brutal: host.mux_settings.clash.brutal ?? null,
                    statistic: host.mux_settings.clash.statistic ?? undefined,
                    only_tcp: host.mux_settings.clash.only_tcp ?? undefined,
                  }
                : undefined,
            }
          : undefined,
        transport_settings: host.transport_settings
          ? {
              xhttp_settings: host.transport_settings.xhttp_settings
                ? {
                    mode: host.transport_settings.xhttp_settings.mode ?? undefined,
                    no_grpc_header: host.transport_settings.xhttp_settings.no_grpc_header === null ? undefined : !!host.transport_settings.xhttp_settings.no_grpc_header,
                    x_padding_bytes: host.transport_settings.xhttp_settings.x_padding_bytes ?? undefined,
                    x_padding_obfs_mode: host.transport_settings.xhttp_settings.x_padding_obfs_mode === null ? undefined : !!host.transport_settings.xhttp_settings.x_padding_obfs_mode,
                    x_padding_key: host.transport_settings.xhttp_settings.x_padding_key ?? undefined,
                    x_padding_header: host.transport_settings.xhttp_settings.x_padding_header ?? undefined,
                    x_padding_placement: host.transport_settings.xhttp_settings.x_padding_placement ?? undefined,
                    x_padding_method: host.transport_settings.xhttp_settings.x_padding_method ?? undefined,
                    uplink_http_method: host.transport_settings.xhttp_settings.uplink_http_method ?? undefined,
                    session_placement: host.transport_settings.xhttp_settings.session_placement ?? undefined,
                    session_key: host.transport_settings.xhttp_settings.session_key ?? undefined,
                    seq_placement: host.transport_settings.xhttp_settings.seq_placement ?? undefined,
                    seq_key: host.transport_settings.xhttp_settings.seq_key ?? undefined,
                    uplink_data_placement: host.transport_settings.xhttp_settings.uplink_data_placement ?? undefined,
                    uplink_data_key: host.transport_settings.xhttp_settings.uplink_data_key ?? undefined,
                    uplink_chunk_size: host.transport_settings.xhttp_settings.uplink_chunk_size ?? undefined,
                    sc_max_each_post_bytes: host.transport_settings.xhttp_settings.sc_max_each_post_bytes ?? undefined,
                    sc_min_posts_interval_ms: host.transport_settings.xhttp_settings.sc_min_posts_interval_ms ?? undefined,
                    download_settings: host.transport_settings.xhttp_settings.download_settings ?? undefined,
                    xmux: host.transport_settings.xhttp_settings.xmux
                      ? {
                          max_concurrency: host.transport_settings.xhttp_settings.xmux.maxConcurrency ?? undefined,
                          max_connections: host.transport_settings.xhttp_settings.xmux.maxConnections ?? undefined,
                          c_max_reuse_times: host.transport_settings.xhttp_settings.xmux.cMaxReuseTimes ?? undefined,
                          h_max_reusable_secs: host.transport_settings.xhttp_settings.xmux.hMaxReusableSecs ?? undefined,
                          h_max_request_times: host.transport_settings.xhttp_settings.xmux.hMaxRequestTimes ?? undefined,
                          h_keep_alive_period: host.transport_settings.xhttp_settings.xmux.hKeepAlivePeriod ?? undefined,
                        }
                      : undefined,
                  }
                : undefined,
              grpc_settings: host.transport_settings.grpc_settings
                ? {
                    multi_mode: host.transport_settings.grpc_settings.multi_mode === null ? undefined : !!host.transport_settings.grpc_settings.multi_mode,
                    idle_timeout: host.transport_settings.grpc_settings.idle_timeout ?? undefined,
                    health_check_timeout: host.transport_settings.grpc_settings.health_check_timeout ?? undefined,
                    permit_without_stream: host.transport_settings.grpc_settings.permit_without_stream ?? undefined,
                    initial_windows_size: host.transport_settings.grpc_settings.initial_windows_size ?? undefined,
                  }
                : undefined,
              kcp_settings: host.transport_settings.kcp_settings
                ? {
                    mtu: host.transport_settings.kcp_settings.mtu ?? undefined,
                    tti: host.transport_settings.kcp_settings.tti ?? undefined,
                    uplink_capacity: host.transport_settings.kcp_settings.uplink_capacity ?? undefined,
                    downlink_capacity: host.transport_settings.kcp_settings.downlink_capacity ?? undefined,
                    congestion: host.transport_settings.kcp_settings.congestion === null ? undefined : !!host.transport_settings.kcp_settings.congestion,
                    read_buffer_size: host.transport_settings.kcp_settings.read_buffer_size ?? undefined,
                    write_buffer_size: host.transport_settings.kcp_settings.write_buffer_size ?? undefined,
                  }
                : undefined,
              tcp_settings: host.transport_settings.tcp_settings
                ? {
                    header: host.transport_settings.tcp_settings.header ?? undefined,
                    request: host.transport_settings.tcp_settings.request
                      ? {
                          version: host.transport_settings.tcp_settings.request.version ?? undefined,
                          method: host.transport_settings.tcp_settings.request.method ?? undefined,
                          headers: host.transport_settings.tcp_settings.request.headers ?? undefined,
                        }
                      : undefined,
                    response: host.transport_settings.tcp_settings.response
                      ? {
                          version: host.transport_settings.tcp_settings.response.version ?? undefined,
                          status: host.transport_settings.tcp_settings.response.status ?? undefined,
                          reason: host.transport_settings.tcp_settings.response.reason ?? undefined,
                          headers: host.transport_settings.tcp_settings.response.headers ?? undefined,
                        }
                      : undefined,
                  }
                : undefined,
              websocket_settings: host.transport_settings.websocket_settings
                ? {
                    heartbeatPeriod: host.transport_settings.websocket_settings.heartbeatPeriod ?? undefined,
                  }
                : undefined,
            }
          : undefined,
        wireguard_overrides: host.wireguard_overrides ?? undefined,
        http_headers: host.http_headers || {},
      }))

      // Make the API call to update priorities
      await modifyHosts(hostsToUpdate)

      // Update local state with the response data
      setHosts(updatedHosts)

      // Show success message
      toast.success(t('host.priorityUpdated', { defaultValue: 'Host priorities updated' }))
    } catch (error) {
      console.error('Error updating host priorities:', error)

      // Revert the optimistic update on error
      setHosts(hosts)

      // Show error message
      toast.error(t('host.priorityUpdateError', { defaultValue: 'Failed to update priorities' }))
    } finally {
      setIsUpdatingPriorities(false)
    }
  }

  // Filter out hosts without IDs for the sortable context
  const sortableHosts =
    hosts
      ?.filter(host => host.id !== null)
      .map(host => ({
        id: host.id as UniqueIdentifier,
      })) ?? []

  // Sort hosts by priority (lower number = higher priority), then by ID for stable sorting
  const sortedHosts = [...(hosts ?? [])].sort((a, b) => {
    const priorityA = a.priority ?? 0
    const priorityB = b.priority ?? 0

    // First sort by priority
    if (priorityA !== priorityB) {
      return priorityA - priorityB
    }

    // If priorities are the same, sort by ID for stable ordering
    const idA = a.id ?? 0
    const idB = b.id ?? 0
    return idA - idB
  })

  // Filter hosts by search query and advanced filters
  const filteredHosts = useMemo(() => {
    const query = filters.search?.toLowerCase().trim()
    const statusFilters = filters.status
    const inboundFilters = filters.inbound_tags
    const securityFilter = filters.security
    const disabledFilter = filters.is_disabled

    return sortedHosts.filter(host => {
      if (query) {
        const remarkMatch = host.remark?.toLowerCase().includes(query)
        const addressMatch = Array.isArray(host.address) ? host.address.some(addr => addr.toLowerCase().includes(query)) : false
        const inboundTagMatch = host.inbound_tag?.toLowerCase().includes(query)
        const hostMatch = Array.isArray(host.host) ? host.host.some(h => h.toLowerCase().includes(query)) : false
        const sniMatch = Array.isArray(host.sni) ? host.sni.some(sni => sni.toLowerCase().includes(query)) : false
        const portMatch = host.port?.toString().includes(query)
        if (!remarkMatch && !addressMatch && !inboundTagMatch && !hostMatch && !sniMatch && !portMatch) {
          return false
        }
      }

      if (statusFilters && statusFilters.length > 0) {
        if (!host.status || host.status.length === 0) {
          return false
        }
        if (!statusFilters.some(status => host.status?.includes(status))) {
          return false
        }
      }

      if (inboundFilters && inboundFilters.length > 0 && (!host.inbound_tag || !inboundFilters.includes(host.inbound_tag))) {
        return false
      }

      const hostSecurity = host.security || 'inbound_default'
      if (securityFilter && hostSecurity !== securityFilter) {
        return false
      }

      if (typeof disabledFilter === 'boolean' && Boolean(host.is_disabled) !== disabledFilter) {
        return false
      }

      return true
    })
  }, [sortedHosts, filters])

  const listColumns = useHostsListColumns({
    onEdit: handleEdit,
    onDuplicate: handleDuplicate,
    onDataChanged: refreshHostsData,
  })

  const hasActiveAdvanceFilters = Boolean(
    (filters.status && filters.status.length > 0) || (filters.inbound_tags && filters.inbound_tags.length > 0) || filters.security || typeof filters.is_disabled === 'boolean',
  )
  const hasSearch = Boolean(filters.search?.trim())
  const isSortingDisabled = isUpdatingPriorities || hasSearch || hasActiveAdvanceFilters
  const isCurrentlyLoading = hosts === undefined || (isRefreshing && sortedHosts.length === 0)
  const isEmpty = !isCurrentlyLoading && filteredHosts.length === 0 && !hasSearch && !hasActiveAdvanceFilters && sortedHosts.length === 0
  const isSearchEmpty = !isCurrentlyLoading && filteredHosts.length === 0 && (hasSearch || hasActiveAdvanceFilters)
  const selectedCount = selectedHostIds.length
  const selectedHosts = (hosts || []).filter(host => typeof host.id === 'number' && selectedHostIds.includes(host.id))
  const selectedEnableEligibleIds = selectedHosts.filter(host => Boolean(host.is_disabled)).map(host => host.id as number)
  const selectedDisableEligibleIds = selectedHosts.filter(host => !Boolean(host.is_disabled)).map(host => host.id as number)
  const enableEligibleCount = selectedEnableEligibleIds.length
  const disableEligibleCount = selectedDisableEligibleIds.length
  const bulkActions: BulkActionItem[] = selectedCount
    ? [
        {
          key: 'delete',
          label: t('delete'),
          icon: Trash2,
          onClick: () => setBulkAction('delete'),
          direct: true,
          destructive: true,
        },
        ...(disableEligibleCount > 0
          ? [
            {
              key: 'disable',
              label: t('disable'),
              icon: PowerOff,
              onClick: () => setBulkAction('disable'),
            } as BulkActionItem,
          ]
          : []),
        ...(enableEligibleCount > 0
          ? [
            {
              key: 'enable',
              label: t('enable'),
              icon: Power,
              onClick: () => setBulkAction('enable'),
            } as BulkActionItem,
          ]
          : []),
      ]
    : []
  const bulkActionConfigs: Record<BulkHostActionType, BulkActionDialogConfig> = {
    delete: {
      title: t('deleteHost.bulkDeleteTitle', { defaultValue: 'Delete Selected Hosts' }),
      description: t('deleteHost.bulkDeletePrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to delete {{count}} selected hosts? This action cannot be undone.',
      }),
      actionLabel: t('delete'),
      onConfirm: handleBulkDelete,
      isPending: bulkDeleteHostsMutation.isPending,
      destructive: true,
    },
    enable: {
      title: t('host.bulkEnableTitle', { defaultValue: 'Enable Selected Hosts' }),
      description: t('host.bulkEnablePrompt', {
        count: enableEligibleCount,
        defaultValue: 'Are you sure you want to enable {{count}} selected hosts?',
      }),
      actionLabel: t('enable'),
      onConfirm: handleBulkEnable,
      isPending: bulkEnableHostsMutation.isPending,
    },
    disable: {
      title: t('host.bulkDisableTitle', { defaultValue: 'Disable Selected Hosts' }),
      description: t('host.bulkDisablePrompt', {
        count: disableEligibleCount,
        defaultValue: 'Are you sure you want to disable {{count}} selected hosts?',
      }),
      actionLabel: t('disable'),
      onConfirm: handleBulkDisable,
      isPending: bulkDisableHostsMutation.isPending,
    },
  }
  const activeBulkActionConfig = bulkAction ? bulkActionConfigs[bulkAction] : null

  return (
    <div>
      <div className="mb-4">
        <HostFilters
          filters={filters}
          onFilterChange={handleFilterChange}
          onRefresh={handleRefreshClick}
          isRefreshing={isRefreshing}
          advanceSearchOnOpen={handleAdvanceSearchOpen}
          onClearAdvanceSearch={handleClearAdvanceSearch}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
        />
      </div>
      <BulkActionsBar selectedCount={selectedCount} onClear={clearSelection} actions={bulkActions} />
      {(isCurrentlyLoading || filteredHosts.length > 0) && viewMode === 'grid' && (
        <DndContext sensors={isSortingDisabled ? [] : sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={sortableHosts} strategy={rectSortingStrategy}>
            <ListGenerator
              data={filteredHosts}
              columns={listColumns}
              getRowId={host => host.id ?? host.remark ?? 'host'}
              isLoading={isCurrentlyLoading}
              loadingRows={6}
              className="max-w-screen-[2000px] min-h-screen gap-3 overflow-hidden"
              mode="grid"
              enableSelection
              enableGridSelection
              selectedRowIds={selectedHostIds}
              onSelectionChange={ids => setSelectedHostIds(ids.map(id => Number(id)))}
              isRowSelectable={host => typeof host.id === 'number'}
              showEmptyState={false}
              renderGridItem={host => (
                <SortableHost key={host.id ?? 'new'} host={host} onEdit={handleEdit} onDuplicate={handleDuplicate} onDataChanged={refreshHostsData} disabled={isSortingDisabled} />
              )}
              renderGridSkeleton={index => (
                <Card key={index} className="p-4">
                  <div className="flex animate-pulse items-center gap-3">
                    <div className="h-5 w-5 shrink-0 rounded-sm bg-muted" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-muted" />
                        <div className="h-4 w-2/5 rounded-md bg-muted" />
                      </div>
                      <div className="h-3 w-4/5 rounded-md bg-muted" />
                      <div className="h-3 w-2/5 rounded-md bg-muted" />
                    </div>
                    <div className="h-8 w-8 shrink-0 rounded-md bg-muted" />
                  </div>
                </Card>
              )}
            />
          </SortableContext>
        </DndContext>
      )}
      {(isCurrentlyLoading || filteredHosts.length > 0) && viewMode === 'list' && (
        <DndContext sensors={isSortingDisabled ? [] : sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={sortableHosts} strategy={rectSortingStrategy}>
            <ListGenerator
              data={filteredHosts}
              columns={listColumns}
              getRowId={host => host.id ?? host.remark ?? 'host'}
              isLoading={isCurrentlyLoading}
              loadingRows={6}
              className="max-w-screen-[2000px] min-h-screen gap-3 overflow-hidden"
              mode="list"
              enableSelection
              selectedRowIds={selectedHostIds}
              onSelectionChange={ids => setSelectedHostIds(ids.map(id => Number(id)))}
              isRowSelectable={host => typeof host.id === 'number'}
              showEmptyState={false}
              onRowClick={handleEdit}
              enableSorting
              sortingDisabled={isSortingDisabled}
            />
          </SortableContext>
        </DndContext>
      )}
      {isEmpty && !isCurrentlyLoading && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('host.noHosts')}</h3>
              <p className="mx-auto max-w-2xl text-muted-foreground">{t('host.noHostsDescription')}</p>
            </div>
          </CardContent>
        </Card>
      )}
      {isSearchEmpty && !isCurrentlyLoading && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('noResults')}</h3>
              <p className="mx-auto max-w-2xl text-muted-foreground">{t('host.noSearchResults')}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <HostAdvanceSearchModal
        isDialogOpen={isAdvanceSearchOpen}
        onOpenChange={handleAdvanceSearchOpen}
        form={advanceSearchForm}
        onSubmit={handleAdvanceSearchSubmit}
        inbounds={inbounds.map(inbound => inbound.tag)}
        isLoadingInbounds={isLoadingInbounds}
      />

      <HostModal
        isDialogOpen={isDialogOpen}
        onSubmit={handleSubmit}
        onOpenChange={open => {
          if (!open) {
            setEditingHost(null)
            form.reset(hostFormDefaultValues)
          } else if (!editingHost) {
            form.reset(hostFormDefaultValues)
          }
          onAddHost(open)
        }}
        form={form}
        editingHost={!!editingHost}
        inboundDetails={inbounds}
        isLoadingInbounds={isLoadingInbounds}
      />
      {activeBulkActionConfig && (
        <BulkActionAlertDialog
          open={!!bulkAction}
          onOpenChange={open => setBulkAction(open ? bulkAction : null)}
          title={activeBulkActionConfig.title}
          description={activeBulkActionConfig.description}
          actionLabel={activeBulkActionConfig.actionLabel}
          onConfirm={activeBulkActionConfig.onConfirm}
          isPending={activeBulkActionConfig.isPending}
          destructive={activeBulkActionConfig.destructive}
        />
      )}
    </div>
  )
}
