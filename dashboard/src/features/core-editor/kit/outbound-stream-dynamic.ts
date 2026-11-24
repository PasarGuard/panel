import { canonicalizeInboundTransportType, transportCompatibleWithReality } from '@/features/core-editor/kit/inbound-form-options'
import { defaultXdriveSettings } from '@/features/core-editor/kit/xdrive-fields'

/**
 * Outbound stream `network` values shown in the editor (`httpupgrade` etc. omitted). `xdrive` is offered for VLESS only
 * (Xray v26.10.17); `masque` belongs to the masque protocol and is never offered here.
 */
export const OUTBOUND_STREAM_ALL_NETWORKS = ['tcp', 'kcp', 'ws', 'h2', 'grpc', 'xhttp', 'splithttp', 'xdrive'] as const

/** XTLS Vision-style `settings.flow` values (require TLS or REALITY on the stream). */
export const VLESS_VISION_FLOW_VALUES = ['xtls-rprx-vision', 'xtls-rprx-vision-udp443'] as const

type OutboundStreamSecurity = 'none' | 'tls' | 'reality'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** A string trimmed and lowercased (stream network, transport and security names); `''` for anything else. */
export function normalizedName(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

/**
 * Outbound `streamSettings.network` uses the same names as inbound transports (plus kit aliases).
 * REALITY is only valid with the same transports as inbound VLESS/TROJAN (see `transportCompatibleWithReality`).
 */
export function outboundStreamNetworkCompatibleWithReality(network: string | undefined): boolean {
  const raw =
    String(network ?? 'tcp')
      .trim()
      .toLowerCase() || 'tcp'
  const mapped = canonicalizeInboundTransportType(raw)
  if (mapped) return transportCompatibleWithReality(mapped)
  return false
}

/** Vision / XTLS-rprx flows need a TLS or REALITY stream, not `security: none`. */
export function outboundVlessVisionFlowAllowed(streamSecurity: string | undefined): boolean {
  const s = String(streamSecurity ?? 'none')
    .trim()
    .toLowerCase()
  return s === 'tls' || s === 'reality'
}

export function vlessVisionFlowIncompatibleWithStreamSecurity(streamSecurity: string | undefined, flow: string | undefined): boolean {
  const f = String(flow ?? '').trim()
  if (!f) return false
  if (!(VLESS_VISION_FLOW_VALUES as readonly string[]).includes(f)) return false
  return !outboundVlessVisionFlowAllowed(streamSecurity)
}

/**
 * The stream's transport name, trimmed and lowercased: `method` when it is a string (Xray reads `method` first, even
 * an empty one), else `network` when it is a string, else `''`.
 */
export function outboundStreamTransportName(stream: Record<string, unknown> | null | undefined): string {
  if (typeof stream?.method === 'string') return normalizedName(stream.method)
  return normalizedName(stream?.network)
}

/**
 * Network choices for an outbound stream. The masque protocol gets only `masque`; other protocols get
 * `OUTBOUND_STREAM_ALL_NETWORKS`, without `xdrive` unless the protocol is VLESS (Xray v26.10.17), and only the REALITY
 * transports under REALITY. A stored network outside the list stays first, so the Select stays controlled and shows
 * the real value until the user changes it.
 */
export function getOutboundStreamNetworkSelectValues(streamSecurity: string, currentNetwork: string, protocol?: string): string[] {
  const cur = currentNetwork.trim().toLowerCase() || 'tcp'
  let base: string[]
  if (protocol === 'masque') {
    base = ['masque']
  } else {
    base = OUTBOUND_STREAM_ALL_NETWORKS.filter(network => network !== 'xdrive' || protocol === 'vless')
    if (normalizedName(streamSecurity) === 'reality') base = base.filter(network => outboundStreamNetworkCompatibleWithReality(network))
  }
  return base.includes(cur) ? base : [cur, ...base]
}

/**
 * The network whose settings blocks the outbound editor shows for a network select value: Xray's `raw` is its current
 * name for `tcp`, so a stored `raw` keeps the TCP blocks. Every other name is used as stored.
 */
export function outboundStreamSectionNetwork(network: string): string {
  return network === 'raw' ? 'tcp' : network
}

/** Security choices for an outbound stream: TLS only for MASQUE; a stored value outside the list stays first. */
export function getOutboundStreamSecuritySelectValues(protocol: string, currentSecurity: OutboundStreamSecurity): OutboundStreamSecurity[] {
  const base: OutboundStreamSecurity[] = protocol === 'masque' ? ['tls'] : ['none', 'tls', 'reality']
  return base.includes(currentSecurity) ? base : [currentSecurity, ...base]
}

/**
 * A copy of the stream with its transport set to `network`, under the key in use (`method` when it is a string, else
 * `network`). Entering `xdrive` seeds the kit's default `xdriveSettings` unless a record is stored; any other network
 * drops `xdriveSettings`, and any network but `masque` drops `masqueSettings` (the kit, like Xray, checks every
 * present block).
 */
export function applyOutboundStreamNetwork(stream: Record<string, unknown>, network: string): Record<string, unknown> {
  const next = { ...stream }
  next[typeof stream.method === 'string' ? 'method' : 'network'] = network
  const name = normalizedName(network)
  if (name === 'xdrive') {
    if (!isRecord(next.xdriveSettings)) next.xdriveSettings = defaultXdriveSettings()
  } else {
    delete next.xdriveSettings
  }
  if (name !== 'masque') delete next.masqueSettings
  return next
}

/**
 * The mux an outbound needs on the xdrive network: Xray v26.10.17 runs every XDrive connection over Mux.Cool, so mux
 * is enabled, stored fields stay, and the values Xray refuses there (a negative `concurrency` or `xudpConcurrency`,
 * `xudpProxyUDP443: "skip"`) are dropped.
 */
function muxForXdrive(mux: unknown): Record<string, unknown> {
  const next: Record<string, unknown> = isRecord(mux) ? { ...mux } : {}
  for (const key of ['concurrency', 'xudpConcurrency']) {
    const value = next[key]
    if (typeof value === 'number' && value < 0) delete next[key]
  }
  if (next.xudpProxyUDP443 === 'skip') delete next.xudpProxyUDP443
  return { ...next, enabled: true }
}

/**
 * A copy of the outbound with its stream network set by `applyOutboundStreamNetwork`. Entering `xdrive` also enables
 * mux (see `muxForXdrive`); other networks leave `mux` as it is (absent stays absent).
 */
export function outboundWithStreamNetwork(outbound: Record<string, unknown>, network: string): Record<string, unknown> {
  const stream = isRecord(outbound.streamSettings) ? outbound.streamSettings : {}
  const next: Record<string, unknown> = { ...outbound, streamSettings: applyOutboundStreamNetwork(stream, network) }
  if (normalizedName(network) === 'xdrive') next.mux = muxForXdrive(outbound.mux)
  return next
}

/** A copy of TLS settings without `alpn`, or `undefined` when nothing else is left. */
function tlsSettingsWithoutAlpn(tls: Record<string, unknown>): Record<string, unknown> | undefined {
  const next = { ...tls }
  delete next.alpn
  return Object.keys(next).length > 0 ? next : undefined
}

/**
 * Stream settings for an outbound switching to `nextProtocol`. To MASQUE: `{ network: 'masque', security: 'tls' }`,
 * plus the old TLS settings without `alpn` (only from a TLS stream, and only when something is left), `sockopt` and
 * `finalmask`. From a MASQUE stream (or one with `masqueSettings`) to another protocol: a copy without `network`,
 * `method` and `masqueSettings`, or `undefined` when nothing is left. Switching XDrive to a non-VLESS protocol also
 * drops its transport name and `xdriveSettings`. A MASQUE stream also loses its TLS `alpn` (the MASQUE HTTP version),
 * and its TLS settings when nothing else is left in them. Anything else is returned as it is.
 */
export function outboundStreamSettingsForProtocolSwitch(stream: Record<string, unknown> | undefined, nextProtocol: string): Record<string, unknown> | undefined {
  if (nextProtocol === 'masque') {
    const next: Record<string, unknown> = { network: 'masque', security: 'tls' }
    if (normalizedName(stream?.security) === 'tls' && isRecord(stream?.tlsSettings)) {
      const tls = tlsSettingsWithoutAlpn(stream.tlsSettings)
      if (tls) next.tlsSettings = tls
    }
    if (isRecord(stream?.sockopt)) next.sockopt = stream.sockopt
    if (isRecord(stream?.finalmask)) next.finalmask = stream.finalmask
    return next
  }
  if (!stream) return stream
  const fromMasque = outboundStreamTransportName(stream) === 'masque'
  const fromXdrive = nextProtocol !== 'vless' && (outboundStreamTransportName(stream) === 'xdrive' || 'xdriveSettings' in stream)
  if (!fromMasque && !('masqueSettings' in stream) && !fromXdrive) return stream
  const next = { ...stream }
  delete next.network
  delete next.method
  delete next.masqueSettings
  delete next.xdriveSettings
  if (fromMasque && isRecord(next.tlsSettings)) {
    const tls = tlsSettingsWithoutAlpn(next.tlsSettings)
    if (tls) next.tlsSettings = tls
    else delete next.tlsSettings
  }
  return Object.keys(next).length > 0 ? next : undefined
}

/**
 * The mux an outbound keeps when switching to `nextProtocol`: none for MASQUE, else `mux`. Dropping it is a safe
 * default, since Xray v26.10.10 and older refuse mux on MASQUE outbounds; v26.10.17 accepts it, so a MASQUE outbound
 * that already has mux keeps it and gets the kit's warning.
 */
export function outboundMuxForProtocolSwitch(mux: unknown, nextProtocol: string): unknown {
  return nextProtocol === 'masque' ? undefined : mux
}
