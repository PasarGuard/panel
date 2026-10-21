import { validateInboundDraft, validateOutboundDraft } from '@pasarguard/xray-config-kit'
import type { Inbound, Issue, Outbound } from '@pasarguard/xray-config-kit'

import { normalizedName, outboundStreamTransportName } from '@/features/core-editor/kit/outbound-stream-dynamic'

/** Result of parsing the text of a form input: `ok: false` keeps the text in the input and writes nothing. */
export type ParsedInput<T> = { ok: true; value: T } | { ok: false }

/** One port from 1 to 65535; empty means "not set". */
export function parsePortInput(raw: string): ParsedInput<number | undefined> {
  const text = raw.trim()
  if (text === '') return { ok: true, value: undefined }
  if (!/^\d+$/.test(text)) return { ok: false }
  const port = Number(text)
  return port >= 1 && port <= 65535 ? { ok: true, value: port } : { ok: false }
}

/** A JSON object: not null and not an array. */
export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** A JSON object (never an array or a scalar); with `stringValues` every value must be a string. Empty means "not set". */
export function parseJsonObjectInput(raw: string, options?: { stringValues?: boolean }): ParsedInput<Record<string, unknown> | undefined> {
  const text = raw.trim()
  if (text === '') return { ok: true, value: undefined }
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return { ok: false }
  }
  if (!isPlainObject(value)) return { ok: false }
  if (options?.stringValues && !Object.values(value).every(item => typeof item === 'string')) return { ok: false }
  return { ok: true, value }
}

export function formatJsonObjectInput(value: unknown): string {
  return isPlainObject(value) ? JSON.stringify(value, null, 2) : ''
}

/**
 * Free text written trimmed, with empty meaning "not set". The input keeps the raw text (see `syncTypedText`),
 * so spaces inside a value can be typed: trimming happens here, not on every keystroke.
 */
export function parseTrimmedTextInput(raw: string): ParsedInput<string | undefined> {
  const text = raw.trim()
  return { ok: true, value: text === '' ? undefined : text }
}

export function formatTextInput(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/** The text of a parsed number input (`parsePortInput`, `parseMasqueMtuInput`, `parseXdriveNumberInput`); "not set" is empty. */
export function formatNumberInput(value: number | undefined): string {
  return value === undefined ? '' : String(value)
}

function sameStoredValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
}

/**
 * The text an input should show after the model changed. Text that does not parse, or that parses to the stored
 * value, is what the user is typing and stays; otherwise the stored value was changed elsewhere and is shown.
 */
export function syncTypedText<T>(text: string, stored: T, parse: (raw: string) => ParsedInput<T>, format: (value: T) => string): string {
  const parsed = parse(text)
  if (!parsed.ok) return text
  if (sameStoredValue(parsed.value, stored)) return text
  return format(stored)
}

/** The entries of a list as trimmed strings (non-strings are stringified), without blanks; anything but an array gives `[]`. */
export function cleanStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map(item => String(item).trim()).filter(item => item !== '')
}

/** A copy of `record` with `key` set, or removed when `value` is `undefined`. */
export function setRecordKey(record: Record<string, unknown>, key: string, value: unknown): Record<string, unknown> {
  const next = { ...record }
  if (value === undefined) delete next[key]
  else next[key] = value
  return next
}

/** A kit issue placed on a MASQUE or XDrive form field (`warp.<key>` for WARP keys, `transport` for the transport name, `''` for the whole proxy). */
export type StreamFieldIssue = { field: string; code: string; severity: 'error' | 'warning' | 'info'; message: string }

const STREAM_ISSUE_CODE_PREFIXES = ['XCK_SEMANTIC_MASQUE_', 'XCK_SEMANTIC_XDRIVE_']
const SCHEMA_ISSUE_CODE = 'XCK_SCHEMA_INVALID_PROFILE'
const TRANSPORT_NAME_KEYS = new Set(['type', 'network', 'method'])
/** MASQUE inbound settings the kit keeps at the top level of the inbound model. */
const MASQUE_INBOUND_TOP_LEVEL_FIELDS = new Set(['mtu', 'address', 'remoteDNS'])

/** JSON pointer segments, decoded (`~1` is `/`, `~0` is `~`). */
function pointerSegments(path: string): string[] {
  if (path === '') return []
  const body = path.startsWith('/') ? path.slice(1) : path
  return body.split('/').map(segment => segment.replace(/~1/g, '/').replace(/~0/g, '~'))
}

function fieldFromSegments(segments: readonly string[]): string {
  const [first, second] = segments
  if (first === undefined) return ''
  if (first === 'warp' && second !== undefined) return `warp.${second}`
  if (TRANSPORT_NAME_KEYS.has(first)) return 'transport'
  return first
}

function toStreamFieldIssue(issue: Issue, field: string): StreamFieldIssue {
  return {
    field,
    code: issue.code,
    severity: issue.severity,
    message: issue.suggestion ? `${issue.message} ${issue.suggestion}` : issue.message,
  }
}

function isStreamIssue(issue: Issue, schemaPathPrefix: string): boolean {
  if (STREAM_ISSUE_CODE_PREFIXES.some(prefix => issue.code.startsWith(prefix))) return true
  return issue.code === SCHEMA_ISSUE_CODE && issue.path.startsWith(schemaPathPrefix)
}

