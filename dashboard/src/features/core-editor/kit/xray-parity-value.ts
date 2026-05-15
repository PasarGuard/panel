import type { RoutingBalancer, RoutingRule } from '@pasarguard/xray-config-kit'
import type { XrayGeneratedFormField } from '@pasarguard/xray-config-kit'

export type ParityFieldMode = 'scalar' | 'stringList' | 'json'

/**
 * Removes empty plain objects and string-map keys with empty values so optional
 * JSON fields (e.g. `attrs`) are omitted instead of persisting `{}` or `{"k":""}`.
 * Arrays are left unchanged (no element pruning).
 */
export function deepPruneEmptyJsonObjects(value: unknown): unknown {
  if (value === null || value === undefined) return undefined
  if (typeof value !== 'object') return value
  if (Array.isArray(value)) return value

  const o = value as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(o)) {
    if (v === null || v === undefined) continue
    if (typeof v === 'string' && v.trim() === '') continue

    let pruned: unknown = v
    if (typeof v === 'object' && !Array.isArray(v)) {
      pruned = deepPruneEmptyJsonObjects(v)
    }
    if (pruned === undefined) continue
    if (typeof pruned === 'object' && !Array.isArray(pruned) && Object.keys(pruned as Record<string, unknown>).length === 0) {
      continue
    }
    out[k] = pruned
  }
  if (Object.keys(out).length === 0) return undefined
  return out
}

/** Stringify a record for the JSON object UI; empty after prune becomes `''` so patches omit the key. */
export function stringifyJsonFormRecord(rec: Record<string, unknown>): string {
  const pruned = deepPruneEmptyJsonObjects(rec)
  if (pruned === undefined) return ''
  return JSON.stringify(pruned, null, 2)
}

function isEmptyPlainObject(v: unknown): boolean {
  return typeof v === 'object' && v !== null && !Array.isArray(v) && Object.keys(v as Record<string, unknown>).length === 0
}

/** Map Xray parity Go type string to a coarse editor mode. */
export function inferParityFieldMode(field: XrayGeneratedFormField): ParityFieldMode {
  const t = field.type
  const bare = t.replace(/^\*+/, '')
  if (
    t.includes('json.RawMessage') ||
    t.includes('map[') ||
    t === 'StrategyConfig' ||
    bare === 'XmuxConfig' ||
    bare === 'StreamConfig' ||
    bare === 'Bandwidth' ||
    bare === 'UdpHop' ||
    bare === 'Masquerade' ||
    bare === 'WebhookRuleConfig' ||
    (t.startsWith('[]') && !t.includes('string') && !t.includes('String'))
  ) {
    return 'json'
  }
  if (
    t.includes('StringList') ||
    t.includes('[]string') ||
    t.includes('PortList') ||
    t.includes('NetworkList')
  ) {
    return 'stringList'
  }
  return 'scalar'
}

function normalizeParityFieldKey(field: XrayGeneratedFormField): string {
  return String(field.go || field.json || '')
    .replace(/[^a-zA-Z0-9]/g, '')
    .toLowerCase()
}

/**
 * Scalar parity fields default to one column in the outbound settings grid.
 * Add normalized keys here only when a specific field must span both columns.
 */
const OUTBOUND_SCALAR_FULL_WIDTH_GRID_KEYS = new Set(['testpre'])

export function outboundScalarParityFieldPrefersFullGridWidth(field: XrayGeneratedFormField): boolean {
  if (inferParityFieldMode(field) !== 'scalar') return false
  const key = normalizeParityFieldKey(field)
  return key.length > 0 && OUTBOUND_SCALAR_FULL_WIDTH_GRID_KEYS.has(key)
}

