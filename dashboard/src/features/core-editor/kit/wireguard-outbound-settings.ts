import { isIpAddress, wireguardReservedBytes } from '@/features/core-editor/kit/wireguard-xray-fields'

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
 * Returns the `remoteDNS` entries Xray cannot load: list entries are trimmed, empty ones ignored, and each
 * must be an IP literal (Xray parses them with `netip.MustParseAddr`). Xray reads the field as `[]string`,
 * so any other value that is set (for example a single string) is returned whole.
 */
export function invalidWireguardRemoteDns(value: unknown): string[] {
  if (value === undefined || value === null) return []
  if (!Array.isArray(value)) return [typeof value === 'string' ? value.trim() : JSON.stringify(value)]
  return value.map(item => String(item).trim()).filter(item => item !== '' && !isIpAddress(item))
}

export type WireguardOutboundIssue = { field: 'remoteDNS'; values: string[] } | { field: 'reserved' }

/** Settings values that would make Xray fail to load or start the WireGuard outbound. */
export function wireguardOutboundSettingsIssues(settings: Record<string, unknown>): WireguardOutboundIssue[] {
  const issues: WireguardOutboundIssue[] = []
  const dns = invalidWireguardRemoteDns(settings.remoteDNS)
  if (dns.length > 0) issues.push({ field: 'remoteDNS', values: dns })
  if (wireguardReservedBytes(settings.reserved) === null) issues.push({ field: 'reserved' })
  return issues
}