/** A schema issue on the MASQUE inbound's top-level `mtu`, `address` or `remoteDNS` (it hides the kit's semantic checks). */
function isMasqueInboundSchemaIssue(issue: Issue): boolean {
  return issue.code === SCHEMA_ISSUE_CODE && MASQUE_INBOUND_TOP_LEVEL_FIELDS.has(pointerSegments(issue.path)[0] ?? '')
}

/**
 * Kit issues of an inbound draft (`validateInboundDraft`) for the MASQUE and XDrive forms: MASQUE/XDrive semantic
 * issues, schema issues under `/transport/` and schema issues on the top-level `mtu`, `address` and `remoteDNS`,
 * each placed on its field. Other issues are dropped.
 */
export function inboundStreamFieldIssues(issues: readonly Issue[]): StreamFieldIssue[] {
  return issues
    .filter(issue => isStreamIssue(issue, '/transport/') || isMasqueInboundSchemaIssue(issue))
    .map(issue => {
      const segments = pointerSegments(issue.path)
      return toStreamFieldIssue(issue, fieldFromSegments(segments[0] === 'transport' ? segments.slice(1) : segments))
    })
}

/**
 * Kit issues of an outbound draft (`validateOutboundDraft`) for the MASQUE and XDrive forms: MASQUE/XDrive semantic
 * issues and schema issues under `/streamSettings/`, each placed on its field (`settings`, `streamSettings` and the
 * `masqueSettings` / `xdriveSettings` block are skipped). Other issues are dropped.
 */
export function outboundStreamFieldIssues(issues: readonly Issue[]): StreamFieldIssue[] {
  return issues
    .filter(issue => isStreamIssue(issue, '/streamSettings/'))
    .map(issue => {
      const segments = pointerSegments(issue.path)
      let rest = segments
      if (segments[0] === 'streamSettings' && (segments[1] === 'masqueSettings' || segments[1] === 'xdriveSettings')) rest = segments.slice(2)
      else if (segments[0] === 'streamSettings' || segments[0] === 'settings') rest = segments.slice(1)
      return toStreamFieldIssue(issue, fieldFromSegments(rest))
    })
}

/** Issues that block Add/Modify: errors, except on `clients` (the backend manages inbound clients). */
export function blockingStreamFieldIssues(issues: readonly StreamFieldIssue[]): StreamFieldIssue[] {
  return issues.filter(issue => issue.severity === 'error' && issue.field !== 'clients')
}

/** Issue fields the outbound "Stream & Security" accordion shows under its network and security selects. */
const OUTBOUND_STREAM_SELECT_FIELDS = new Set(['transport', 'security'])

/**
 * The blocking issues (`blockingStreamFieldIssues`) the outbound "Stream & Security" accordion shows, so the form can
 * open it: on the xdrive network all of them (the XDrive box sits inside the accordion), otherwise only the messages
 * under its network and security selects (the MASQUE box, outside the accordion, shows the rest).
 */
export function outboundStreamAccordionBlockingIssues(issues: readonly StreamFieldIssue[], protocol: string, network: string): StreamFieldIssue[] {
  const blocking = blockingStreamFieldIssues(issues)
  if (protocol !== 'masque' && normalizedName(network) === 'xdrive') return blocking
  return blocking.filter(issue => OUTBOUND_STREAM_SELECT_FIELDS.has(issue.field))
}

/** A stable key for the set of `field` and `code` pairs in `issues` (order, repeats and messages ignored); `''` for none. */
export function streamIssueSetKey(issues: readonly StreamFieldIssue[]): string {
  return [...new Set(issues.map(issue => `${issue.field} ${issue.code}`))].sort().join('\n')
}

/** Whether the issue set `next` holds an issue `previous` does not (both from `streamIssueSetKey`). */
export function streamIssueSetGained(previous: string, next: string): boolean {
  if (next === '') return false
  const before = new Set(previous === '' ? [] : previous.split('\n'))
  return next.split('\n').some(member => !before.has(member))
}

/** The MASQUE and XDrive forms own a proxy's kit issues for the masque protocol and for a masque or xdrive transport on any protocol. */
function hasStreamForms(protocol: string, transportName: string): boolean {
  return protocol === 'masque' || transportName === 'masque' || transportName === 'xdrive'
}

/**
 * `inboundStreamFieldIssues` of the kit draft check, for inbounds the MASQUE or XDrive forms own; `[]` for every
 * other inbound, whose transport issues stay with the generic form and the save-time check.
 */
export function streamFieldIssuesForInbound(inbound: Inbound): StreamFieldIssue[] {
  if (inbound.protocol === 'unmanaged') return []
  const transport = 'transport' in inbound ? (inbound.transport as { type?: unknown } | undefined) : undefined
  if (!hasStreamForms(inbound.protocol, normalizedName(transport?.type))) return []
  return inboundStreamFieldIssues(validateInboundDraft(inbound))
}

/**
 * `outboundStreamFieldIssues` of the kit draft check, for outbounds the MASQUE or XDrive forms own (the transport is
 * `outboundStreamTransportName`); `[]` for every other outbound, so an issue no form field can fix never blocks
 * Add/Modify.
 */
export function streamFieldIssuesForOutbound(outbound: Outbound): StreamFieldIssue[] {
  if (outbound.protocol === 'unmanaged') return []
  const stream = 'streamSettings' in outbound ? (outbound.streamSettings as Record<string, unknown> | undefined) : undefined
  if (!hasStreamForms(outbound.protocol, outboundStreamTransportName(stream))) return []
  return outboundStreamFieldIssues(validateOutboundDraft(outbound))
}
