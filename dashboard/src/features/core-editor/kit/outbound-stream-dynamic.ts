import { canonicalizeInboundTransportType, transportCompatibleWithReality } from '@/features/core-editor/kit/inbound-form-options'

/** Outbound stream `network` values shown in the editor (matches previous UI; `httpupgrade` etc. omitted). */
export const OUTBOUND_STREAM_ALL_NETWORKS = ['tcp', 'kcp', 'ws', 'h2', 'grpc', 'xhttp', 'splithttp'] as const

/** XTLS Vision-style `settings.flow` values (require TLS or REALITY on the stream). */
export const VLESS_VISION_FLOW_VALUES = ['xtls-rprx-vision', 'xtls-rprx-vision-udp443'] as const

/**
 * Outbound `streamSettings.network` uses the same names as inbound transports (plus kit aliases).
 * REALITY is only valid with the same transports as inbound VLESS/TROJAN (see `transportCompatibleWithReality`).
 */
export function outboundStreamNetworkCompatibleWithReality(network: string | undefined): boolean {
  const raw = String(network ?? 'tcp').trim().toLowerCase() || 'tcp'
  const mapped = canonicalizeInboundTransportType(raw)
  if (mapped) return transportCompatibleWithReality(mapped)
  return false
}

/** Vision / XTLS-rprx flows need a TLS or REALITY stream — not `security: none`. */
export function outboundVlessVisionFlowAllowed(streamSecurity: string | undefined): boolean {
  const s = String(streamSecurity ?? 'none').trim().toLowerCase()
  return s === 'tls' || s === 'reality'
}

export function vlessVisionFlowIncompatibleWithStreamSecurity(
  streamSecurity: string | undefined,
  flow: string | undefined,
): boolean {
  const f = String(flow ?? '').trim()
  if (!f) return false
  if (!(VLESS_VISION_FLOW_VALUES as readonly string[]).includes(f)) return false
  return !outboundVlessVisionFlowAllowed(streamSecurity)
}

/**
 * When stream security is REALITY, only list transports that support REALITY (like inbound transport picker).
 * If the current network is invalid but still present in config, keep it first so the Select stays controlled until the user fixes it.
 */
export function getOutboundStreamNetworkSelectValues(streamSecurity: string, currentNetwork: string): string[] {
  const cur = String(currentNetwork || 'tcp').trim().toLowerCase() || 'tcp'
  const all: string[] = [...OUTBOUND_STREAM_ALL_NETWORKS]
  if (String(streamSecurity).trim().toLowerCase() !== 'reality') return all
  const ok: string[] = all.filter(n => outboundStreamNetworkCompatibleWithReality(n))
  if (ok.includes(cur)) return ok
  return [cur, ...ok]
}
