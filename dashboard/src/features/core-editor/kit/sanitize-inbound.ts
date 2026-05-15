import type { Inbound, Profile } from '@pasarguard/xray-config-kit'

/** Loopback values often come from Xray samples, browser autofill, or legacy defaults — not a meaningful rewrite target in the editor. */
export function isPlaceholderTunnelRewriteAddress(v: unknown): boolean {
  if (typeof v !== 'string') return false
  const t = v.trim().toLowerCase()
  return t === '127.0.0.1' || t === 'localhost' || t === '::1'
}

/** xray-config-kit strict schema allows only these; empty or unknown values break compile. */
export function normalizeTunnelNetworkForKit(v: unknown): 'tcp' | 'udp' | 'tcp,udp' {
  if (typeof v !== 'string') return 'tcp,udp'
  const lower = v.trim().toLowerCase().replace(/\s+/g, '')
  if (lower === '' || lower === 'tcp+udp') return 'tcp,udp'
  if (lower === 'tcp,udp') return 'tcp,udp'
  if (lower === 'udp') return 'udp'
  if (lower === 'tcp') return 'tcp'
  return 'tcp,udp'
}

function clearClients(inbound: Inbound): Inbound {
  if (inbound.protocol === 'unmanaged' || inbound.protocol === 'tun') return inbound
  if (
    inbound.protocol === 'http' ||
    inbound.protocol === 'mixed' ||
    inbound.protocol === 'socks' ||
    inbound.protocol === 'dokodemo-door' ||
    inbound.protocol === 'tunnel' ||
    inbound.protocol === 'wireguard'
  ) {
    return inbound
  }
  if ('clients' in inbound) {
    return { ...inbound, clients: [] } as Inbound
  }
  return inbound
}

function isTunnelLikeInbound(ib: Inbound): boolean {
  return ib.protocol === 'tunnel' || ib.protocol === 'dokodemo-door'
}

function recordToPortMap(pm: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(pm)) out[k] = v != null ? String(v) : ''
  return out
}

/**
 * Migrates tunnel/dokodemo inbounds for the kit: flat parity fields (`address`, `targetPort`, `network`, …).
 * `portMap` stays as typed inbound fields; `normalizeProfile` in xray-config-kit lifts `raw` `/settings/portMap`.
 * A legacy top-level inbound `settings` object is Xray JSON shape only and fails `.strict()` inbound schema.
 */
export function normalizeTunnelInboundForKit(ib: Inbound): Inbound {
  if (!isTunnelLikeInbound(ib)) {
    if (!('portMap' in (ib as object))) return ib
    const d = structuredClone(ib) as Record<string, unknown>
    delete d.portMap
    return d as unknown as Inbound
  }
  const draft = structuredClone(ib) as Record<string, unknown>

  const legacy = draft.settings
  if (!legacy || typeof legacy !== 'object' || Array.isArray(legacy)) {
    delete draft.settings
    if (isPlaceholderTunnelRewriteAddress(draft.address)) delete draft.address
    draft.network = normalizeTunnelNetworkForKit(draft.network)
    return draft as unknown as Inbound
  }

  const s = legacy as Record<string, unknown>

  if (draft.address === undefined) {
    const a = s.rewriteAddress ?? s.address
    if (typeof a === 'string') {
      const trimmed = a.trim()
      if (trimmed !== '' && !isPlaceholderTunnelRewriteAddress(trimmed)) draft.address = trimmed
    }
  }

  if (draft.targetPort === undefined) {
    const tp = s.rewritePort ?? s.port
    if (tp !== undefined && tp !== null && tp !== '') {
      const n = typeof tp === 'number' ? tp : Number(tp)
      if (Number.isFinite(n) && Number.isInteger(n)) draft.targetPort = n
      else if (Number.isFinite(n)) draft.targetPort = Math.trunc(n)
    }
  }

  if (draft.network === undefined || (typeof draft.network === 'string' && draft.network.trim() === '')) {
    const nw = s.network ?? s.allowedNetwork
    if (typeof nw === 'string' && nw.trim() !== '') draft.network = normalizeTunnelNetworkForKit(nw)
  }

  if (draft.followRedirect === undefined && typeof s.followRedirect === 'boolean') draft.followRedirect = s.followRedirect

  const pm = s.portMap
  if (
    pm &&
    typeof pm === 'object' &&
    !Array.isArray(pm) &&
    Object.keys(pm).length > 0 &&
    (draft.portMap === undefined ||
      (typeof draft.portMap === 'object' &&
        draft.portMap !== null &&
        !Array.isArray(draft.portMap) &&
        Object.keys(draft.portMap as object).length === 0))
  ) {
    draft.portMap = recordToPortMap(pm as Record<string, unknown>)
  }

  delete draft.settings
  if (isPlaceholderTunnelRewriteAddress(draft.address)) delete draft.address
  draft.network = normalizeTunnelNetworkForKit(draft.network)
  return draft as unknown as Inbound
}

