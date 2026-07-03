import { DEFAULT_XRAY_CORE_CONFIG } from '@/lib/default-xray-core-config'
import { checkSessionIdRoomSize } from '@/lib/xray-session-id-room-size'
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
  return stripHysteriaInboundAuth(stripRealityInboundXverForKit(sanitizeProfileInbounds(normalizeProfile(JSON.parse(JSON.stringify(profile)) as Profile))))
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

function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null
}

function realityXverValue(value: unknown): number | undefined {
  const n = typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN
  if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0) return undefined
  return n
}

function inboundSettingString(rawInbound: unknown, key: string): string | undefined {
  const settings = asRecord(asRecord(rawInbound)?.settings)
  const value = settings?.[key]
  return typeof value === 'string' ? value : undefined
}

function patchVlessInboundEncryptionFromRaw(profile: Profile, raw: unknown): Profile {
  if (!isRecord(raw)) return profile
  const rawInbounds = raw.inbounds
  if (!Array.isArray(rawInbounds)) return profile

  const inbounds = profile.inbounds.map((inbound, index) => {
    if (inbound.protocol !== 'vless') return inbound
    const rawInbound = rawInbounds[index]
    const encryption = inboundSettingString(rawInbound, 'encryption')
    if (encryption === undefined) return inbound
    return { ...inbound, encryption } as typeof inbound
  })

  return { ...profile, inbounds }
}

function patchRealityInboundXverFromRaw(profile: Profile, raw: unknown): Profile {
  if (!isRecord(raw)) return profile
  const rawInbounds = raw.inbounds
  if (!Array.isArray(rawInbounds)) return profile

  const inbounds = profile.inbounds.map((inbound, index) => {
    const security = asRecord((inbound as { security?: unknown }).security)
    if (security?.type !== 'reality') return inbound
    const rawInbound = asRecord(rawInbounds[index])
    const streamSettings = asRecord(rawInbound?.streamSettings)
    const realitySettings = asRecord(streamSettings?.realitySettings)
    const xver = realityXverValue(realitySettings?.xver)
    if (xver === undefined) return inbound
    return {
      ...inbound,
      security: {
        ...security,
        xver,
      },
    } as unknown as typeof inbound
  })

  return { ...profile, inbounds }
}

function preserveInboundStreamSettingsFromRaw(profile: Profile, raw: unknown): Profile {
  if (!isRecord(raw)) return profile
  const rawInbounds = raw.inbounds
  if (!Array.isArray(rawInbounds)) return profile

  let changed = false
  const inbounds = profile.inbounds.map((inbound, index) => {
    if (inbound.protocol === 'unmanaged') return inbound
    if ('transport' in inbound && 'security' in inbound) return inbound

    const rawInbound = asRecord(rawInbounds[index])
    const streamSettings = rawInbound?.streamSettings
    if (!isJsonValue(streamSettings)) return inbound

    const currentRaw = Array.isArray((inbound as { raw?: unknown }).raw) ? [...((inbound as { raw?: unknown }).raw as unknown[])] : []
    const hasStreamPatch = currentRaw.some(entry => isRecord(entry) && entry.path === '/streamSettings')
    if (hasStreamPatch) return inbound

    changed = true
    return {
      ...inbound,
      raw: [
        ...currentRaw,
        {
          op: 'add',
          path: '/streamSettings',
          value: streamSettings,
        },
      ],
    } as typeof inbound
  })

  return changed ? { ...profile, inbounds } : profile
}

