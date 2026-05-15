import type { Outbound } from '@pasarguard/xray-config-kit'
import { deepPruneEmptyJsonObjects } from '@/features/core-editor/kit/xray-parity-value'

/** Deep-prune empty objects; use for `streamSettings`, `mux`, `proxySettings`, etc. (avoid `{}` in JSON / profile). Preserves sockopt even if empty. */
export function normalizeOutboundStreamSettings(value: unknown): unknown {
  if (value === undefined || value === null) return undefined
  if (typeof value !== 'object' || Array.isArray(value)) return value
  
  const obj = value as Record<string, unknown>
  const sockopt = obj.sockopt
  const pruned = deepPruneEmptyJsonObjects(obj)
  
  // If sockopt existed in the original, preserve it even if empty
  if (sockopt !== undefined && sockopt !== null && typeof sockopt === 'object' && !Array.isArray(sockopt)) {
    if (pruned && typeof pruned === 'object' && !Array.isArray(pruned)) {
      const prunedObj = pruned as Record<string, unknown>
      prunedObj.sockopt = sockopt
    } else {
      return { sockopt }
    }
  }
  
  return pruned
}

export function stripEmptyStreamSettingsFromRecord<T extends Record<string, unknown>>(o: T): T {
  const ss = normalizeOutboundStreamSettings(o.streamSettings)
  if (ss === undefined) {
    if (!('streamSettings' in o)) return o
    const { streamSettings: _removed, ...rest } = o
    return rest as T
  }
  return { ...o, streamSettings: ss } as T
}

/**
 * Remove meaningless outbound envelope keys: `createDefaultOutbound` always spreads
 * `mux` / `proxySettings` / `streamSettings` / `targetStrategy` even when `undefined`,
 * which keeps `'mux' in ob` true and leaves accordions visible.
 */
export function stripSparseOutboundEnvelope<T extends Record<string, unknown>>(o: T): T {
  const next: Record<string, unknown> = { ...o }
  for (const key of ['mux', 'proxySettings'] as const) {
    if (!(key in next)) continue
    const raw = next[key]
    if (raw === undefined) {
      delete next[key]
      continue
    }
    const pruned = normalizeOutboundStreamSettings(raw)
    if (pruned === undefined) delete next[key]
    else next[key] = pruned
  }
  if ('targetStrategy' in next && next.targetStrategy === undefined) delete next.targetStrategy
  if ('sendThrough' in next) {
    const st = next.sendThrough
    if (st === undefined || st === null || String(st).trim() === '') delete next.sendThrough
  }
  return stripEmptyStreamSettingsFromRecord(next) as T
}

function compactSettingsUser(user: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(user)) {
    if (v === undefined || v === null) continue
    if (v === '') continue
    const pruned =
      typeof v === 'object' && v !== null && !Array.isArray(v) ? deepPruneEmptyJsonObjects(v) : v
    if (pruned === undefined) continue
    out[k] = pruned
  }
  return out
}

function flattenVnextLike(
  settings: Record<string, unknown>,
  protocol: 'vless' | 'vmess',
): Record<string, unknown> {
  const vnext = settings.vnext as
    | Array<{ address?: string; port?: number; users?: Array<Record<string, unknown>> }>
    | undefined
  if (!vnext?.[0]) return { ...settings }
  const ep = vnext[0]
  const u = ep.users?.[0] ?? {}
  const next: Record<string, unknown> = { ...settings }
  delete next.vnext
  next.address = ep.address
  next.port = ep.port
  if (protocol === 'vless') {
    next.id = u.id
    next.flow = u.flow != null && u.flow !== '' ? u.flow : ''
    next.encryption = u.encryption
  } else {
    next.id = u.id
    next.security = u.security
    next.alterId = u.alterId
  }
  if (u.level !== undefined) next.level = u.level
  if (u.email !== undefined) next.email = u.email
  if (protocol === 'vmess' && u.experiments !== undefined) next.experiments = u.experiments
  return next
}

function flattenServersLike(settings: Record<string, unknown>, protocol: 'trojan' | 'shadowsocks'): Record<string, unknown> {
  const servers = settings.servers as Array<Record<string, unknown>> | undefined
  if (!servers?.[0]) return { ...settings }
  const s = servers[0]
  const next: Record<string, unknown> = { ...settings }
  delete next.servers
  for (const k of [
    'address',
    'port',
    'password',
    'method',
    'flow',
    'level',
    'email',
    'uot',
    'uotVersion',
  ] as const) {
    if (s[k] !== undefined) next[k] = s[k]
  }
  if (protocol === 'shadowsocks' && s.ivCheck !== undefined) next.ivCheck = s.ivCheck
  return next
}

