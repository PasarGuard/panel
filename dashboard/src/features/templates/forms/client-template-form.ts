import { ClientTemplateType } from '@/service/api'
import { z } from 'zod'

export const clientTemplateFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(64),
  template_type: z.enum([
    ClientTemplateType.clash_subscription,
    ClientTemplateType.xray_subscription,
    ClientTemplateType.singbox_subscription,
    ClientTemplateType.user_agent,
    ClientTemplateType.grpc_user_agent,
  ]),
  content: z.string().min(1, 'Content is required'),
  is_default: z.boolean().optional(),
})

export type ClientTemplateFormValues = z.infer<typeof clientTemplateFormSchema>
const DEFAULT_USER_AGENT_TEMPLATE = {
  list: [],
}
export const DEFAULT_TEMPLATE_CONTENT: Record<ClientTemplateType, string> = {
  [ClientTemplateType.clash_subscription]: `mode: rule
mixed-port: 7890
ipv6: true

tun:
  enable: true
  stack: mixed
  dns-hijack:
    - "any:53"
  auto-route: true
  auto-detect-interface: true
  strict-route: true

dns:
  enable: true
  listen: :1053
  ipv6: true
  nameserver:
    - 'https://1.1.1.1/dns-query#PROXY'
  proxy-server-nameserver:
    - '178.22.122.100'
    - '78.157.42.100'

sniffer:
  enable: true
  override-destination: true
  sniff:
    HTTP:
      ports: [80, 8080-8880]
    TLS:
      ports: [443, 8443]
    QUIC:
      ports: [443, 8443]

{{ conf | except("proxy-groups", "port", "mode", "rules") | yaml }}

proxy-groups:
- name: 'PROXY'
  type: 'select'
  proxies:
  - 'Fastest'
  {{ proxy_remarks | yaml | indent(2) }}

- name: 'Fastest'
  type: 'url-test'
  proxies:
  {{ proxy_remarks | yaml | indent(2) }}

rules:
  - MATCH,PROXY`,

  [ClientTemplateType.xray_subscription]: JSON.stringify(
    {
      log: {
        access: '',
        error: '',
        loglevel: 'warning',
      },
      inbounds: [
        {
          tag: 'socks',
          port: 10808,
          listen: '0.0.0.0',
          protocol: 'socks',
          sniffing: { enabled: true, destOverride: ['http', 'tls'], routeOnly: false },
          settings: { auth: 'noauth', udp: true, allowTransparent: false },
        },
        {
          tag: 'http',
          port: 10809,
          listen: '0.0.0.0',
          protocol: 'http',
          sniffing: { enabled: true, destOverride: ['http', 'tls'], routeOnly: false },
          settings: { auth: 'noauth', udp: true, allowTransparent: false },
        },
      ],
      outbounds: [
        {
          protocol: 'freedom',
          tag: 'DIRECT',
        },
        {
          protocol: 'blackhole',
          tag: 'BLOCK',
        },
      ],
      dns: {
        servers: ['1.1.1.1', '8.8.8.8'],
      },
      routing: {
        domainStrategy: 'AsIs',
        rules: [],
      },
    },
    null,
    2,
  ),

  [ClientTemplateType.singbox_subscription]: JSON.stringify(
    {
      log: {
        level: 'warn',
        timestamp: false,
      },
      dns: {
        servers: [
          {
            type: 'udp',
            tag: 'dns-remote',
            server: '1.1.1.2',
            detour: 'proxy',
          },
          {
            type: 'local',
            tag: 'dns-local',
          },
        ],
        final: 'dns-remote',
      },
      inbounds: [
        {
          type: 'tun',
          tag: 'tun-in',
          interface_name: 'sing-tun',
          address: ['172.19.0.1/30', 'fdfe:dcba:9876::1/126'],
          auto_route: true,
          route_exclude_address: ['192.168.0.0/16', '10.0.0.0/8', '169.254.0.0/16', '172.16.0.0/12', 'fe80::/10', 'fc00::/7'],
        },
      ],
      outbounds: [
        {
          type: 'selector',
          tag: 'proxy',
          outbounds: null,
          interrupt_exist_connections: true,
        },
        {
          type: 'urltest',
          tag: 'Best Latency',
          outbounds: null,
        },
        {
          type: 'direct',
          tag: 'direct',
        },
      ],
      route: {
        rules: [
          {
            inbound: 'tun-in',
            action: 'sniff',
          },
          {
            protocol: 'dns',
            action: 'hijack-dns',
          },
        ],
        final: 'proxy',
        auto_detect_interface: true,
        override_android_vpn: true,
      },
      experimental: {
        cache_file: { enabled: true, store_dns: true },
      },
    },
    null,
    2,
  ),

  [ClientTemplateType.user_agent]: JSON.stringify(DEFAULT_USER_AGENT_TEMPLATE, null, 2),

  [ClientTemplateType.grpc_user_agent]: JSON.stringify(DEFAULT_USER_AGENT_TEMPLATE, null, 2),
}

export const clientTemplateFormDefaultValues: Partial<ClientTemplateFormValues> = {
  name: '',
  template_type: ClientTemplateType.xray_subscription,
  content: DEFAULT_TEMPLATE_CONTENT[ClientTemplateType.xray_subscription],
  is_default: false,
}