function preserveInboundSockoptFromRaw(profile: Profile, raw: unknown): Profile {
  if (!isRecord(raw)) return profile
  const rawInbounds = raw.inbounds
  if (!Array.isArray(rawInbounds)) return profile

  let changed = false
  const inbounds = profile.inbounds.map((inbound, index) => {
    if (inbound.protocol === 'unmanaged' || inbound.protocol === 'tun') return inbound

    const rawInbound = asRecord(rawInbounds[index])
    const streamSettings = asRecord(rawInbound?.streamSettings)
    const sockopt = asRecord(streamSettings?.sockopt)
    if (!sockopt || Object.keys(sockopt).length === 0 || !isJsonValue(sockopt)) return inbound

    const streamAdvanced = asRecord((inbound as { streamAdvanced?: unknown }).streamAdvanced)
    const currentSockopt = asRecord(streamAdvanced?.sockopt)
    if (currentSockopt && Object.keys(currentSockopt).length > 0) return inbound

    changed = true
    return {
      ...inbound,
      streamAdvanced: {
        ...(streamAdvanced ?? {}),
        sockopt: JSON.parse(JSON.stringify(sockopt)) as JsonValue,
      },
    } as typeof inbound
  })

  return changed ? { ...profile, inbounds } : profile
}

function stripRealityInboundXverForKit(profile: Profile): Profile {
  const inbounds = profile.inbounds.map(inbound => {
    const security = asRecord((inbound as { security?: unknown }).security)
    if (security?.type !== 'reality' || !Object.prototype.hasOwnProperty.call(security, 'xver')) return inbound
    const { xver: _xver, ...restSecurity } = security
    return { ...inbound, security: restSecurity } as unknown as typeof inbound
  })

  return { ...profile, inbounds }
}

function stripHysteriaInboundAuth(profile: Profile): Profile {
  let changed = false
  const inbounds = profile.inbounds.map(inbound => {
    if (inbound.protocol !== 'hysteria') return inbound

    const transport = asRecord((inbound as { transport?: unknown }).transport)
    const nextTransport = transport ? { ...transport } : undefined
    const hadTransportAuth = Boolean(nextTransport && Object.prototype.hasOwnProperty.call(nextTransport, 'auth'))
    if (nextTransport) delete nextTransport.auth

    const clients = Array.isArray((inbound as { clients?: unknown }).clients) ? ((inbound as { clients?: unknown[] }).clients ?? []) : []
    const hasClients = clients.length > 0
    if (!hadTransportAuth && !hasClients) return inbound

    changed = true
    return {
      ...inbound,
      clients: [],
      ...(nextTransport ? { transport: nextTransport } : {}),
    } as typeof inbound
  })

  return changed ? { ...profile, inbounds } : profile
}

function applyVlessInboundEncryptionToCompiledConfig(profile: Profile, config: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(config.inbounds)) return config
  const inbounds = config.inbounds.map((compiledInbound, index) => {
    if (!isRecord(compiledInbound) || compiledInbound.protocol !== 'vless') return compiledInbound
    const profileInbound = profile.inbounds?.[index]
    if (profileInbound?.protocol !== 'vless') return compiledInbound
    const encryption = typeof profileInbound.encryption === 'string' ? profileInbound.encryption : undefined
    if (encryption === undefined) return compiledInbound
    const normalizedEncryption = encryption.trim()
    if (normalizedEncryption === '' || normalizedEncryption === 'none') return compiledInbound
    const settings = isRecord(compiledInbound.settings) ? { ...compiledInbound.settings } : {}
    settings.encryption = encryption
    return { ...compiledInbound, settings }
  })
  return { ...config, inbounds }
}

/**
 * `xray-config-kit`'s `compileRealityServer` drops `xver`, `fingerprint`, `publicKey`, and `mldsa65Verify`.
 * The importer reads these fields, so without re-applying them after compile, edits made in the panel
 * (e.g. picking a uTLS fingerprint) are silently lost on the next round-trip.
 */
