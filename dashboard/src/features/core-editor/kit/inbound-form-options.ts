import type { Inbound, InboundFormCapabilities, Transport } from '@pasarguard/xray-config-kit'

/**
 * Stream transport types the kit models (hysteria is fixed by its protocol). Mainly decides which stored transport
 * stays selectable when the kit's per-protocol list (`transportsByProtocol`) leaves it out;
 * `canonicalizeInboundTransportType` also accepts only these names. The kit builds `masque` only for the masque
 * protocol and `xdrive` only for VLESS. The parity manifest names `websocket`, `mkcp`, `raw` and `splithttp` are
 * aliases, normalized below.
 */
const KIT_MATERIAL_STREAM_TYPES = new Set<Transport['type']>(['tcp', 'grpc', 'xhttp', 'ws', 'httpupgrade', 'kcp', 'xdrive', 'masque'])

/** Parity / docs alias → canonical streamSettings.type used in kit models */
const PARITY_TRANSPORT_TO_CANONICAL: Record<string, Transport['type']> = {
  websocket: 'ws',
  mkcp: 'kcp',
  raw: 'tcp',
  splithttp: 'xhttp',
}

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

/** Protocols whose transport is fixed by the protocol, so the form shows no transport picker. */
const FIXED_TRANSPORT_PROTOCOLS = new Set<Inbound['protocol']>(['unmanaged', 'hysteria', 'masque'])

/** Transports edited by their own form instead of the generic kit transport fields. */
const DEDICATED_FORM_TRANSPORTS = new Set<string>(['hysteria', 'xdrive', 'masque'])

const SELECTABLE_SECURITIES = new Set<string>(['none', 'tls', 'reality'])

function isSelectableSecurity(value: string | undefined): value is 'none' | 'tls' | 'reality' {
  return value !== undefined && SELECTABLE_SECURITIES.has(value)
}

/**
 * Transport choices for an inbound, in kit picker order (`transportsByProtocol` follows the selected Xray release).
 * REALITY keeps only `tcp` / `grpc` / `xhttp`; a stored transport outside the list stays first so the Select stays controlled.
 */
export function getInboundTransportSelectOptions(
  caps: InboundFormCapabilities,
  input: {
    protocol: Inbound['protocol']
    securityType?: 'none' | 'tls' | 'reality'
    currentTransportType?: Transport['type']
  },
): Transport['type'][] {
  if (FIXED_TRANSPORT_PROTOCOLS.has(input.protocol)) return []

  let options = [...(caps.transportsByProtocol[input.protocol] ?? [])]
  if ((input.protocol === 'vless' || input.protocol === 'trojan') && input.securityType === 'reality') {
    options = options.filter(t => REALITY_COMPATIBLE_TRANSPORTS.has(t))
  }

  const cur = input.currentTransportType
  if (cur && !options.includes(cur) && KIT_MATERIAL_STREAM_TYPES.has(cur)) {
    return [cur, ...options]
  }
  return options
}

/** Security choices for an inbound from the kit (`securitiesByProtocol`); a stored value outside the list stays first. */
export function getInboundSecuritySelectOptions(caps: InboundFormCapabilities, protocol: Inbound['protocol'], currentSecurity?: string): Array<'none' | 'tls' | 'reality'> {
  const options = (caps.securitiesByProtocol[protocol] ?? []).filter(isSelectableSecurity)
  if (isSelectableSecurity(currentSecurity) && !options.includes(currentSecurity)) {
    return [currentSecurity, ...options]
  }
  return options
}

/** True for transports that have their own form section instead of the generic kit transport fields. */
export function inboundTransportHasDedicatedForm(type: string | undefined): boolean {
  return type !== undefined && DEDICATED_FORM_TRANSPORTS.has(type)
}

/**
 * For the vmess, vless, trojan and shadowsocks security handler, which rebuilds the inbound with `createDefaultInbound`:
 * false for a stored transport the kit refuses for the protocol (it throws), that is masque on any of them and xdrive
 * outside VLESS, as imported configs can hold. Rebuilding such an inbound passes no transport (the protocol's default)
 * and keeps the stored one, whose kit error the form shows. Other protocols (hysteria, masque) keep their fixed
 * transport and never rebuild it, so their answer is not used.
 */
export function kitBuildsInboundTransport(protocol: Inbound['protocol'], transport: string): boolean {
  if (transport === 'masque') return protocol === 'masque'
  if (transport === 'xdrive') return protocol === 'vless'
  return true
}
