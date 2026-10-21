import { isIpAddress, parseWireguardReservedInput, wireguardReservedBytes } from '@/features/core-editor/kit/wireguard-xray-fields'

/** Outbound settings that newer Xray no longer reads: the last release that reads each one, and the first that does not. */
export const WIREGUARD_OUTBOUND_LEGACY_FIELDS = {
  workers: { lastRelease: 'v26.6.1', removedIn: 'v26.6.22' },
  domainStrategy: { lastRelease: 'v26.9.9', removedIn: 'v26.9.30' },
} as const

/** Settings keys the dedicated WireGuard outbound form owns; the generic settings grid hides them. */
export const WIREGUARD_OUTBOUND_FORM_KEYS = ['secretKey', 'address', 'peers', 'mtu', 'workers', 'reserved', 'domainStrategy', 'DNS', 'remoteDNS', 'kernelMode', 'noKernelTun'] as const

export type WireguardKernelTunChoice = '__default__' | 'kernel' | 'userspace'

/** A boolean `noKernelTun` decides; otherwise a boolean legacy `kernelMode` does; otherwise Xray's default. */
export function wireguardKernelTunChoice(settings: Record<string, unknown>): WireguardKernelTunChoice {
  if (typeof settings.noKernelTun === 'boolean') return settings.noKernelTun ? 'userspace' : 'kernel'
  if (typeof settings.kernelMode === 'boolean') return settings.kernelMode ? 'kernel' : 'userspace'
  return '__default__'
}

/** Writes the choice as `noKernelTun` (Default removes it) and drops the legacy `kernelMode`. */
export function applyWireguardKernelTunChoice(settings: Record<string, unknown>, choice: WireguardKernelTunChoice): Record<string, unknown> {
  const next = { ...settings }
  delete next.kernelMode
  if (choice === '__default__') delete next.noKernelTun
  else next.noKernelTun = choice === 'userspace'
  return next
}

/**
 * Xray no longer reads `kernelMode`: a boolean one becomes `noKernelTun: !kernelMode` unless `noKernelTun`
 * is already a boolean, and `kernelMode` is removed. Returns the same object when `kernelMode` is absent.
 */
export function migrateWireguardOutboundLegacySettings(settings: Record<string, unknown>): Record<string, unknown> {
  if (!('kernelMode' in settings)) return settings
  const { kernelMode, ...next } = settings
  if (typeof next.noKernelTun !== 'boolean' && typeof kernelMode === 'boolean') next.noKernelTun = !kernelMode
  return next
}

/**
 * Applies the typed Reserved text: a valid list is written as bytes and empty text removes the key. Text that
 * does not parse is written as is, so `wireguardOutboundSettingsIssues` blocks Modify instead of the previous
 * value being saved, and the text survives edits to other fields.
 */
export function applyWireguardOutboundReservedInput(settings: Record<string, unknown>, text: string): Record<string, unknown> {
  const next = { ...settings }
  const parsed = parseWireguardReservedInput(text)
  if (!parsed.ok) next.reserved = text
  else if (parsed.value === undefined) delete next.reserved
  else next.reserved = parsed.value
  return next
}

const shownDnsValue = (item: unknown): string => JSON.stringify(item)

/**
 * Xray v26.9.9 accepts exactly `["local"]`; v26.9.30 removed that special case and panics on it at startup.
 * Only a known target version before v26.9.30 keeps it (releases before v26.9.8 do not read `remoteDNS`); an
 * unknown one counts as the newest Xray, since the editor cannot tell which release a node runs. Other entries
 * must be IP literals: Xray passes them untrimmed to `netip.MustParseAddr`. Show invalid values as JSON so
 * padded and empty strings remain visible. A non-list value fails Xray's `[]string` decoding.
 */
export function invalidWireguardRemoteDns(value: unknown, xrayVersion?: string): string[] {
  if (value === undefined || value === null) return []
  if (!Array.isArray(value)) return [shownDnsValue(value)]
  const version = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(xrayVersion ?? '')
  const [major, minor, patch] = version ? version.slice(1).map(Number) : []
  const localRemoved = version === null || major > 26 || (major === 26 && (minor > 9 || (minor === 9 && patch >= 30)))
  if (value.length === 1 && value[0] === 'local' && !localRemoved) return []
  return value.filter(item => typeof item !== 'string' || !isIpAddress(item)).map(shownDnsValue)
}

/** `notList` marks a `remoteDNS` that is set but is not a list (Xray reads it as `[]string`). */
export type WireguardOutboundIssue = { field: 'remoteDNS'; values: string[]; notList: boolean } | { field: 'reserved' }

/** Settings values that would make Xray fail to load or start the WireGuard outbound. */
export function wireguardOutboundSettingsIssues(settings: Record<string, unknown>, xrayVersion?: string): WireguardOutboundIssue[] {
  const issues: WireguardOutboundIssue[] = []
  const dns = invalidWireguardRemoteDns(settings.remoteDNS, xrayVersion)
  if (dns.length > 0) issues.push({ field: 'remoteDNS', values: dns, notList: !Array.isArray(settings.remoteDNS) })
  if (wireguardReservedBytes(settings.reserved) === null) issues.push({ field: 'reserved' })
  return issues
}

type Translate = (key: string, options?: Record<string, unknown>) => string

/** The message for one WireGuard outbound issue, shared by the form's inline errors and the Modify validation. */
export function wireguardOutboundIssueMessage(t: Translate, issue: WireguardOutboundIssue): string {
  if (issue.field === 'reserved') {
    return t('coreEditor.outbound.wireguard.reservedInvalid', {
      defaultValue: 'Reserved must be three numbers from 0 to 255, for example 1, 2, 3.',
    })
  }
  if (issue.notList) {
    return t('coreEditor.outbound.wireguard.dnsNotList', {
      defaultValue: 'DNS servers must be a list of IP addresses. Edit the list to save it as one.',
    })
  }
  return t('coreEditor.outbound.wireguard.dnsInvalid', {
    values: issue.values.join(', '),
    defaultValue: 'DNS servers must be IP addresses: {{values}}',
  })
}
