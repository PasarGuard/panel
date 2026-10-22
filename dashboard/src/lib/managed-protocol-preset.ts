// Opt-in only: TLS must terminate on a reverse proxy in the same network namespace.
// Clients are provisioned by the panel, never by shared credentials in a template.
export function createManagedProtocolPreset() {
  const protocols = ['vless', 'vmess', 'trojan'] as const
  return {
    log: { loglevel: 'warning' },
    policy: { levels: { '0': { statsUserUplink: true, statsUserDownlink: true, statsUserOnline: true } } },
    inbounds: protocols.map((protocol, index) => ({
      tag: `${protocol.toUpperCase()} WS`,
      listen: '127.0.0.1',
      port: 10001 + index,
      protocol,
      settings: protocol === 'vless' ? { clients: [], decryption: 'none' } : { clients: [] },
      streamSettings: { network: 'ws', security: 'none', wsSettings: { path: `/pasarguard/${protocol}` } },
    })),
    outbounds: [{ tag: 'DIRECT', protocol: 'freedom' }, { tag: 'BLOCK', protocol: 'blackhole' }],
    routing: {
      rules: [{ type: 'field', ip: ['0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16', '224.0.0.0/4', '240.0.0.0/4', '::/128', '::1/128', 'fc00::/7', 'fe80::/10', 'ff00::/8'], outboundTag: 'BLOCK' }],
    },
  }
}
