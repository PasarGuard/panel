import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { BaseHost, CreateHost, createHost, modifyHosts } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { closestCenter, DndContext, DragEndEvent, KeyboardSensor, PointerSensor, UniqueIdentifier, useSensor, useSensors } from '@dnd-kit/core'
import { arrayMove, rectSortingStrategy, SortableContext, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { zodResolver } from '@hookform/resolvers/zod'
import { RefreshCw, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Resolver, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import * as z from 'zod'
import HostModal from '../dialogs/host-modal'
import SortableHost from './sortable-host'
import ViewToggle, { ViewMode } from '@/components/common/view-toggle'
import { ListGenerator } from '@/components/common/list-generator'
import { useHostsListColumns } from '@/components/hosts/use-hosts-list-columns'

interface Brutal {
  enable?: boolean
  up_mbps: number
  down_mbps: number
}

interface XrayMuxSettings {
  enabled?: boolean
  concurrency: number | null
  xudp_concurrency: number | null
  xudp_proxy_443: string
}

interface SingBoxMuxSettings {
  enable?: boolean
  protocol: string | null | undefined
  max_connections: number | null
  max_streams: number | null
  min_streams: number | null
  padding: boolean | null
  brutal: Brutal | null
}

interface ClashMuxSettings {
  enable?: boolean
  protocol: string | null | undefined
  max_connections: number | null
  max_streams: number | null
  min_streams: number | null
  padding: boolean | null
  brutal: Brutal | null
  statistic: boolean | null
  only_tcp: boolean | null
}

interface MuxSettings {
  xray?: XrayMuxSettings
  sing_box?: SingBoxMuxSettings
  clash?: ClashMuxSettings
}

export interface HostFormValues {
  id?: number
  remark: string
  address: string[]
  port?: number
  inbound_tag: string
  status: ('active' | 'disabled' | 'limited' | 'expired' | 'on_hold')[]
  host?: string[]
  sni?: string[]
  path?: string
  http_headers?: Record<string, string>
  security: 'none' | 'tls' | 'inbound_default'
  alpn?: string[]
  fingerprint?: string
  allowinsecure: boolean
  is_disabled: boolean
  random_user_agent: boolean
  use_sni_as_host: boolean
  vless_route?: string
  priority: number
  ech_config_list?: string
  fragment_settings?: {
    xray?: {
      packets?: string
      length?: string
      interval?: string
    }
    sing_box?: {
      fragment?: boolean
      fragment_fallback_delay?: string
      record_fragment?: boolean
    }
  }
  noise_settings?: {
    xray?: {
      type: string
      packet: string
      delay: string
      apply_to: 'ip' | 'ipv4' | 'ipv6'
    }[]
  }
  mux_settings?: MuxSettings
  transport_settings?: {
    xhttp_settings?: {
      mode?: 'auto' | 'packet-up' | 'stream-up' | 'stream-one'
      no_grpc_header?: boolean
      x_padding_bytes?: string
      x_padding_obfs_mode?: boolean
      x_padding_key?: string
      x_padding_header?: string
      x_padding_placement?: string
      x_padding_method?: string
      uplink_http_method?: string
      session_placement?: string
      session_key?: string
      seq_placement?: string
      seq_key?: string
      uplink_data_placement?: string
      uplink_data_key?: string
      uplink_chunk_size?: number
      sc_max_each_post_bytes?: string
      sc_min_posts_interval_ms?: string
      download_settings?: number
      xmux?: {
        max_concurrency?: string
        max_connections?: string
        c_max_reuse_times?: string
        h_max_reusable_secs?: string
        h_max_request_times?: string
        h_keep_alive_period?: number
      }
    }
    grpc_settings?: {
      multi_mode?: boolean
      idle_timeout?: number
      health_check_timeout?: number
      permit_without_stream?: boolean
      initial_windows_size?: number
    }
    kcp_settings?: {
      header?: string
      mtu?: number
      tti?: number
      uplink_capacity?: number
      downlink_capacity?: number
      congestion?: number
      read_buffer_size?: number
      write_buffer_size?: number
    }
    tcp_settings?: {
      header?: string
      request?: {
        version?: string
        headers?: Record<string, string[]>
        method?: string
      }
      response?: {
        version?: string
        headers?: Record<string, string[]>
        status?: string
        reason?: string
      }
    }
    websocket_settings?: {
      heartbeatPeriod?: number
    }
  }
}

// Update the transport settings schema
const transportSettingsSchema = z
  .object({
    xhttp_settings: z
      .object({
        mode: z.enum(['', 'auto', 'packet-up', 'stream-up', 'stream-one']).nullish().optional(),
        no_grpc_header: z.boolean().nullish().optional(),
        x_padding_bytes: z.string().nullish().optional(),
        x_padding_obfs_mode: z.boolean().nullish().optional(),
        x_padding_key: z.string().nullish().optional(),
        x_padding_header: z.string().nullish().optional(),
        x_padding_placement: z.string().nullish().optional(),
        x_padding_method: z.string().nullish().optional(),
        uplink_http_method: z.string().nullish().optional(),
        session_placement: z.string().nullish().optional(),
        session_key: z.string().nullish().optional(),
        seq_placement: z.string().nullish().optional(),
        seq_key: z.string().nullish().optional(),
        uplink_data_placement: z.string().nullish().optional(),
        uplink_data_key: z.string().nullish().optional(),
        uplink_chunk_size: z.number().nullish().optional(),
        sc_max_each_post_bytes: z.string().nullish().optional(),
        sc_min_posts_interval_ms: z.string().nullish().optional(),
        download_settings: z.number().nullish().optional(),
        xmux: z
          .object({
            max_concurrency: z.string().nullish().optional(),
            max_connections: z.string().nullish().optional(),
            c_max_reuse_times: z.string().nullish().optional(),
            h_max_reusable_secs: z.string().nullish().optional(),
            h_max_request_times: z.string().nullish().optional(),
            h_keep_alive_period: z.number().nullish().optional(),
          })
          .nullish()
          .optional(),
      })
      .nullish()
      .optional(),
    grpc_settings: z
      .object({
        multi_mode: z.boolean().nullish().optional(),
        idle_timeout: z.number().nullish().optional(),
        health_check_timeout: z.number().nullish().optional(),
        permit_without_stream: z.boolean().nullish().optional(),
        initial_windows_size: z.number().nullish().optional(),
      })
      .nullish()
      .optional(),
    kcp_settings: z
      .object({
        header: z.string().nullish().optional(),
        mtu: z.number().nullish().optional(),
        tti: z.number().nullish().optional(),
        uplink_capacity: z.number().nullish().optional(),
        downlink_capacity: z.number().nullish().optional(),
        congestion: z.number().nullish().optional(),
        read_buffer_size: z.number().nullish().optional(),
        write_buffer_size: z.number().nullish().optional(),
      })
      .nullish()
      .optional(),
    tcp_settings: z
      .object({
        header: z.enum(['none', 'http', '']).nullish().optional(),
        request: z
          .object({
            version: z.enum(['1.0', '1.1', '2.0', '3.0']).nullish().optional(),
            method: z.enum(['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH', 'TRACE', 'CONNECT']).nullish().optional(),
            headers: z.record(z.array(z.string())).nullish().optional(),
          })
          .nullish()
          .optional(),
        response: z
          .object({
            version: z.enum(['1.0', '1.1', '2.0', '3.0']).nullish().optional(),
            status: z
              .string()
              .regex(/^[1-5]\d{2}$/)
              .nullish()
              .optional(),
            reason: z
              .enum([
                'Continue',
                'Switching Protocols',
                'OK',
                'Created',
                'Accepted',
                'Non-Authoritative Information',
                'No Content',
                'Reset Content',
                'Partial Content',
                'Multiple Choices',
                'Moved Permanently',
                'Found',
                'See Other',
                'Not Modified',
                'Use Proxy',
                'Temporary Redirect',
                'Permanent Redirect',
                'Bad Request',
                'Unauthorized',
                'Payment Required',
                'Forbidden',
                'Not Found',
                'Method Not Allowed',
                'Not Acceptable',
                'Proxy Authentication Required',
                'Request Timeout',
                'Conflict',
                'Gone',
                'Length Required',
                'Precondition Failed',
                'Payload Too Large',
                'URI Too Long',
                'Unsupported Media Type',
                'Range Not Satisfiable',
                'Expectation Failed',
                "I'm a teapot",
                'Misdirected Request',
                'Unprocessable Entity',
                'Locked',
                'Failed Dependency',
                'Too Early',
                'Upgrade Required',
                'Precondition Required',
                'Too Many Requests',
                'Request Header Fields Too Large',
                'Unavailable For Legal Reasons',
                'Internal Server Error',
                'Not Implemented',
                'Bad Gateway',
                'Service Unavailable',
                'Gateway Timeout',
                'HTTP Version Not Supported',
              ])
              .nullish()
              .optional(),
            headers: z.record(z.array(z.string())).nullish().optional(),
          })
          .nullish()
          .optional(),
      })
      .nullish()
      .optional(),
    websocket_settings: z
      .object({
        heartbeatPeriod: z.number().nullish().optional(),
      })
      .nullish()
      .optional(),
  })
  .nullish()
  .optional()

export const HostFormSchema = z.object({
  remark: z.string().min(1, 'Remark is required'),
  address: z.array(z.string()).min(1, 'At least one address is required'),
  port: z.number().min(1, 'Port must be at least 1').max(65535, 'Port must be at most 65535').optional().or(z.literal('')),
  inbound_tag: z.string().min(1, 'Inbound tag is required'),
  status: z.array(z.string()).default([]),
  host: z.array(z.string()).default([]),
  sni: z.array(z.string()).default([]),
  path: z.string().default(''),
  http_headers: z.record(z.string()).default({}),
  security: z.enum(['inbound_default', 'tls', 'none']).default('inbound_default'),
  alpn: z.array(z.string()).default([]),
  fingerprint: z.string().default(''),
  allowinsecure: z.boolean().default(false),
  random_user_agent: z.boolean().default(false),
  use_sni_as_host: z.boolean().default(false),
  vless_route: z
    .union([z.literal(''), z.string().regex(/^[0-9a-fA-F]{4}$/, 'VLESS route must be exactly 4 hex characters')])
    .optional(),
  priority: z.number().default(0),
  is_disabled: z.boolean().default(false),
  ech_config_list: z.string().optional(),
  fragment_settings: z
    .object({
      xray: z
        .object({
          packets: z.string().optional(),
          length: z.string().optional(),
          interval: z.string().optional(),
        })
        .optional(),
      sing_box: z
        .object({
          fragment: z.boolean().optional(),
          fragment_fallback_delay: z.string().optional(),
          record_fragment: z.boolean().optional(),
        })
        .optional(),
    })
    .optional(),
  noise_settings: z
    .object({
      xray: z
        .array(
          z.object({
            type: z
              .string()
              .regex(/^(?:rand|str|base64|hex)$/)
              .optional(),
            packet: z.string().optional(),
            delay: z
              .string()
              .optional()
              .refine(val => !val || /^\d{1,16}(-\d{1,16})?$/.test(val), {
                message: "Delay must be in format like '10-20' or '10'",
              }),
            apply_to: z.enum(['ip', 'ipv4', 'ipv6']).default('ip'),
          }),
        )
        .optional(),
    })
    .optional(),
  mux_settings: z
    .object({
      xray: z
        .object({
          enabled: z.boolean().optional(),
          concurrency: z.number().nullable().optional(),
          xudp_concurrency: z.number().nullable().optional(),
          xudp_proxy_443: z.enum(['reject', 'allow', 'skip']).nullable().optional(),
        })
        .optional(),
      sing_box: z
        .object({
          enable: z.boolean().optional(),
          protocol: z.enum(['none', 'smux', 'yamux', 'h2mux']).default('smux'),
          max_connections: z.number().nullable().optional(),
          max_streams: z.number().nullable().optional(),
          min_streams: z.number().nullable().optional(),
          padding: z.boolean().nullable().optional(),
          brutal: z
            .object({
              enable: z.boolean().optional(),
              up_mbps: z.number().nullable().optional(),
              down_mbps: z.number().nullable().optional(),
            })
            .nullable()
            .optional(),
        })
        .optional(),
      clash: z
        .object({
          enable: z.boolean().optional(),
          protocol: z.enum(['none', 'smux', 'yamux', 'h2mux']).default('smux'),
          max_connections: z.number().nullable().optional(),
          max_streams: z.number().nullable().optional(),
          min_streams: z.number().nullable().optional(),
          padding: z.boolean().nullable().optional(),
          brutal: z
            .object({
              enable: z.boolean().optional(),
              up_mbps: z.number().nullable().optional(),
              down_mbps: z.number().nullable().optional(),
            })
            .nullable()
            .optional(),
          statistic: z.boolean().nullable().optional(),
          only_tcp: z.boolean().nullable().optional(),
        })
        .optional(),
    })
    .optional(),
  transport_settings: transportSettingsSchema,
})

// Define initial default values separately
const initialDefaultValues: HostFormValues = {
  remark: '',
  address: [],
  port: undefined,
  inbound_tag: '',
  status: [],
  host: [],
  sni: [],
  path: '',
  http_headers: {},
  security: 'inbound_default',
  alpn: [],
  fingerprint: '',
  allowinsecure: false,
  is_disabled: false,
  random_user_agent: false,
  use_sni_as_host: false,
  vless_route: '',
  priority: 0,
  ech_config_list: undefined,
  fragment_settings: undefined,
}

export interface HostsListProps {
  data: BaseHost[]
  isDialogOpen: boolean
  onDialogOpenChange: (open: boolean) => void
  onAddHost: (open: boolean) => void
  onSubmit: (data: HostFormValues) => Promise<{ status: number }>
  editingHost: BaseHost | null
  setEditingHost: (host: BaseHost | null) => void
  onRefresh?: () => Promise<unknown>
  isRefreshing?: boolean
}

export default function HostsList({ data, onAddHost, isDialogOpen, onSubmit, editingHost, setEditingHost, onRefresh, isRefreshing: isRefreshingProp }: HostsListProps) {
  const [hosts, setHosts] = useState<BaseHost[] | undefined>()
  const [isUpdatingPriorities, setIsUpdatingPriorities] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [isManualRefreshing, setIsManualRefreshing] = useState(false)
  const { t } = useTranslation()
  const dir = useDirDetection()

  // Set up hosts data from props
  useEffect(() => {
    setHosts(data ?? [])
  }, [data])

  const form = useForm<HostFormValues>({
    resolver: zodResolver(HostFormSchema) as Resolver<HostFormValues>,
    defaultValues: initialDefaultValues,
  })

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
                  x_padding_obfs_mode:
                    host.transport_settings.xhttp_settings.x_padding_obfs_mode === null ? undefined : !!host.transport_settings.xhttp_settings.x_padding_obfs_mode,
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
                  header: host.transport_settings.kcp_settings.header ?? undefined,
                  mtu: host.transport_settings.kcp_settings.mtu ?? undefined,
                  tti: host.transport_settings.kcp_settings.tti ?? undefined,
                  uplink_capacity: host.transport_settings.kcp_settings.uplink_capacity ?? undefined,
                  downlink_capacity: host.transport_settings.kcp_settings.downlink_capacity ?? undefined,
                  congestion: host.transport_settings.kcp_settings.congestion ?? undefined,
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
        fragment_settings: host.fragment_settings,
        noise_settings: host.noise_settings,
        mux_settings: host.mux_settings,
        transport_settings: host.transport_settings as any, // Type cast needed due to Output/Input mismatch
        http_headers: host.http_headers || {},
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

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event

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
                    x_padding_obfs_mode:
                      host.transport_settings.xhttp_settings.x_padding_obfs_mode === null ? undefined : !!host.transport_settings.xhttp_settings.x_padding_obfs_mode,
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
                    header: host.transport_settings.kcp_settings.header ?? undefined,
                    mtu: host.transport_settings.kcp_settings.mtu ?? undefined,
                    tti: host.transport_settings.kcp_settings.tti ?? undefined,
                    uplink_capacity: host.transport_settings.kcp_settings.uplink_capacity ?? undefined,
                    downlink_capacity: host.transport_settings.kcp_settings.downlink_capacity ?? undefined,
                    congestion: host.transport_settings.kcp_settings.congestion ?? undefined,
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

  // Filter hosts by search query
  const filteredHosts = useMemo(() => {
    if (!searchQuery.trim()) return sortedHosts
    const query = searchQuery.toLowerCase().trim()
    return sortedHosts.filter(host => {
      const remarkMatch = host.remark?.toLowerCase().includes(query)
      const addressMatch = Array.isArray(host.address) ? host.address.some(addr => addr.toLowerCase().includes(query)) : false
      const inboundTagMatch = host.inbound_tag?.toLowerCase().includes(query)
      const hostMatch = Array.isArray(host.host) ? host.host.some(h => h.toLowerCase().includes(query)) : false
      return remarkMatch || addressMatch || inboundTagMatch || hostMatch
    })
  }, [sortedHosts, searchQuery])

  const listColumns = useHostsListColumns({
    onEdit: handleEdit,
    onDuplicate: handleDuplicate,
    onDataChanged: refreshHostsData,
  })

  const isCurrentlyLoading = !data || (isRefreshing && sortedHosts.length === 0)
  const isEmpty = !isCurrentlyLoading && filteredHosts.length === 0 && !searchQuery.trim() && sortedHosts.length === 0
  const isSearchEmpty = !isCurrentlyLoading && filteredHosts.length === 0 && searchQuery.trim() !== ''

  return (
    <div>
      {/* Search Input */}
      <div className="mb-4 flex items-center gap-2 md:gap-3">
        <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none" dir={dir}>
          <Search className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground')} />
          <Input placeholder={t('search')} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className={cn('pl-8 pr-10', dir === 'rtl' && 'pl-10 pr-8')} />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground')}>
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <Button
            size="icon-md"
            variant="ghost"
            onClick={handleRefreshClick}
            className={cn('h-9 w-9 rounded-lg border', isRefreshing && 'opacity-70')}
            aria-label={t('autoRefresh.refreshNow')}
            title={t('autoRefresh.refreshNow')}
          >
            <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
          </Button>
          <ViewToggle value={viewMode} onChange={setViewMode} />
        </div>
      </div>
      {(isCurrentlyLoading || filteredHosts.length > 0) && viewMode === 'grid' && (
        <DndContext sensors={isUpdatingPriorities ? [] : sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={sortableHosts} strategy={rectSortingStrategy}>
            <ListGenerator
              data={filteredHosts}
              columns={listColumns}
              getRowId={host => host.id ?? host.remark ?? 'host'}
              isLoading={isCurrentlyLoading}
              loadingRows={6}
              className="gap-3 max-w-screen-[2000px] min-h-screen overflow-hidden"
              mode="grid"
              showEmptyState={false}
              renderGridItem={host => (
                <SortableHost
                  key={host.id ?? 'new'}
                  host={host}
                  onEdit={handleEdit}
                  onDuplicate={handleDuplicate}
                  onDataChanged={refreshHostsData}
                  disabled={isUpdatingPriorities}
                />
              )}
              renderGridSkeleton={index => (
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
              )}
            />
          </SortableContext>
        </DndContext>
      )}
      {(isCurrentlyLoading || filteredHosts.length > 0) && viewMode === 'list' && (
        <DndContext sensors={isUpdatingPriorities ? [] : sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={sortableHosts} strategy={rectSortingStrategy}>
            <ListGenerator
              data={filteredHosts}
              columns={listColumns}
              getRowId={host => host.id ?? host.remark ?? 'host'}
              isLoading={isCurrentlyLoading}
              loadingRows={6}
              className="gap-3 max-w-screen-[2000px] min-h-screen overflow-hidden"
              mode="list"
              showEmptyState={false}
              onRowClick={handleEdit}
              enableSorting
              sortingDisabled={isUpdatingPriorities}
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

      <HostModal
        isDialogOpen={isDialogOpen}
        onSubmit={handleSubmit}
        onOpenChange={open => {
          if (!open) {
            setEditingHost(null)
            form.reset(initialDefaultValues) // Reset to initial values when closing
          } else if (!editingHost) {
            // When opening for a new host, ensure form is reset to initial values
            form.reset(initialDefaultValues)
          }
          onAddHost(open)
        }}
        form={form}
        editingHost={!!editingHost}
      />
    </div>
  )
}
