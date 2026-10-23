import { MASQUE_LIMITS } from '@pasarguard/xray-config-kit'
import type { Alpn, Security, TlsSecurity } from '@pasarguard/xray-config-kit'

import { isPlainObject } from '@/features/core-editor/kit/stream-form-fields'
import type { ParsedInput } from '@/features/core-editor/kit/stream-form-fields'

/** Settings keys the dedicated MASQUE outbound form owns; the generic settings grid hides them. */
export const MASQUE_OUTBOUND_FORM_KEYS = ['address', 'port', 'remoteDNS'] as const

/**
 * Keys of a masque transport (inbound `transport`, outbound `streamSettings.masqueSettings`) the dedicated MASQUE form
 * owns. The client form edits all of them. The server form edits host, path and headers; for the client-only rest
 * (user, pass, warp, xmux) it shows the kit's issues (warnings, and errors where Xray checks the value on a server
 * too) next to a "Remove client-only settings" action.
 */
export const MASQUE_TRANSPORT_FORM_KEYS = ['host', 'path', 'user', 'pass', 'headers', 'warp', 'xmux'] as const

/** Transport keys only MASQUE clients use. A server ignores them, but Xray still checks them there. */
const MASQUE_CLIENT_ONLY_KEYS = ['user', 'pass', 'warp', 'xmux'] as const

/** Issue fields of the client-only keys, which the server box shows next to its "Remove client-only settings" action. */
export const MASQUE_CLIENT_ONLY_FIELDS = ['user', 'pass', 'warp', 'warp.privateKey', 'warp.publicKey', 'warp.address', 'xmux'] as const

const MASQUE_SERVER_SHOWN_FIELDS: readonly string[] = ['address', 'mtu', 'remoteDNS', 'path', 'host', 'headers', ...MASQUE_CLIENT_ONLY_FIELDS]
// The outbound stream accordion shows `security` and `transport` messages under its own selects.
const MASQUE_CLIENT_ALWAYS_SHOWN_FIELDS: readonly string[] = ['address', 'port', 'remoteDNS', 'path', 'host', 'headers', 'xmux', 'security', 'transport']
const MASQUE_CLIENT_BASIC_FIELDS: readonly string[] = ['user', 'pass']
const MASQUE_CLIENT_WARP_FIELDS: readonly string[] = ['warp', 'warp.privateKey', 'warp.publicKey', 'warp.address']

/**
 * Whether the client box shows the user and password inputs: in Basic mode, and in WARP mode while a user or pass is
 * stored (Xray refuses them together with warp, so the inputs let the admin clear them).
 */
export function masqueClientShowsBasicAuthFields(transport: Record<string, unknown>, authMode: MasqueClientAuthMode): boolean {
  return authMode === 'basic' || (authMode === 'warp' && (isNonEmptyString(transport.user) || isNonEmptyString(transport.pass)))
}

/**
 * Issue fields shown next to their inputs (or by the surrounding form); the MASQUE box lists every other field at its
 * bottom. The client box has WARP inputs only in WARP mode and user and pass inputs only where
 * `masqueClientShowsBasicAuthFields` says so, so issues on keys without an input land at the bottom.
 */
export function masqueShownFields(side: 'server' | 'client', authMode: MasqueClientAuthMode = 'none', transport: Record<string, unknown> = {}): readonly string[] {
  if (side === 'server') return MASQUE_SERVER_SHOWN_FIELDS
  return [...MASQUE_CLIENT_ALWAYS_SHOWN_FIELDS, ...(masqueClientShowsBasicAuthFields(transport, authMode) ? MASQUE_CLIENT_BASIC_FIELDS : []), ...(authMode === 'warp' ? MASQUE_CLIENT_WARP_FIELDS : [])]
}

/** True when a client-only key is set the way the kit flags it on a server: not empty, and `xmux` not `{}`. */
export function hasMasqueClientOnlySettings(transport: Record<string, unknown>): boolean {
  return MASQUE_CLIENT_ONLY_KEYS.some(key => {
    const value = transport[key]
    if (value === undefined || value === null || value === '') return false
    return !(key === 'xmux' && isPlainObject(value) && Object.keys(value).length === 0)
  })
}

