export const DEFAULT_XRAY_CORE_CONFIG: Record<string, unknown> = {
  policy: {
    levels: {
      '0': {
        statsUserOnline: true,
      },
    },
  },
  log: {
    loglevel: 'info',
  },
  inbounds: [
    {
      tag: 'Shadowsocks TCP',
      listen: '0.0.0.0',
      port: 1080,
      protocol: 'shadowsocks',
      settings: {
        clients: [],
        network: 'tcp,udp',
      },
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
  routing: {
    rules: [
      {
        ip: ['geoip:private'],
        outboundTag: 'BLOCK',
        type: 'field',
      },
    ],
  },
}

export const DEFAULT_XRAY_CORE_CONFIG_JSON = JSON.stringify(DEFAULT_XRAY_CORE_CONFIG, null, 2)