/** Flatten `vnext` / `servers` into scalar fields for form editing (matches JSON tab body shape). */
export function flattenOutboundSettings(ob: Outbound): Record<string, unknown> {
  if (ob.protocol === 'unmanaged') return {}
  const raw = ((ob as { settings?: Record<string, unknown> }).settings ?? {}) as Record<string, unknown>
  const p = ob.protocol
  if (p === 'vless' || p === 'vmess') return flattenVnextLike(raw, p)
  if (p === 'trojan' || p === 'shadowsocks') return flattenServersLike(raw, p)
  return { ...raw }
}

/** Xray Hysteria outbound is v2-only; `version: 2` is implied — omit from saved JSON / editor body. */
export function stripHysteriaOutboundRedundantVersion(settings: Record<string, unknown>): Record<string, unknown> {
  if (settings.version !== 2 && settings.version !== '2') return settings
  const { version: _removed, ...rest } = settings
  return rest
}

/** Map mistaken `rewrite*` keys (older UI) onto Xray `DNSOutboundConfig` (`network`, `address`, `port`). */
function migrateLegacyDnsOutboundKeys(out: Record<string, unknown>): void {
  if ('rewriteNetwork' in out) {
    const legacy = out.rewriteNetwork
    delete out.rewriteNetwork
    if (out.network === undefined && legacy !== undefined && legacy !== null && legacy !== '') {
      out.network = legacy
    }
  }
  if ('rewriteAddress' in out) {
    const legacy = out.rewriteAddress
    delete out.rewriteAddress
    if (out.address === undefined && legacy !== undefined && legacy !== null) {
      if (typeof legacy === 'string') {
        const t = legacy.trim()
        if (t) out.address = t
      } else {
        out.address = legacy
      }
    }
  }
  if ('rewritePort' in out) {
    const legacy = out.rewritePort
    delete out.rewritePort
    if (out.port === undefined && legacy !== undefined && legacy !== null && legacy !== '') {
      out.port = legacy
    }
  }
}

/** Drop empty DNS-outbound fields so JSON matches Xray `DNSOutboundConfig` parity. */
export function pruneDnsOutboundSettings(settings: Record<string, unknown>): Record<string, unknown> {
  const out = { ...settings }
  migrateLegacyDnsOutboundKeys(out)
  const nw = out.network
  if (nw === undefined || nw === null || nw === '') delete out.network
  if (out.address !== undefined && String(out.address).trim() === '') delete out.address
  if (out.port === undefined || out.port === null || out.port === '') delete out.port
  else if (typeof out.port === 'string' && out.port.trim() === '') delete out.port
  if (out.userLevel === '' || out.userLevel === undefined || out.userLevel === null) delete out.userLevel
  else if (typeof out.userLevel === 'string' && out.userLevel.trim() === '') delete out.userLevel
  else if (typeof out.userLevel === 'number' && out.userLevel === 0) delete out.userLevel

  if (Array.isArray(out.rules)) {
    const cleaned = (out.rules as unknown[])
      .map(r => {
        if (!r || typeof r !== 'object' || Array.isArray(r)) return null
        const o = { ...(r as Record<string, unknown>) }
        for (const k of Object.keys(o)) {
          if (o[k] === undefined || o[k] === null) delete o[k]
        }
        if (Array.isArray(o.domain) && o.domain.length === 0) delete o.domain
        if (o.qtype === '' || o.qtype === undefined || o.qtype === null) delete o.qtype
        return Object.keys(o).length > 0 ? o : null
      })
      .filter(Boolean) as Record<string, unknown>[]
    if (cleaned.length === 0) delete out.rules
    else out.rules = cleaned
  }
  return out
}

/** JSON body shown in the outbound editor (flattened proxy settings when applicable). */
export function outboundEditorBodyFromOutbound(ob: Outbound): Record<string, unknown> {
  if (ob.protocol === 'unmanaged') {
    return { protocol: 'unmanaged', tag: ob.tag, raw: (ob as { raw: unknown }).raw }
  }
  const flat = flattenOutboundSettings(ob) as Record<string, unknown>
  const settingsBody =
    ob.protocol === 'hysteria'
      ? stripHysteriaOutboundRedundantVersion(flat)
      : ob.protocol === 'dns'
        ? pruneDnsOutboundSettings(flat)
        : flat
  const body: Record<string, unknown> = {
    protocol: ob.protocol,
    tag: ob.tag,
    settings: settingsBody,
  }
  const streamPruned = normalizeOutboundStreamSettings((ob as { streamSettings?: unknown }).streamSettings)
  if (streamPruned !== undefined) body.streamSettings = streamPruned
  if ('sendThrough' in ob && ob.sendThrough) body.sendThrough = ob.sendThrough
  const muxPruned = normalizeOutboundStreamSettings((ob as { mux?: unknown }).mux)
  if (muxPruned !== undefined) body.mux = muxPruned
  const proxyPruned = normalizeOutboundStreamSettings((ob as { proxySettings?: unknown }).proxySettings)
  if (proxyPruned !== undefined) body.proxySettings = proxyPruned
  return body
}

