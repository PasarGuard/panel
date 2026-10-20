// Client mirror of the panel's MTProto (telemt) core rules in app/core/mtproto.py.
// No imports, so it can be tested in isolation.

export type MtprotoModes = { classic: boolean; secure: boolean; tls: boolean }

export type MtprotoFields = {
  inboundTag: string
  /** `null`: `server.port` is JSON null (not set, telemt uses 443) or not a whole number. */
  port: number | null
  tlsDomain: string
  modes: MtprotoModes
}

export type MtprotoConfigIssue = 'inboundTag' | 'port' | 'modes' | 'tlsDomain' | 'listenerPort'

/** telemt 3.5.14 per-field defaults: a missing `general.modes` means fake TLS only. */
export const TELEMT_DEFAULT_MODES: Readonly<MtprotoModes> = { classic: false, secure: false, tls: true }

/** The domain the default core template ships with; the panel refuses it until it is replaced. */
export const TLS_DOMAIN_PLACEHOLDER = 'your-domain.example'

const DEFAULT_INBOUND_TAG = 'mtproto'
const DEFAULT_PORT = 443
const MAX_INBOUND_TAG_LENGTH = 256
const MODE_KEYS = ['classic', 'secure', 'tls'] as const

function asObject(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

function isValidPort(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 65535
}

function resolvedModes(config: Record<string, unknown>): MtprotoModes {
  const raw = asObject(asObject(config.general)?.modes)
  const modes: MtprotoModes = { ...TELEMT_DEFAULT_MODES }
  for (const key of MODE_KEYS) {
    const value = raw?.[key]
    if (typeof value === 'boolean') modes[key] = value
  }
  return modes
}

export function readMtprotoFields(config: Record<string, unknown>): MtprotoFields {
  const tag = config.inbound_tag
  const port = asObject(config.server)?.port
  const domain = asObject(config.censorship)?.tls_domain
  return {
    inboundTag: typeof tag === 'string' ? tag : tag == null ? DEFAULT_INBOUND_TAG : String(tag),
    port: port === undefined ? DEFAULT_PORT : typeof port === 'number' && Number.isInteger(port) ? port : null,
    tlsDomain: typeof domain === 'string' ? domain : '',
    modes: resolvedModes(config),
  }
}

/** A new config with the four fields written; every other key is kept. An empty TLS domain removes the key. */
export function applyMtprotoFields(config: Record<string, unknown>, fields: MtprotoFields): Record<string, unknown> {
  const general = asObject(config.general) ?? {}
  const next: Record<string, unknown> = {
    ...config,
    inbound_tag: fields.inboundTag,
    general: { ...general, modes: { ...(asObject(general.modes) ?? {}), ...fields.modes } },
    server: { ...(asObject(config.server) ?? {}), port: fields.port },
  }
  const censorship = asObject(config.censorship)
  if (fields.tlsDomain !== '') {
    next.censorship = { ...censorship, tls_domain: fields.tlsDomain }
  } else if (censorship) {
    const rest = { ...censorship }
    delete rest.tls_domain
    next.censorship = rest
  }
  return next
}

/** Issues the panel would reject, in the order it checks them. Type errors elsewhere are left to the server. */
export function mtprotoConfigIssues(config: Record<string, unknown>): MtprotoConfigIssue[] {
  const issues: MtprotoConfigIssue[] = []

  const tag = config.inbound_tag ?? DEFAULT_INBOUND_TAG
  const trimmedTag = typeof tag === 'string' ? tag.trim() : ''
  if (!trimmedTag || trimmedTag.includes(',') || trimmedTag.includes('<=>') || [...trimmedTag].length > MAX_INBOUND_TAG_LENGTH) {
    issues.push('inboundTag')
  }

  const server = asObject(config.server)
  const port = server?.port ?? DEFAULT_PORT
  const listeners = server?.listeners
  if (!isValidPort(port)) {
    issues.push('port')
  } else if (Array.isArray(listeners)) {
    const mismatch = listeners.some(listener => {
      const listenerPort = asObject(listener)?.port
      return listenerPort != null && listenerPort !== port
    })
    if (mismatch) issues.push('listenerPort')
  }

  const modes = resolvedModes(config)
  if (!modes.classic && !modes.secure && !modes.tls) issues.push('modes')

  const domain = asObject(config.censorship)?.tls_domain
  if (domain == null) {
    if (modes.tls) issues.push('tlsDomain')
  } else {
    const trimmed = typeof domain === 'string' ? domain.trim() : ''
    const malformed = !trimmed || /[\s/\\]/.test(trimmed)
    const notForTls = modes.tls && (trimmed.includes(':') || trimmed.toLowerCase().endsWith('.example'))
    if (malformed || notForTls) issues.push('tlsDomain')
  }

  return issues
}