function applyRealityInboundExtrasToCompiledConfig(profile: Profile, config: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(config.inbounds)) return config

  let changed = false
  const inbounds = config.inbounds.map((compiledInbound, index) => {
    if (!isRecord(compiledInbound)) return compiledInbound
    const profileInbound = profile.inbounds?.[index]
    const security = asRecord((profileInbound as { security?: unknown } | undefined)?.security)
    if (security?.type !== 'reality') return compiledInbound

    const xver = realityXverValue(security.xver)
    const fingerprint = typeof security.fingerprint === 'string' && security.fingerprint.trim() !== '' ? security.fingerprint : undefined
    const publicKey = typeof security.publicKey === 'string' && security.publicKey.trim() !== '' ? security.publicKey : undefined
    const mldsa65Verify = typeof security.mldsa65Verify === 'string' && security.mldsa65Verify.trim() !== '' ? security.mldsa65Verify : undefined

    if (xver === undefined && fingerprint === undefined && publicKey === undefined && mldsa65Verify === undefined) {
      return compiledInbound
    }

    const streamSettings = isRecord(compiledInbound.streamSettings) ? { ...compiledInbound.streamSettings } : {}
    const realitySettings = isRecord(streamSettings.realitySettings) ? { ...streamSettings.realitySettings } : {}
    if (xver !== undefined) realitySettings.xver = xver
    if (fingerprint !== undefined) realitySettings.fingerprint = fingerprint
    if (publicKey !== undefined) realitySettings.publicKey = publicKey
    if (mldsa65Verify !== undefined) realitySettings.mldsa65Verify = mldsa65Verify
    streamSettings.realitySettings = realitySettings
    changed = true
    return { ...compiledInbound, streamSettings }
  })

  return changed ? { ...config, inbounds } : config
}

const UNMODELED_TOP_LEVEL_KEYS_TO_PRESERVE = ['policy', 'api', 'stats', 'metrics', 'fakeDns', 'observatory', 'burstObservatory', 'reverse', 'transport', 'geodata', 'version'] as const

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

function applyUnmodeledTopLevelSectionsToCompiledConfig(profile: Profile, config: Record<string, unknown>): Record<string, unknown> {
  const topLevel = profile.raw?.topLevel
  if (!isRecord(topLevel)) return config

  let next: Record<string, unknown> | undefined
  for (const key of UNMODELED_TOP_LEVEL_KEYS_TO_PRESERVE) {
    if (!Object.prototype.hasOwnProperty.call(topLevel, key)) continue
    const value = topLevel[key]
    if (!isJsonValue(value)) continue
    next ??= { ...config }
    next[key] = JSON.parse(JSON.stringify(value)) as JsonValue
  }

  return next ?? config
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

function normalizeHysteriaSettingsForCore(config: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(config.inbounds)) return config

  let changed = false
  const inbounds = config.inbounds.map(compiledInbound => {
    if (!isRecord(compiledInbound)) return compiledInbound
    const streamSettings = isRecord(compiledInbound.streamSettings) ? { ...compiledInbound.streamSettings } : null
    if (!streamSettings || streamSettings.network !== 'hysteria') return compiledInbound

    let inboundChanged = false
    const hysteriaSettings = isRecord(streamSettings.hysteriaSettings) ? { ...streamSettings.hysteriaSettings } : {}
    if (Object.prototype.hasOwnProperty.call(hysteriaSettings, 'auth')) {
      delete hysteriaSettings.auth
      inboundChanged = true
    }
    if (Object.prototype.hasOwnProperty.call(hysteriaSettings, 'ignoreClientBandwidth')) {
      delete hysteriaSettings.ignoreClientBandwidth
      inboundChanged = true
    }
    let udpmasks = Array.isArray(hysteriaSettings.udpmasks) ? hysteriaSettings.udpmasks : undefined
    if (udpmasks) {
      delete hysteriaSettings.udpmasks
      inboundChanged = true
    }
    if (Array.isArray(streamSettings.udpmasks)) {
      udpmasks = streamSettings.udpmasks
      delete streamSettings.udpmasks
      inboundChanged = true
    }
    if (udpmasks && udpmasks.length > 0) {
      const finalmask = isRecord(streamSettings.finalmask) ? { ...streamSettings.finalmask } : {}
      finalmask.udp = udpmasks
      streamSettings.finalmask = finalmask
      inboundChanged = true
    }

    const settings = isRecord(compiledInbound.settings) ? { ...compiledInbound.settings } : {}
    if (Array.isArray(settings.clients) && settings.clients.length > 0) {
      settings.clients = []
      inboundChanged = true
    }
    if (Object.prototype.hasOwnProperty.call(settings, 'auth')) {
      delete settings.auth
      inboundChanged = true
    }

    if (!inboundChanged) return compiledInbound
    streamSettings.hysteriaSettings = hysteriaSettings
    changed = true
    return { ...compiledInbound, settings, streamSettings }
  })

  return changed ? { ...config, inbounds } : config
}

