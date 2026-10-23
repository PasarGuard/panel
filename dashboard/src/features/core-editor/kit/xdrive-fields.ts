import { createDefaultInboundForProtocol, XDRIVE_SERVICES } from '@pasarguard/xray-config-kit'
import type { Inbound, XDriveService } from '@pasarguard/xray-config-kit'

import type { ParsedInput, StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'

/** The XDrive tuning numbers, in the kit's `XDRIVE_DEFAULTS` order. */
export const XDRIVE_TUNING_FIELDS = ['segmentBytes', 'flushIntervalMs', 'pollIntervalMs', 'maxPollIntervalMs', 'sessionTtlSeconds', 'concurrency', 'eagerWindowMs', 'holeTimeoutMs'] as const

export type XdriveTuningField = (typeof XDRIVE_TUNING_FIELDS)[number]

/** Xray reads the XDrive numbers as uint32. */
export const XDRIVE_UINT32_MAX = 4294967295

/**
 * The two spellings of the Google Drive service: Xray v26.10.17 renamed "Google Drive" to "google-drive" and still
 * reads the old name, which is the only one older releases know. Typed against the kit's service list.
 */
const GOOGLE_DRIVE_SERVICES: ReadonlySet<unknown> = new Set<XDriveService>(['Google Drive', 'google-drive'])

/** The spelling new configs get, like the kit default: XDrive peers on Xray 26.9.30 to 26.10.10 know only this one. */
const NEW_GOOGLE_DRIVE_SERVICE: XDriveService = 'Google Drive'

/** An XDrive number: empty means "not set" (Xray's default); otherwise a whole number 0 to 4294967295. */
export function parseXdriveNumberInput(raw: string): ParsedInput<number | undefined> {
  const text = raw.trim()
  if (text === '') return { ok: true, value: undefined }
  if (!/^\d+$/.test(text)) return { ok: false }
  const value = Number(text)
  return value <= XDRIVE_UINT32_MAX ? { ok: true, value } : { ok: false }
}

/** True for either spelling of the Google Drive service. */
export function isXdriveGoogleDriveService(service: unknown): boolean {
  return GOOGLE_DRIVE_SERVICES.has(service)
}

/**
 * Service choices for the select: one Google Drive item in the stored spelling (else the spelling new configs get),
 * and a stored service the kit does not know first, so the select stays controlled.
 */
export function xdriveServiceSelectOptions(storedService: unknown): string[] {
  const googleDrive = isXdriveGoogleDriveService(storedService) ? (storedService as string) : NEW_GOOGLE_DRIVE_SERVICE
  const options: string[] = []
  for (const service of XDRIVE_SERVICES) {
    const option = isXdriveGoogleDriveService(service) ? googleDrive : service
    if (!options.includes(option)) options.push(option)
  }
  if (typeof storedService === 'string' && storedService !== '' && !(XDRIVE_SERVICES as readonly string[]).includes(storedService)) return [storedService, ...options]
  return options
}

/** The three Google Drive secrets (ClientID, ClientSecret, RefreshToken): non-strings read as `''`, padded to three. */
export function xdriveGoogleDriveSecrets(settings: Record<string, unknown>): [string, string, string] {
  const list = Array.isArray(settings.secrets) ? settings.secrets : []
  const entry = (index: number): string => {
    const value: unknown = list[index]
    return typeof value === 'string' ? value : ''
  }
  return [entry(0), entry(1), entry(2)]
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

/**
 * A copy of the XDrive settings for `service`, keeping `remoteFolder` and every other key, and dropping what the
 * service does not read: `local` drops `secrets` and `template`; Google Drive drops `template` and keeps exactly three
 * secrets; `template` keeps a `secrets` list only when it holds strings. Both Google Drive spellings are one service,
 * so a stored spelling stays.
 */
export function applyXdriveService(settings: Record<string, unknown>, service: XDriveService): Record<string, unknown> {
  const next = { ...settings }
  if (isXdriveGoogleDriveService(service)) {
    next.service = isXdriveGoogleDriveService(settings.service) ? settings.service : service
    delete next.template
    next.secrets = xdriveGoogleDriveSecrets(settings)
    return next
  }
  next.service = service
  if (service === 'local') {
    delete next.secrets
    delete next.template
  } else if (!isStringArray(next.secrets)) {
    delete next.secrets
  }
  return next
}

/**
 * A copy with Google Drive secret `index` set to the trimmed `value`, and the list cut or padded to three entries.
 * `undefined` (an empty input read by `parseTrimmedTextInput`) writes `''`.
 */
export function setXdriveGoogleDriveSecret(settings: Record<string, unknown>, index: 0 | 1 | 2, value: string | undefined): Record<string, unknown> {
  const secrets = xdriveGoogleDriveSecrets(settings)
  secrets[index] = (value ?? '').trim()
  return { ...settings, secrets }
}

/** The kit's default XDrive transport without its `type` key (outbound `xdriveSettings`), a fresh object each call. */
export function defaultXdriveSettings(): Record<string, unknown> {
  const inbound = createDefaultInboundForProtocol({ protocol: 'vless', transport: 'xdrive', clientDefaults: 'empty' })
  const settings: Record<string, unknown> = 'transport' in inbound ? { ...(inbound.transport as Record<string, unknown>) } : {}
  delete settings.type
  return settings
}

/**
 * `issues` plus the panel's own XDrive flow check on a VLESS inbound: panel users take the inbound-level `flow` and
 * Xray refuses flow on xdrive, so a non-blank inbound flow blocks even without clients (the kit flags it only through a
 * client that inherits it). Adds nothing when an issue already sits on `flow`.
 */
export function withXdriveInboundFlowIssue(issues: readonly StreamFieldIssue[], inbound: Inbound, message: string): StreamFieldIssue[] {
  if (inbound.protocol !== 'vless' || inbound.transport.type !== 'xdrive') return [...issues]
  const flow: unknown = inbound.flow
  if (typeof flow !== 'string' || flow.trim() === '' || issues.some(issue => issue.field === 'flow')) return [...issues]
  return [...issues, { field: 'flow', code: 'XCK_SEMANTIC_XDRIVE_VLESS_FLOW', severity: 'error', message }]
}

/**
 * Flow values a VLESS Flow select (inbound or outbound) offers besides Default. On the xdrive transport none (Xray
 * v26.10.17 refuses flow there on both sides), except a stored non-blank flow, which stays selectable so the select
 * shows it next to its error until Default is picked. On any other transport, `allowed` (what the transport and
 * security permit).
 */
export function vlessFlowSelectValues(transport: string, storedFlow: string, allowed: readonly string[]): string[] {
  if (!isXdriveTransport(transport)) return [...allowed]
  return storedFlow.trim() === '' ? [] : [storedFlow]
}

/**
 * Whether a VLESS Flow select shows its hint that Vision needs another transport or security: only when Vision is not
 * `allowed` and the transport is not xdrive, which offers no flow at all (a stored flow gets its own error there).
 */
export function vlessVisionFlowHintShown(transport: string, allowed: boolean): boolean {
  return !allowed && !isXdriveTransport(transport)
}

function isXdriveTransport(transport: string): boolean {
  return transport.trim().toLowerCase() === 'xdrive'
}
