import { TLS_DOMAIN_PLACEHOLDER } from '@/features/core-editor/kit/mtproto-config'

export const DEFAULT_MTPROTO_CORE_CONFIG: Record<string, unknown> = {
  inbound_tag: 'mtproto',
  general: {
    use_middle_proxy: true,
    modes: {
      classic: false,
      secure: false,
      tls: true,
    },
  },
  server: {
    port: 443,
    listeners: [{ ip: '0.0.0.0' }],
  },
  censorship: {
    tls_domain: TLS_DOMAIN_PLACEHOLDER,
  },
}

export const DEFAULT_MTPROTO_CORE_CONFIG_JSON = JSON.stringify(DEFAULT_MTPROTO_CORE_CONFIG, null, 2)
