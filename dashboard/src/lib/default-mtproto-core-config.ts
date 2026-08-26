export const DEFAULT_MTPROTO_CORE_CONFIG: Record<string, unknown> = {
  inbound_tag: 'mtproto',
  general: {
    use_middle_proxy: true,
    prefer_ipv6: false,
    fast_update: false,
    modes: {
      classic: true,
      secure: true,
      tls: true,
    },
  },
  server: {
    port: 443,
    proxy_protocol: false,
    listeners: [{ ip: '0.0.0.0' }],
  },
  censorship: {
    tls_domain: 'cloudflare.com',
  },
}

export const DEFAULT_MTPROTO_CORE_CONFIG_JSON = JSON.stringify(DEFAULT_MTPROTO_CORE_CONFIG, null, 2)