function applyHysteriaTransportUdpmasksToCompiledConfig(profile: Profile, config: Record<string, unknown>): Record<string, unknown> {
  if (!Array.isArray(config.inbounds)) return config

  let changed = false
  const inbounds = config.inbounds.map((compiledInbound, index) => {
    if (!isRecord(compiledInbound)) return compiledInbound
    const profileInbound = profile.inbounds?.[index]
    const transport = asRecord((profileInbound as { transport?: unknown } | undefined)?.transport)
    const udpmasks = transport?.type === 'hysteria' && Array.isArray(transport.udpmasks) ? transport.udpmasks : undefined
    if (!udpmasks || udpmasks.length === 0) return compiledInbound

    const streamSettings = isRecord(compiledInbound.streamSettings) ? { ...compiledInbound.streamSettings } : {}
    const finalmask = isRecord(streamSettings.finalmask) ? { ...streamSettings.finalmask } : {}
    finalmask.udp = udpmasks
    streamSettings.finalmask = finalmask
    changed = true
    return { ...compiledInbound, streamSettings }
  })

  return changed ? { ...config, inbounds } : config
}

/**
 * `sessionIDTable`/`sessionIDLength` (XHTTP transport) survive schema validation on any xray-config-kit
 * version — the field is present, just not semantically checked. Xray-core's own Build() hard-fails when
 * the table/length combination can't produce ~2.1B distinct session IDs, so this is checked here directly
 * rather than relying on the kit (same category as allowInsecure: a Build()-time value check, not a
 * schema fact). Runs over every inbound regardless of how it was edited — typed dialog or raw JSON —
 * since both end up as the same `Profile.inbounds` shape before persist.
 */
function getXhttpSessionIdRoomSizeIssues(profile: Profile): Issue[] {
  const issues: Issue[] = []
  profile.inbounds.forEach((inbound, index) => {
    const transport = 'transport' in inbound ? (inbound.transport as { type?: string; extra?: Record<string, unknown> } | undefined) : undefined
    if (transport?.type !== 'xhttp') return
    const table = transport.extra?.sessionIDTable
    const length = transport.extra?.sessionIDLength
    if (typeof table !== 'string' || typeof length !== 'string' || !table || !length) return
    const problem = checkSessionIdRoomSize(table, length)
    if (!problem) return
    issues.push({
      code: problem === 'length-not-positive' ? 'XCK_XHTTP_SESSION_ID_LENGTH_NOT_POSITIVE' : 'XCK_XHTTP_SESSION_ID_ROOM_TOO_SMALL',
      severity: 'error',
      category: 'semantic',
      path: `/inbounds/${index + 1}/transport/extra/sessionIDLength`,
      message:
        problem === 'length-not-positive'
          ? 'sessionIDLength must be greater than 0.'
          : 'Too few possible session IDs (must be at least ~2.1 billion). Increase the length range or use a larger character table.',
    })
  })
  return issues
}

/**
 * Issues from {@link buildXrayConfig} in strict mode when the profile does not compile (schema / semantic / unsafe patches, …),
 * plus the sessionIDTable/sessionIDLength room-size check (not covered by the kit — see {@link getXhttpSessionIdRoomSizeIssues}).
 */
