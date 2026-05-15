import { DEFAULT_XRAY_CORE_CONFIG } from '@/lib/default-xray-core-config'
import { buildXrayConfig, importXrayConfig, normalizeProfile } from '@pasarguard/xray-config-kit'
import type { Issue, JsonValue, Profile } from '@pasarguard/xray-config-kit'
import type { CoreKitValidationIssue } from '@pasarguard/core-kit'
import { validateCoreConfig } from '@pasarguard/core-kit'
import { filterCoreKitIssuesHidingInboundClients } from './inbound-clients-issue-filter'
import { sanitizeProfileInbounds } from './sanitize-inbound'

function isEmptyCompiledConfig(config: unknown): boolean {
  return typeof config === 'object' && config !== null && !Array.isArray(config) && Object.keys(config as object).length === 0
}

function prepareProfileForKit(profile: Profile): Profile {
  return sanitizeProfileInbounds(normalizeProfile(JSON.parse(JSON.stringify(profile)) as Profile))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null) return true
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return true
  if (Array.isArray(value)) return value.every(isJsonValue)
  if (!isRecord(value)) return false
  return Object.values(value).every(v => v === undefined || isJsonValue(v))
}

const UNMODELED_TOP_LEVEL_KEYS_TO_PRESERVE = [
  'policy',
  'api',
  'stats',
  'metrics',
  'fakeDns',
  'observatory',
  'burstObservatory',
  'reverse',
  'transport',
  'geodata',
  'version',
] as const

function preserveUnmodeledTopLevelSections(profile: Profile, raw: unknown): Profile {
  if (!isRecord(raw)) return profile

  const topLevel: Record<string, JsonValue> = { ...(profile.raw?.topLevel ?? {}) }
  let changed = false
  for (const key of UNMODELED_TOP_LEVEL_KEYS_TO_PRESERVE) {
    if (!(key in raw)) continue
    const value = raw[key]
    if (value === undefined || !isJsonValue(value)) continue
    topLevel[key] = value
    changed = true
  }

  if (!changed) return profile
  return {
    ...profile,
    raw: {
      ...(profile.raw ?? {}),
      topLevel,
    },
  } as Profile
}

function applyInboundSockoptToCompiledConfig(profile: Profile, config: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(config.inbounds)) return config
  const inbounds = config.inbounds.map((compiledInbound, index) => {
    if (!isRecord(compiledInbound)) return compiledInbound
    const profileInbound = profile.inbounds?.[index] as { streamAdvanced?: { sockopt?: unknown } } | undefined
    const sockopt = profileInbound?.streamAdvanced?.sockopt
    if (!isRecord(sockopt) || Object.keys(sockopt).length === 0) return compiledInbound
    const streamSettings = isRecord(compiledInbound.streamSettings) ? { ...compiledInbound.streamSettings } : {}
    streamSettings.sockopt = sockopt
    return { ...compiledInbound, streamSettings }
  })
  return { ...config, inbounds }
}

/**
 * Issues from {@link buildXrayConfig} in strict mode when the profile does not compile (schema / semantic / unsafe patches, …).
 */
export function getXrayStrictCompileBlockers(profile: Profile): Issue[] {
  const { config, issues } = buildXrayConfig(prepareProfileForKit(profile), { mode: 'strict' })
  if (!isEmptyCompiledConfig(config)) return []
  const errors = issues.filter(i => i.severity === 'error')
  return errors.length > 0 ? errors : issues
}

export type XrayPersistValidationResult =
  | { ok: true; config: Record<string, unknown> }
  | { ok: false; strictBlockers: Issue[]; coreKitIssues: CoreKitValidationIssue[] }

export function importRawToProfile(raw: unknown): { profile: Profile; issues: Issue[] } {
  const imported = importXrayConfig(raw)
  const profile = preserveUnmodeledTopLevelSections(
    sanitizeProfileInbounds(normalizeProfile(imported.profile)),
    raw,
  )

  return { profile, issues: [...imported.issues] }
}

export function profileToPersistedConfig(profile: Profile): Record<string, unknown> {
  const prepared = prepareProfileForKit(profile)
  const { config } = buildXrayConfig(prepared, { mode: 'permissive' })
  const result = applyInboundSockoptToCompiledConfig(prepared, config as Record<string, unknown>)

  return result
}

export function validateProfileForSave(profile: Profile) {
  const config = profileToPersistedConfig(profile)
  return validateCoreConfig('xray', config)
}

/**
 * Persist validation: strict-mode Xray compile blockers from xray-config-kit plus core-kit checks on permissive JSON
 * (inbound clients noise filtered out).
 */
export function validateProfileForPersist(profile: Profile): XrayPersistValidationResult {
  const strictBlockers = getXrayStrictCompileBlockers(profile)
  const config = profileToPersistedConfig(profile)
  const r = validateCoreConfig('xray', config)
  const coreKitIssues = r.ok ? [] : filterCoreKitIssuesHidingInboundClients([...r.issues])

  if (strictBlockers.length > 0 || coreKitIssues.length > 0) {
    return { ok: false, strictBlockers, coreKitIssues }
  }
  return { ok: true, config }
}

export function createNewXrayProfile(): Profile {
  const { profile } = importRawToProfile(DEFAULT_XRAY_CORE_CONFIG)
  return profile
}
