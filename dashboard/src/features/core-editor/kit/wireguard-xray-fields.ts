import { scalarMultBase } from '@stablelib/x25519'
import type { Inbound } from '@pasarguard/xray-config-kit'

/** Backend WireGuard MTU range (inclusive). */
export const WIREGUARD_MTU_MIN = 576
export const WIREGUARD_MTU_MAX = 9000
/** Xray and the backend use this MTU when `mtu` is absent. */
export const WIREGUARD_DEFAULT_MTU = 1420

export type IpOrCidr = { version: 4 | 6; prefix: number | null }

const IPV4_RE = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/
const IPV6_CHARS_RE = /^[0-9A-Fa-f:.]+$/
const IPV6_GROUP_RE = /^[0-9A-Fa-f]{1,4}$/
const PREFIX_RE = /^(0|[1-9]\d{0,2})$/

function isIpv6Address(value: string): boolean {
  if (!IPV6_CHARS_RE.test(value)) return false
  let text = value
  const lastColon = value.lastIndexOf(':')
  const tail = value.slice(lastColon + 1)
  if (tail.includes('.')) {
    // A dotted IPv4 tail fills the last two 16-bit groups.
    if (!IPV4_RE.test(tail)) return false
    text = `${value.slice(0, lastColon + 1)}0:0`
  }
  const halves = text.split('::')
  if (halves.length > 2) return false
  const groupsOf = (part: string) => (part === '' ? [] : part.split(':'))
  const groups = halves.length === 2 ? [...groupsOf(halves[0]), ...groupsOf(halves[1])] : text.split(':')
  if (!groups.every(group => IPV6_GROUP_RE.test(group))) return false
  return halves.length === 2 ? groups.length <= 7 : groups.length === 8
}

/** Parses an IP or CIDR the way Xray's netip parsing does (no trimming, no leading zeros). */
export function parseIpOrCidr(value: string): IpOrCidr | null {
  const parts = value.split('/')
  if (parts.length > 2) return null
  const [address, prefixText] = parts
  let version: 4 | 6
  if (address.includes(':')) {
    if (!isIpv6Address(address)) return null
    version = 6
  } else {
    if (!IPV4_RE.test(address)) return null
    version = 4
  }
  if (prefixText === undefined) return { version, prefix: null }
  if (!PREFIX_RE.test(prefixText)) return null
  const prefix = Number(prefixText)
  if (prefix > (version === 4 ? 32 : 128)) return null
  return { version, prefix }
}

export function isIpAddress(value: string): boolean {
  return parseIpOrCidr(value)?.prefix === null
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2)
  for (let i = 0; i < bytes.length; i += 1) bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16)
  return bytes
}

function binaryToBytes(binary: string): Uint8Array {
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

/**
 * Accepts 64 hex chars, or 43 base64 chars of one alphabet (standard or URL-safe) plus at most one `=`.
 * Returns the 32 key bytes, or null.
 */
export function parseWireguardKey(value: string): Uint8Array | null {
  const text = value.trim()
  if (/^[0-9a-fA-F]{64}$/.test(text)) return hexToBytes(text)
  const body = text.endsWith('=') ? text.slice(0, -1) : text
  if (!/^[A-Za-z0-9+/]{43}$/.test(body) && !/^[A-Za-z0-9_-]{43}$/.test(body)) return null
  let binary: string
  try {
    binary = atob(`${body.replace(/-/g, '+').replace(/_/g, '/')}=`)
  } catch {
    return null
  }
  return binary.length === 32 ? binaryToBytes(binary) : null
}

/** Standard padded base64 public key for a secret key, or '' when the key does not parse. */
export function deriveWireguardPublicKey(secretKey: string): string {
  // Overlaps utils/wireguard.ts getWireGuardPublicKey (base64 only); that file cannot be edited
  // while the MTProto work is open, so the two are unified later.
  const bytes = parseWireguardKey(secretKey)
  if (!bytes) return ''
  return bytesToBase64(scalarMultBase(bytes))
}

export function parseWireguardMtuInput(raw: string): { ok: true; value: number | undefined } | { ok: false } {
  const text = raw.trim()
  if (text === '') return { ok: true, value: undefined }
  if (!/^\d+$/.test(text)) return { ok: false }
  const value = Number(text)
  if (value < WIREGUARD_MTU_MIN || value > WIREGUARD_MTU_MAX) return { ok: false }
  return { ok: true, value }
}

/** Accepts `1, 2, 3` or `[1, 2, 3]`: exactly 3 integers from 0 to 255. */
export function parseWireguardReservedInput(raw: string): { ok: true; value: number[] | undefined } | { ok: false } {
  let text = raw.trim()
  if (text === '') return { ok: true, value: undefined }
  if (text.startsWith('[')) {
    if (!text.endsWith(']')) return { ok: false }
    text = text.slice(1, -1)
  }
  const parts = text.split(',').map(part => part.trim())
  if (parts.length !== 3) return { ok: false }
  const value: number[] = []
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return { ok: false }
    const byte = Number(part)
    if (byte > 255) return { ok: false }
    value.push(byte)
  }
  return { ok: true, value }
}

const isByte = (item: unknown): item is number => typeof item === 'number' && Number.isInteger(item) && item >= 0 && item <= 255