export function getXrayStrictCompileBlockers(profile: Profile, xrayVersion?: string | null): Issue[] {
  const roomSizeIssues = getXhttpSessionIdRoomSizeIssues(profile)
  const { config, issues } = buildXrayConfig(prepareProfileForKit(profile), { mode: 'strict', xrayVersion: xrayVersion ?? undefined })
  if (!isEmptyCompiledConfig(config)) return roomSizeIssues
  const errors = issues.filter(i => i.severity === 'error')
  return errors.length > 0 ? [...errors, ...roomSizeIssues] : [...issues, ...roomSizeIssues]
}

export type XrayPersistValidationResult = { ok: true; config: Record<string, unknown> } | { ok: false; strictBlockers: Issue[]; coreKitIssues: CoreKitValidationIssue[] }

export function importRawToProfile(raw: unknown): { profile: Profile; issues: Issue[] } {
  const imported = importXrayConfig(raw)
  const normalized = sanitizeProfileInbounds(normalizeProfile(imported.profile))
  const withVlessEncryption = patchVlessInboundEncryptionFromRaw(normalized, raw)
  const withRealityXver = patchRealityInboundXverFromRaw(withVlessEncryption, raw)
  const withInboundSockopt = preserveInboundSockoptFromRaw(withRealityXver, raw)
  const withInboundStreamSettings = preserveInboundStreamSettingsFromRaw(withInboundSockopt, raw)
  const profile = stripHysteriaInboundAuth(
    preserveUnmodeledTopLevelSections(
      withInboundStreamSettings,
      raw,
    ),
  )

  return { profile, issues: [...imported.issues] }
}

export function profileToPersistedConfig(profile: Profile, xrayVersion?: string | null): Record<string, unknown> {
  const prepared = prepareProfileForKit(profile)
  const { config } = buildXrayConfig(prepared, { mode: 'permissive', xrayVersion: xrayVersion ?? undefined })
  const result = normalizeHysteriaSettingsForCore(
    applyHysteriaTransportUdpmasksToCompiledConfig(
      prepared,
      applyRealityInboundExtrasToCompiledConfig(profile, applyVlessInboundEncryptionToCompiledConfig(prepared, applyInboundSockoptToCompiledConfig(prepared, config as Record<string, unknown>))),
    ),
  )

  return applyUnmodeledTopLevelSectionsToCompiledConfig(prepared, result)
}

export function validateProfileForSave(profile: Profile, xrayVersion?: string | null) {
  const config = profileToPersistedConfig(profile, xrayVersion)
  return validateCoreConfig('xray', config, { xrayVersion: xrayVersion ?? undefined })
}

/**
 * Persist validation: strict-mode Xray compile blockers from xray-config-kit plus core-kit checks on permissive JSON
 * (inbound clients noise filtered out). Warnings and info-level issues do not block save.
 */
export function validateProfileForPersist(profile: Profile, xrayVersion?: string | null): XrayPersistValidationResult {
  const strictBlockers = getXrayStrictCompileBlockers(profile, xrayVersion)
  const config = profileToPersistedConfig(profile, xrayVersion)
  const r = validateCoreConfig('xray', config, { xrayVersion: xrayVersion ?? undefined })
  const coreKitIssues = r.ok ? [] : filterCoreKitIssuesHidingInboundClients([...r.issues])

  const blockingStrict = strictBlockers.filter(i => i.severity !== 'warning' && i.severity !== 'info')
  const blockingCoreKit = coreKitIssues.filter(i => i.severity !== 'warning' && i.severity !== 'info')

  if (blockingStrict.length > 0 || blockingCoreKit.length > 0) {
    return { ok: false, strictBlockers: blockingStrict, coreKitIssues: blockingCoreKit }
  }
  return { ok: true, config }
}

export function createNewXrayProfile(): Profile {
  const { profile } = importRawToProfile(DEFAULT_XRAY_CORE_CONFIG)
  return profile
}