/**
 * REALITY keys must be 32 raw bytes as base64url (no standard `+`/`/`). If present but malformed,
 * xray-config-kit rejects with XCK_SEMANTIC_INVALID_REALITY_PUBLIC_KEY — omit the field instead.
 */
function isValidRealityBase64UrlKey32(v: string): boolean {
  const t = v.trim()
  if (!t || !/^[A-Za-z0-9_-]+$/.test(t)) return false
  const padLen = (4 - (t.length % 4)) % 4
  const padded = t + '='.repeat(padLen)
  let bin: string
  try {
    bin = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  } catch {
    return false
  }
  return bin.length === 32
}

/** Filter out empty strings from array fields in security settings to prevent validation errors. */
function sanitizeSecurityArrays(inbound: Inbound): Inbound {
  if (!('security' in inbound) || !inbound.security || typeof inbound.security !== 'object') {
    return inbound
  }

  const security = inbound.security as Record<string, unknown>
  const sanitized = { ...security }

  for (const [key, value] of Object.entries(sanitized)) {
    if (Array.isArray(value)) {
      const filtered = value.filter(item => {
        if (typeof item === 'string') return item.trim() !== ''
        return item !== '' && item !== null && item !== undefined
      })
      // Allow empty arrays for shortIds field, filter others
      if (key !== 'shortIds') {
        sanitized[key] = filtered
      }
    }
  }

  // REALITY: never persist invalid `publicKey` (kit validates when set). Empty / legacy placeholder / bad encoding → omit.
  if (security.type === 'reality') {
    const privateKeyValue = String(sanitized.privateKey ?? '').trim()
    const publicKeyRaw = String(sanitized.publicKey ?? '').trim()
    const shortIdsValue = sanitized.shortIds

    if (privateKeyValue === '') {
      sanitized.privateKey = 'YOUR_PRIVATE_KEY'
    }

    const publicKeyBadPlaceholder = publicKeyRaw === '' || publicKeyRaw === 'YOUR_PUBLIC_KEY'
    if (publicKeyBadPlaceholder || !isValidRealityBase64UrlKey32(publicKeyRaw)) {
      delete sanitized.publicKey
    } else {
      sanitized.publicKey = publicKeyRaw
    }

    if (!Array.isArray(shortIdsValue) || shortIdsValue.length === 0) {
      sanitized.shortIds = ['YOUR_SHORT_ID']
    }

    if (sanitized.target === '' || sanitized.target === undefined) {
      delete sanitized.target
    }
  }

  return { ...inbound, security: sanitized } as Inbound
}

/** Panel policy: never surface client rows in the editor; always persist empty client lists for protocols that use `clients`. */
export function sanitizeProfileInbounds(profile: Profile): Profile {
  return {
    ...profile,
    inbounds: profile.inbounds.map(ib => sanitizeSecurityArrays(normalizeTunnelInboundForKit(clearClients(ib)))),
  }
}