/** Reads a stored `reserved` value: [] when unset, 3 bytes for a valid list or 4-char base64, null otherwise. */
export function wireguardReservedBytes(value: unknown): number[] | null {
  if (value === undefined || value === null || value === '') return []
  if (Array.isArray(value)) {
    if (value.length === 0) return []
    return value.length === 3 && value.every(isByte) ? [...value] : null
  }
  if (typeof value === 'string' && /^[A-Za-z0-9+/]{4}$/.test(value)) return Array.from(binaryToBytes(atob(value)))
  return null
}

/** Text for the reserved input; values that do not read as bytes are shown as they are stored. */
export function formatWireguardReserved(value: unknown): string {
  const bytes = wireguardReservedBytes(value)
  if (bytes) return bytes.length === 3 ? bytes.join(', ') : ''
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return JSON.stringify(value)
  return ''
}

export function wireguardReservedInputMatches(text: string, value: unknown): boolean {
  const parsed = parseWireguardReservedInput(text)
  if (!parsed.ok) return false
  const stored = wireguardReservedBytes(value)
  if (stored === null) return false
  const typed = parsed.value ?? []
  return typed.length === stored.length && typed.every((byte, i) => byte === stored[i])
}

/** A WireGuard inbound listens on exactly one port: an integer (or decimal string) from 1 to 65535. */
export function parseWireguardInboundPort(raw: unknown): number | null {
  let port: number
  if (typeof raw === 'number') {
    port = raw
  } else if (typeof raw === 'string') {
    const text = raw.trim()
    if (!/^\d+$/.test(text)) return null
    port = Number(text)
  } else {
    return null
  }
  return Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null
}

export function wireguardInboundAddresses(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(item => String(item).trim()).filter(item => item !== '')
}

/**
 * Backend allocatable rule (`xray_wireguard_allocatable_addresses`) plus Xray netip parsing (leading-zero prefixes):
 * a CIDR with IPv4 prefix 30 or less, or IPv6 prefix 126 or less, is allocatable; bare IPs and narrower
 * CIDRs are valid but unmanaged; anything that does not parse is invalid. Input order is kept.
 */
export function classifyWireguardAddresses(addresses: readonly string[]): { allocatable: string[]; unmanaged: string[]; invalid: string[] } {
  const result = { allocatable: [] as string[], unmanaged: [] as string[], invalid: [] as string[] }
  for (const address of addresses) {
    const parsed = parseIpOrCidr(address)
    if (!parsed) result.invalid.push(address)
    else if (parsed.prefix === null || parsed.prefix > (parsed.version === 4 ? 30 : 126)) result.unmanaged.push(address)
    else result.allocatable.push(address)
  }
  return result
}

/**
 * Commits the MTU and reserved texts to a WireGuard inbound. Texts that do not parse leave their key as is;
 * empty texts remove the key. Returns the same object when nothing parses or the inbound is not WireGuard.
 */
export function applyWireguardInboundFormValues(inbound: Inbound, values: { mtu: string; reserved: string }): Inbound {
  if (inbound.protocol !== 'wireguard') return inbound
  const mtu = parseWireguardMtuInput(values.mtu)
  const reserved = parseWireguardReservedInput(values.reserved)
  if (!mtu.ok && !reserved.ok) return inbound
  const next: Record<string, unknown> = { ...inbound }
  if (mtu.ok) {
    if (mtu.value === undefined) delete next.mtu
    else next.mtu = mtu.value
  }
  if (reserved.ok) {
    if (reserved.value === undefined) delete next.reserved
    else next.reserved = reserved.value
  }
  return next as unknown as Inbound
}

/**
 * Commit step for a WireGuard inbound: `applyWireguardInboundFormValues`, plus the trimmed secret key, the port number
 * when the port parses, and address entries trimmed with blank ones dropped. Other inbounds are returned as they are.
 */
export function normalizeWireguardInboundForCommit(inbound: Inbound, values: { mtu: string; reserved: string }): Inbound {
  if (inbound.protocol !== 'wireguard') return inbound
  const next: Record<string, unknown> = { ...applyWireguardInboundFormValues(inbound, values) }
  if (typeof next.secretKey === 'string') next.secretKey = next.secretKey.trim()
  const port = parseWireguardInboundPort(next.port)
  if (port !== null) next.port = port
  if (Array.isArray(next.address)) next.address = wireguardInboundAddresses(next.address)
  return next as unknown as Inbound
}

/**
 * MTU and reserved form texts for an inbound ('' for other protocols). Without `current` they show the stored values.
 * With `current` (the same dialog stays open), a typed text is kept when it does not parse, so its error stays and
 * commit stays blocked, or when it parses to the stored value, so typing is not reformatted; a text that parses to
 * another value gives way to the stored one.
 */
export function wireguardInboundFormTexts(inbound: Inbound, current?: { mtu: string; reserved: string }): { mtu: string; reserved: string } {
  if (inbound.protocol !== 'wireguard') return { mtu: '', reserved: '' }
  const { mtu, reserved } = inbound as { mtu?: unknown; reserved?: unknown }
  const storedMtu = typeof mtu === 'number' ? mtu : undefined
  const stored = { mtu: storedMtu === undefined ? '' : String(storedMtu), reserved: formatWireguardReserved(reserved) }
  if (!current) return stored
  const typedMtu = parseWireguardMtuInput(current.mtu)
  const typedReservedParses = parseWireguardReservedInput(current.reserved).ok
  return {
    mtu: !typedMtu.ok || typedMtu.value === storedMtu ? current.mtu : stored.mtu,
    reserved: !typedReservedParses || wireguardReservedInputMatches(current.reserved, reserved) ? current.reserved : stored.reserved,
  }
}