export function normalizeSettingsFromEditor(protocol: string, settings: Record<string, unknown>): Record<string, unknown> {
  if (protocol === 'vless') {
    if (Array.isArray(settings.vnext) && settings.vnext.length > 0) return { ...settings }
    const { address, port, id, flow, encryption, level, email, ...rest } = settings
    if (address != null && port != null && id != null) {
      const user = compactSettingsUser({
        id,
        encryption,
        flow: typeof flow === 'string' && flow === '' ? undefined : flow,
        level,
        email,
      })
      return {
        ...rest,
        vnext: [{ address, port, users: [user] }],
      }
    }
    return { ...settings }
  }
  if (protocol === 'vmess') {
    if (Array.isArray(settings.vnext) && settings.vnext.length > 0) return { ...settings }
    const { address, port, id, alterId, security, level, email, experiments, ...rest } = settings
    if (address != null && port != null && id != null) {
      const user = compactSettingsUser({
        id,
        alterId: alterId ?? 0,
        security,
        level,
        email,
        experiments,
      })
      return {
        ...rest,
        vnext: [{ address, port, users: [user] }],
      }
    }
    return { ...settings }
  }
  if (protocol === 'trojan') {
    if (Array.isArray(settings.servers) && settings.servers.length > 0) return { ...settings }
    const { address, port, password, flow, level, email, ...rest } = settings
    if (address != null && port != null && password != null) {
      return {
        ...rest,
        servers: [compactSettingsUser({ address, port, password, flow, level, email })],
      }
    }
    return { ...settings }
  }
  if (protocol === 'shadowsocks') {
    if (Array.isArray(settings.servers) && settings.servers.length > 0) return { ...settings }
    const { address, port, password, method, level, email, uot, uotVersion, ivCheck, ...rest } = settings
    if (address != null && port != null && password != null) {
      return {
        ...rest,
        servers: [
          compactSettingsUser({ address, port, password, method, level, email, uot, uotVersion, ivCheck }),
        ],
      }
    }
    return { ...settings }
  }
  if (protocol === 'hysteria') {
    return stripHysteriaOutboundRedundantVersion({ ...settings })
  }
  if (protocol === 'dns') {
    return pruneDnsOutboundSettings({ ...settings })
  }
  return { ...settings }
}

/** Apply parsed JSON body onto an existing outbound. Omitted keys fall back to `ob`; empty `mux` / `proxySettings` / `streamSettings` / blank `sendThrough` are stripped (keys deleted). */
export function mergeEditorBodyIntoOutbound(ob: Outbound, body: Record<string, unknown>): Outbound {
  if (ob.protocol === 'unmanaged') return ob
  const protocol = (body.protocol as Outbound['protocol']) ?? ob.protocol
  const tag = body.tag != null ? String(body.tag) : ob.tag
  const bodyHasStreamSettings = Object.prototype.hasOwnProperty.call(body, 'streamSettings')
  const streamSource = bodyHasStreamSettings ? body.streamSettings : (ob as { streamSettings?: unknown }).streamSettings
  const streamSettings = normalizeOutboundStreamSettings(streamSource)
  let settingsIn = body.settings
  if (!settingsIn || typeof settingsIn !== 'object' || Array.isArray(settingsIn)) settingsIn = {}
  const settings = normalizeSettingsFromEditor(protocol, settingsIn as Record<string, unknown>)

  const sendThroughRaw =
    body.sendThrough !== undefined
      ? body.sendThrough
      : 'sendThrough' in ob
        ? (ob as { sendThrough?: unknown }).sendThrough
        : undefined
  const sendThrough =
    sendThroughRaw !== undefined && sendThroughRaw !== null && String(sendThroughRaw).trim() !== ''
      ? String(sendThroughRaw)
      : undefined

  const muxSource = body.mux !== undefined ? body.mux : (ob as { mux?: unknown }).mux
  const mux = normalizeOutboundStreamSettings(muxSource)
  const proxySource =
    body.proxySettings !== undefined ? body.proxySettings : (ob as { proxySettings?: unknown }).proxySettings
  const proxySettings = normalizeOutboundStreamSettings(proxySource)

  const next: Record<string, unknown> = {
    ...(ob as Record<string, unknown>),
    protocol,
    tag,
    settings,
  }
  if (sendThrough !== undefined) next.sendThrough = sendThrough
  else delete next.sendThrough

  if (mux !== undefined) next.mux = mux
  else delete next.mux

  if (proxySettings !== undefined) next.proxySettings = proxySettings
  else delete next.proxySettings

  if (streamSettings !== undefined) {
    next.streamSettings = streamSettings
  } else {
    delete next.streamSettings
  }
  return next as Outbound
}
