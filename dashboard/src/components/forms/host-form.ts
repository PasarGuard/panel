import * as z from 'zod'

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
  subscription_templates?: {
    xray?: string | null
    [key: string]: any
  }
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
  pinned_peer_cert_sha256?: string
  verify_peer_cert_by_name?: string[]
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
      mtu?: number
      tti?: number
      uplink_capacity?: number
      downlink_capacity?: number
      congestion?: boolean
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
        mtu: z.number().nullish().optional(),
        tti: z.number().nullish().optional(),
        uplink_capacity: z.number().nullish().optional(),
        downlink_capacity: z.number().nullish().optional(),
        congestion: z.boolean().nullish().optional(),
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
  subscription_templates: z
    .object({
      xray: z.string().nullish(),
    })
    .passthrough()
    .nullish(),
  security: z.enum(['inbound_default', 'tls', 'none']).default('inbound_default'),
  alpn: z.array(z.string()).default([]),
  fingerprint: z.string().default(''),
  allowinsecure: z.boolean().default(false),
  random_user_agent: z.boolean().default(false),
  use_sni_as_host: z.boolean().default(false),
  vless_route: z.union([z.literal(''), z.string().regex(/^[0-9a-fA-F]{4}$/, 'VLESS route must be exactly 4 hex characters')]).optional(),
  priority: z.number().default(0),
  is_disabled: z.boolean().default(false),
  ech_config_list: z.string().optional(),
  pinned_peer_cert_sha256: z.string().max(128, 'Pinned peer cert SHA256 must be at most 128 characters').optional(),
  verify_peer_cert_by_name: z.array(z.string()).default([]),
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

export const hostFormDefaultValues: HostFormValues = {
  remark: '',
  address: [],
  port: undefined,
  inbound_tag: '',
  status: [],
  host: [],
  sni: [],
  path: '',
  http_headers: {},
  subscription_templates: undefined,
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
  pinned_peer_cert_sha256: undefined,
  verify_peer_cert_by_name: [],
  fragment_settings: undefined,
}