export function routingRuleFieldToString(rule: RoutingRule, jsonKey: string, field: XrayGeneratedFormField): string {
  const mode = inferParityFieldMode(field)
  const v = (rule as Record<string, unknown>)[jsonKey]
  if (v === undefined || v === null) return ''
  if (mode === 'json') {
    if (typeof v === 'string') return v
    if (isEmptyPlainObject(v)) return ''
    try {
      return JSON.stringify(v, null, 2)
    } catch {
      return String(v)
    }
  }
  if (mode === 'stringList') {
    if (Array.isArray(v)) return v.join('\n')
    return String(v)
  }
  if (typeof v === 'object') {
    if (isEmptyPlainObject(v)) return ''
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}

export function parseRoutingRuleFieldValue(
  jsonKey: string,
  field: XrayGeneratedFormField,
  raw: string,
): { value: unknown; clearDomains?: boolean; clearDomain?: boolean } {
  const mode = inferParityFieldMode(field)
  const t = raw.trim()
  if (mode === 'json') {
    if (!t) return { value: undefined }
    const parsed = JSON.parse(t) as unknown
    return { value: deepPruneEmptyJsonObjects(parsed) as unknown }
  }
  if (mode === 'stringList') {
    if (!t) return { value: undefined }
    if (field.type.includes('PortList')) return { value: t }
    const arr = raw
      .split(/[\n,]+/)
      .map(s => s.trim())
      .filter(Boolean)
    if (arr.length === 0) return { value: undefined, clearDomains: jsonKey === 'domain', clearDomain: jsonKey === 'domains' }
    return {
      value: arr,
      clearDomains: jsonKey === 'domain',
      clearDomain: jsonKey === 'domains',
    }
  }
  if (!t) return { value: undefined }
  if (field.type === 'bool') return { value: t === 'true' || t === '1' }
  if (
    field.type.includes('int') ||
    field.type === 'uint16' ||
    field.type === 'byte' ||
    field.type === 'uint64'
  ) {
    const n = Number(t)
    return { value: Number.isFinite(n) ? n : t }
  }
  return { value: t }
}

export function routingBalancerFieldToString(b: RoutingBalancer, jsonKey: string, field: XrayGeneratedFormField): string {
  const mode = inferParityFieldMode(field)
  if (jsonKey === 'tag') return b.tag
  if (jsonKey === 'fallbackTag') return b.fallbackTag ?? ''
  if (jsonKey === 'selector') {
    const v = b.selector
    if (mode === 'stringList') return (v ?? []).join('\n')
    return Array.isArray(v) ? v.join('\n') : String(v ?? '')
  }
  const v = (b as Record<string, unknown>)[jsonKey]
  if (v === undefined || v === null) return ''
  if (mode === 'json') {
    if (isEmptyPlainObject(v)) return ''
    return typeof v === 'string' ? v : JSON.stringify(v, null, 2)
  }
  return String(v)
}

/** TLS `curvePreferences` / ECDHE — only these values are valid in Xray JSON (see Xray TLS docs). */
export const TLS_CURVE_PREFERENCE_OPTIONS = [
  'CurveP256',
  'CurveP384',
  'CurveP521',
  'X25519',
  'X25519MLKEM768',
  'SecP256r1MLKEM768',
  'SecP384r1MLKEM1024',
] as const

function normParityFieldKey(field: XrayGeneratedFormField): string {
  return String(field.json ?? field.go ?? '')
    .replace(/[^a-zA-Z0-9]/g, '')
    .toLowerCase()
}

/** Keep only supported curve names; order is not preserved (caller may re-order). */
export function filterTlsCurvePreferenceStrings(values: readonly string[]): string[] {
  const allowed = new Set<string>(TLS_CURVE_PREFERENCE_OPTIONS as readonly string[])
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of values) {
    const v = String(raw).trim()
    if (!v || seen.has(v)) continue
    if (!allowed.has(v)) continue
    seen.add(v)
    out.push(v)
  }
  return out
}

export function outboundSettingToString(value: unknown, field: XrayGeneratedFormField): string {
  const mode = inferParityFieldMode(field)
  if (value === undefined || value === null) return ''
  if (mode === 'json') {
    if (typeof value === 'string') return value
    if (isEmptyPlainObject(value)) return ''
    return JSON.stringify(value, null, 2)
  }
  if (mode === 'stringList') {
    if (Array.isArray(value)) return (value as unknown[]).map(String).join('\n')
    return String(value)
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function parseOutboundSettingValue(field: XrayGeneratedFormField, raw: string): unknown {
  const mode = inferParityFieldMode(field)
  const t = raw.trim()
  if (mode === 'json') {
    if (!t) return undefined
    const parsed = JSON.parse(t) as unknown
    return deepPruneEmptyJsonObjects(parsed) as unknown
  }
  if (mode === 'stringList') {
    if (!t) return undefined
    const arr = raw
      .split(/[\n,]+/)
      .map(s => s.trim())
      .filter(Boolean)
    if (arr.length === 0) return undefined
    if (normParityFieldKey(field) === 'curvepreferences') {
      const filtered = filterTlsCurvePreferenceStrings(arr)
      return filtered.length > 0 ? filtered : undefined
    }
    return arr
  }
  if (!t) return undefined
  if (field.type === 'bool') return t === 'true' || t === '1'
  if (field.type.includes('int') || field.type === 'uint16' || field.type === 'byte') {
    const n = Number(t)
    return Number.isFinite(n) ? n : t
  }
  return t
}