/** A copy of a server's masque transport without the client-only keys. */
export function removeMasqueClientOnlySettings(transport: Record<string, unknown>): Record<string, unknown> {
  const next = { ...transport }
  for (const key of MASQUE_CLIENT_ONLY_KEYS) delete next[key]
  return next
}

/** MASQUE `mtu`: 0 (Xray's default) or a whole number in the kit's MTU range; empty means "not set". */
export function parseMasqueMtuInput(raw: string): ParsedInput<number | undefined> {
  const text = raw.trim()
  if (text === '') return { ok: true, value: undefined }
  if (!/^\d+$/.test(text)) return { ok: false }
  const mtu = Number(text)
  return mtu === 0 || (mtu >= MASQUE_LIMITS.minMtu && mtu <= MASQUE_LIMITS.maxMtu) ? { ok: true, value: mtu } : { ok: false }
}

export type MasqueHttpMode = 'both' | 'h3' | 'h2'

/** ALPN entries as Xray reads them: its StringList splits a string on "," without trimming, so "h3, h2" is h3 only. */
function alpnList(alpn: unknown): string[] {
  if (Array.isArray(alpn)) return alpn.map(item => String(item))
  if (typeof alpn === 'string') return alpn.split(',')
  return []
}

/**
 * HTTP versions a TLS `alpn` gives MASQUE. Server (Xray `serverVersions`): HTTP/2 when ALPN has h2, HTTP/3 when it
 * has h3 or lacks h2. Client (Xray `usesHTTP2`): HTTP/2 only when ALPN has h2 and not h3.
 */
export function masqueHttpMode(alpn: unknown, side: 'server' | 'client'): MasqueHttpMode {
  const list = alpnList(alpn)
  if (side === 'client') return list.includes('h2') && !list.includes('h3') ? 'h2' : 'h3'
  const h2 = list.includes('h2')
  const h3 = list.includes('h3') || !h2
  if (h2 && h3) return 'both'
  return h2 ? 'h2' : 'h3'
}

export function masqueAlpnForMode(mode: MasqueHttpMode): Alpn[] {
  if (mode === 'both') return ['h3', 'h2']
  return mode === 'h2' ? ['h2'] : ['h3']
}

/**
 * Security for a MASQUE inbound (MASQUE offers TLS only): a TLS one as it is, else new TLS settings whose `alpn` keeps
 * the HTTP version the select showed without TLS (`masqueHttpMode` of no ALPN), so turning TLS on does not change it.
 */
export function masqueInboundTlsSecurity(security: Security): TlsSecurity {
  if (security.type === 'tls') return security
  return { type: 'tls', serverName: '', alpn: masqueAlpnForMode(masqueHttpMode(undefined, 'server')) }
}

export type MasqueClientAuthMode = 'none' | 'basic' | 'warp'

function isNonEmptyString(value: unknown): boolean {
  return typeof value === 'string' && value !== ''
}

/** WARP when a `warp` object is set, else Basic when `user` or `pass` is set, else none. */
export function masqueClientAuthMode(transport: Record<string, unknown>): MasqueClientAuthMode {
  if (typeof transport.warp === 'object' && transport.warp !== null) return 'warp'
  if (isNonEmptyString(transport.user) || isNonEmptyString(transport.pass)) return 'basic'
  return 'none'
}

/** A copy of the transport with only the keys of `mode`: the other modes' keys are removed, every other key stays. */
export function applyMasqueClientAuthMode(transport: Record<string, unknown>, mode: MasqueClientAuthMode): Record<string, unknown> {
  const next = { ...transport }
  if (mode !== 'basic') {
    delete next.user
    delete next.pass
  }
  if (mode !== 'warp') delete next.warp
  else if (typeof next.warp !== 'object' || next.warp === null) next.warp = { privateKey: '', publicKey: '', address: [] }
  return next
}
