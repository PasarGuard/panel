import type { Inbound, InboundFormCapabilities, Transport } from '@pasarguard/xray-config-kit'

/**
 * Stream types that xray-config-kit `createDefaultInbound` can build via its internal
 * `defaultTransport`. Parity manifest names extras like `websocket` / `mkcp` / `raw` /
 * `splithttp` that are aliases or not materialized in the kit — we normalize below.
 */
const KIT_MATERIAL_STREAM_TYPES = new Set<Transport['type']>(['tcp', 'grpc', 'xhttp', 'ws', 'httpupgrade', 'kcp'])

/** Parity / docs alias → canonical streamSettings.type used in kit models */
const PARITY_TRANSPORT_TO_CANONICAL: Record<string, Transport['type']> = {
  websocket: 'ws',
  mkcp: 'kcp',
  raw: 'tcp',
  splithttp: 'xhttp',
}

const STREAM_TRANSPORT_LABEL_ORDER: Transport['type'][] = ['tcp', 'grpc', 'xhttp', 'ws', 'httpupgrade', 'kcp']

/** Matches kit REALITY transport validation (tcp / xhttp / grpc only). */
const REALITY_COMPATIBLE_TRANSPORTS = new Set<Transport['type']>(['tcp', 'grpc', 'xhttp'])

export function transportCompatibleWithReality(transport: Transport['type'] | undefined): boolean {
  const t = transport ?? 'tcp'
  return REALITY_COMPATIBLE_TRANSPORTS.has(t)
}

export function canonicalizeInboundTransportType(name: string): Transport['type'] | null {
  const key = name.toLowerCase()
  const mapped = PARITY_TRANSPORT_TO_CANONICAL[key]
  const candidate = (mapped ?? key) as Transport['type']
  return KIT_MATERIAL_STREAM_TYPES.has(candidate) ? candidate : null
}

export function getInboundTransportSelectOptions(
  caps: InboundFormCapabilities,
  input: {
    protocol: Inbound['protocol']
    securityType?: 'none' | 'tls' | 'reality'
    currentTransportType?: Transport['type']
  },
): Transport['type'][] {
  if (input.protocol === 'hysteria' || input.protocol === 'unmanaged') {
    return []
  }

  const fromCaps = new Set<Transport['type']>()
  for (const name of Object.keys(caps.transports)) {
    if (!caps.transports[name]) continue
    const c = canonicalizeInboundTransportType(name)
    if (c) fromCaps.add(c)
  }

  if (
    (input.protocol === 'vless' || input.protocol === 'trojan') &&
    input.securityType === 'reality'
  ) {
    for (const t of [...fromCaps]) {
      if (!REALITY_COMPATIBLE_TRANSPORTS.has(t)) fromCaps.delete(t)
    }
  }

  fromCaps.delete('hysteria')

  let ordered = STREAM_TRANSPORT_LABEL_ORDER.filter(t => fromCaps.has(t))
  if (ordered.length === 0) {
    ordered = [...STREAM_TRANSPORT_LABEL_ORDER]
  }
  const cur = input.currentTransportType
  if (cur && KIT_MATERIAL_STREAM_TYPES.has(cur) && !ordered.includes(cur)) {
    return [cur, ...ordered]
  }
  return ordered
}

export function getInboundSecuritySelectOptions(
  caps: InboundFormCapabilities,
  protocol: Inbound['protocol'],
): Array<'none' | 'tls' | 'reality'> {
  const all = Object.keys(caps.securities).filter((k): k is 'none' | 'tls' | 'reality' =>
    caps.securities[k],
  )
  if (protocol === 'vmess' || protocol === 'shadowsocks' || protocol === 'hysteria') {
    return all.filter(s => s !== 'reality')
  }
  return all
}
