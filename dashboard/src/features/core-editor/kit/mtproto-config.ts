// Client mirror of the panel's MTProto (telemt) core rules in app/core/mtproto.py.
// No imports, so it can be tested in isolation.

export type MtprotoModes = { classic: boolean; secure: boolean; tls: boolean }

export type MtprotoFields = {
  inboundTag: string
  /** `null`: `server.port` is JSON null (not set, telemt uses 443) or not a whole number. */
  port: number | null
  tlsDomain: string
  /** `censorship.tls_domains`: extra fake TLS domains (string entries only). */
  tlsDomains: string[]
  modes: MtprotoModes
  /** `null` while WEB is off: no `web.enabled = true` and no listener with `transport = "web"`. */
  web: MtprotoWebFields | null
}

export type MtprotoWebSecretMode = 'dd' | 'plain'

export type MtprotoWebVhostFields = {
  host: string
  basePath: string
  publicAddr: string
  decoyUpstream: string
  secretMode: MtprotoWebSecretMode
  /** Index of the `web.vhosts` entry the row was read from, so its other keys stay with it when rows are removed; unset for a new row. */
  source?: number
}

export type MtprotoWebFields = {
  /** The port of the first `transport = "web"` listener; `null` when it has none or it is not a whole number. */
  listenerPort: number | null
  vhosts: MtprotoWebVhostFields[]
}

export type MtprotoConfigIssue = 'inboundTag' | 'port' | 'modes' | 'tlsDomain' | 'tlsDomains' | 'listenerPort' | 'webListener' | 'webVhost'

/** telemt 3.5.14 per-field defaults: a missing `general.modes` means fake TLS only. */
export const TELEMT_DEFAULT_MODES: Readonly<MtprotoModes> = { classic: false, secure: false, tls: true }

/** The domain the default core template ships with; the panel refuses it until it is replaced. */
export const TLS_DOMAIN_PLACEHOLDER = 'your-domain.example'

const DEFAULT_INBOUND_TAG = 'mtproto'
const DEFAULT_PORT = 443
const MAX_INBOUND_TAG_LENGTH = 256
const MODE_KEYS = ['classic', 'secure', 'tls'] as const
// The panel's rule (app/core/mtproto.py): an ASCII host name, since telemt hex-encodes its IDNA-normalized host into the "ee" secret.
const TLS_HOST_NAME = /^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$/
const WEB_DEFAULT_SECRET_MODE: MtprotoWebSecretMode = 'dd'
const WEB_SECRET_MODES: readonly unknown[] = ['dd', 'plain']
const WEB_PROFILE_LIMITS: readonly string[] = ['max_sessions', 'max_streams', 'max_streams_per_session']
const UINT32_MAX = 4294967295
const DEFAULT_WEB_LISTENER_PORT = 18080

function asObject(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}

function isValidPort(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 65535
}

function stringOr(value: unknown): string {
  return typeof value === 'string' ? value : ''
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

function parseIPv4(text: string): number[] | null {
  const parts = text.split('.')
  if (parts.length !== 4 || !parts.every(part => /^(0|[1-9]\d{0,2})$/.test(part))) return null
  const bytes = parts.map(Number)
  return bytes.every(byte => byte <= 255) ? bytes : null
}

/** The eight 16-bit groups of an IPv6 literal, or `null`. A zone (`%eth0`) is refused, as the node's net.ParseIP does. */
function parseIPv6(text: string): number[] | null {
  let source = text
  const lastColon = source.lastIndexOf(':')
  if (lastColon === -1) return null
  const tail = source.slice(lastColon + 1)
  if (tail.includes('.')) {
    const v4 = parseIPv4(tail)
    if (!v4) return null
    source = `${source.slice(0, lastColon + 1)}${((v4[0] << 8) | v4[1]).toString(16)}:${((v4[2] << 8) | v4[3]).toString(16)}`
  }
  const halves = source.split('::')
  if (halves.length > 2) return null
  const groups = (part: string) => (part === '' ? [] : part.split(':'))
  const head = groups(halves[0])
  const rest = halves.length === 2 ? groups(halves[1]) : []
  if (![...head, ...rest].every(group => /^[0-9A-Fa-f]{1,4}$/.test(group))) return null
  const missing = 8 - head.length - rest.length
  if (halves.length === 2 ? missing < 1 : missing !== 0) return null
  return [...head, ...Array<string>(missing).fill('0'), ...rest].map(group => parseInt(group, 16))
}

function isPrivateIPv4([a, b, c, d]: number[]): boolean {
  if (a === 0 && b === 0 && c === 0 && d === 0) return false
  return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
}

/** A loopback or private IP literal (never unspecified), like the node's IsLoopback() || IsPrivate(). */
function isPrivateIp(value: unknown): boolean {
  if (typeof value !== 'string') return false
  const v4 = parseIPv4(value)
  if (v4) return isPrivateIPv4(v4)
  const v6 = parseIPv6(value)
  if (!v6) return false
  if (v6.slice(0, 5).every(group => group === 0) && v6[5] === 0xffff) {
    return isPrivateIPv4([v6[6] >> 8, v6[6] & 0xff, v6[7] >> 8, v6[7] & 0xff])
  }
  if (v6.slice(0, 7).every(group => group === 0)) return v6[7] === 1
  return (v6[0] & 0xfe00) === 0xfc00
}

/** The host of a URL as Python's urlsplit().hostname reads it, or `null`. Whitespace and control characters are refused. */
function urlHostname(url: string): string | null {
  if (/[\s\x00-\x1f\x7f]/.test(url)) return null
  const netloc = /^(?:[A-Za-z][A-Za-z0-9+.-]*:)?\/\/([^/?#]*)/.exec(url)?.[1]
  if (netloc === undefined) return null
  const hostinfo = netloc.slice(netloc.lastIndexOf('@') + 1)
  const bracket = hostinfo.indexOf('[')
  const host = bracket !== -1 ? hostinfo.slice(bracket + 1).split(']')[0] : hostinfo.split(':')[0]
  return host ? host.toLowerCase() : null
}

function listenersOf(config: Record<string, unknown>): unknown[] {
  const listeners = asObject(config.server)?.listeners
  return Array.isArray(listeners) ? listeners : []
}

function isWebListener(listener: unknown): boolean {
  return asObject(listener)?.transport === 'web'
}

function isNativeListener(listener: unknown): listener is Record<string, unknown> {
  const transport = asObject(listener)?.transport
  return asObject(listener) !== undefined && (transport == null || transport === 'mtproxy')
}

function readTlsDomains(config: Record<string, unknown>): string[] {
  const domains = asObject(config.censorship)?.tls_domains
  return Array.isArray(domains) ? domains.filter((domain): domain is string => typeof domain === 'string') : []
}

function readWebVhost(value: unknown, source: number): MtprotoWebVhostFields {
  const vhost = asObject(value)
  return {
    source,
    host: stringOr(vhost?.host),
    basePath: stringOr(vhost?.base_path),
    publicAddr: stringOr(vhost?.public_addr),
    decoyUpstream: stringOr(asObject(vhost?.decoy)?.upstream),
    secretMode: asObject(vhost?.user_profile)?.secret_mode === 'plain' ? 'plain' : WEB_DEFAULT_SECRET_MODE,
  }
}

function readWebVhosts(config: Record<string, unknown>): MtprotoWebVhostFields[] {
  const vhosts = asObject(config.web)?.vhosts
  return Array.isArray(vhosts) ? vhosts.map((vhost, index) => readWebVhost(vhost, index)) : []
}

function readWeb(config: Record<string, unknown>): MtprotoWebFields | null {
  const listener = listenersOf(config).find(isWebListener)
  if (asObject(config.web)?.enabled !== true && listener === undefined) return null
  const port = asObject(listener)?.port
  return { listenerPort: typeof port === 'number' && Number.isInteger(port) ? port : null, vhosts: readWebVhosts(config) }
}

function sameVhost(a: MtprotoWebVhostFields, b: MtprotoWebVhostFields): boolean {
  return a.source === b.source && a.host === b.host && a.basePath === b.basePath && a.publicAddr === b.publicAddr && a.decoyUpstream === b.decoyUpstream && a.secretMode === b.secretMode
}

function sameWeb(a: MtprotoWebFields | null, b: MtprotoWebFields | null): boolean {
  if (a === null || b === null) return a === b
  return a.listenerPort === b.listenerPort && a.vhosts.length === b.vhosts.length && a.vhosts.every((vhost, index) => sameVhost(vhost, b.vhosts[index]))
}

function sameStrings(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index])
}

export function emptyMtprotoWebVhost(): MtprotoWebVhostFields {
  return { host: '', basePath: '', publicAddr: '', decoyUpstream: '', secretMode: WEB_DEFAULT_SECRET_MODE }
}

/** What the form writes when WEB is switched on: a free private port and the config's vhosts (one empty vhost if it has none). */
export function mtprotoWebDefaults(config: Record<string, unknown>): MtprotoWebFields {
  const port = asObject(config.server)?.port ?? DEFAULT_PORT
  const vhosts = readWebVhosts(config)
  return { listenerPort: port === DEFAULT_WEB_LISTENER_PORT ? DEFAULT_WEB_LISTENER_PORT + 1 : DEFAULT_WEB_LISTENER_PORT, vhosts: vhosts.length ? vhosts : [emptyMtprotoWebVhost()] }
}

export function readMtprotoFields(config: Record<string, unknown>): MtprotoFields {
  const tag = config.inbound_tag
  const port = asObject(config.server)?.port
  const domain = asObject(config.censorship)?.tls_domain
  return {
    inboundTag: typeof tag === 'string' ? tag : tag == null ? DEFAULT_INBOUND_TAG : String(tag),
    port: port === undefined ? DEFAULT_PORT : typeof port === 'number' && Number.isInteger(port) ? port : null,
    tlsDomain: typeof domain === 'string' ? domain : '',
    tlsDomains: readTlsDomains(config),
    modes: resolvedModes(config),
    web: readWeb(config),
  }
}

/** The row's own vhost (`fields.source`) with the form's fields written over it; only changed fields are written, so other keys and values stay. */
function applyWebVhost(previousVhosts: unknown[], fields: MtprotoWebVhostFields): unknown {
  const previous = fields.source === undefined ? undefined : previousVhosts[fields.source]
  const old = asObject(previous)
  const was = old && fields.source !== undefined ? readWebVhost(old, fields.source) : null
  if (was && sameVhost(was, fields)) return previous
  const vhost: Record<string, unknown> = { ...old }
  if (!was || was.host !== fields.host) vhost.host = fields.host
  if (!was || was.basePath !== fields.basePath) {
    if (fields.basePath !== '') vhost.base_path = fields.basePath
    else delete vhost.base_path
  }
  if (!was || was.publicAddr !== fields.publicAddr) vhost.public_addr = fields.publicAddr
  // The form edits the http_upstream decoy only, the one mode the panel accepts.
  if (!was || was.decoyUpstream !== fields.decoyUpstream) vhost.decoy = { ...asObject(vhost.decoy), mode: 'http_upstream', upstream: fields.decoyUpstream }
  if (was ? was.secretMode !== fields.secretMode : fields.secretMode !== WEB_DEFAULT_SECRET_MODE) {
    vhost.user_profile = { ...asObject(vhost.user_profile), secret_mode: fields.secretMode }
  }
  return vhost
}

/** telemt's default public listeners, which it opens only while `server.listeners` is empty. */
function defaultNativeListeners(server: Record<string, unknown>): Record<string, unknown>[] {
  const ipv4 = server.listen_addr_ipv4
  const ipv6 = server.listen_addr_ipv6
  return [{ ip: typeof ipv4 === 'string' && ipv4 !== '' ? ipv4 : '0.0.0.0' }, { ip: typeof ipv6 === 'string' && ipv6 !== '' ? ipv6 : '::' }]
}

function newWebListener(port: number | null): Record<string, unknown> {
  // A front (Caddy, nginx) on the same host forwards to it and sends the client address in one X-Forwarded-For header.
  return { ip: '127.0.0.1', ...(port === null ? {} : { port }), transport: 'web', web_client_ip_source: 'x_forwarded_for', web_trusted_proxy_cidrs: ['127.0.0.1/32'] }
}

function applyWeb(next: Record<string, unknown>, config: Record<string, unknown>, web: MtprotoWebFields | null, current: MtprotoWebFields | null) {
  const server: Record<string, unknown> = { ...asObject(next.server) }
  const listeners = listenersOf(config)
  if (web === null) {
    const kept = listeners.filter(listener => !isWebListener(listener))
    if (kept.length) server.listeners = kept
    else delete server.listeners
    next.server = server
    delete next.web
    return
  }
  const webIndex = listeners.findIndex(isWebListener)
  if (webIndex === -1) {
    // Without this, adding the WEB listener would switch telemt's default native listeners off.
    server.listeners = [...(listeners.length ? listeners : defaultNativeListeners(server)), newWebListener(web.listenerPort)]
  } else if (web.listenerPort !== current?.listenerPort) {
    const listener: Record<string, unknown> = { ...asObject(listeners[webIndex]) }
    if (web.listenerPort === null) delete listener.port
    else listener.port = web.listenerPort
    server.listeners = listeners.map((item, index) => (index === webIndex ? listener : item))
  }
  next.server = server
  const section: Record<string, unknown> = { ...asObject(config.web) }
  const previous = Array.isArray(section.vhosts) ? section.vhosts : []
  section.enabled = true
  section.vhosts = web.vhosts.map(vhost => applyWebVhost(previous, vhost))
  next.web = section
}

/** A new config with the form's fields written; every other key is kept. An empty TLS domain removes the key. */
export function applyMtprotoFields(config: Record<string, unknown>, fields: MtprotoFields): Record<string, unknown> {
  const current = readMtprotoFields(config)
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
  // The lists are written only when changed, so entries the form does not read (non-strings) stay as they are.
  if (!sameStrings(fields.tlsDomains, current.tlsDomains)) {
    const rest: Record<string, unknown> = { ...asObject(next.censorship) }
    if (fields.tlsDomains.length) rest.tls_domains = [...fields.tlsDomains]
    else delete rest.tls_domains
    next.censorship = rest
  }
  if (!sameWeb(fields.web, current.web)) applyWeb(next, config, fields.web, current.web)
  return next
}

function isExtraTlsDomain(value: unknown): boolean {
  if (typeof value !== 'string') return false
  const trimmed = value.trim()
  // telemt skips empty entries.
  if (!trimmed) return true
  const host = trimmed.endsWith('.') ? trimmed.slice(0, -1) : trimmed
  return TLS_HOST_NAME.test(host) && !host.toLowerCase().endsWith('.example')
}

function isValidWebVhost(value: unknown): boolean {
  const vhost = asObject(value)
  if (!vhost || vhost.profiles != null) return false
  if (typeof vhost.host !== 'string' || vhost.host.trim() === '') return false
  if (vhost.base_path != null && typeof vhost.base_path !== 'string') return false
  const decoy = asObject(vhost.decoy)
  if (decoy?.mode !== 'http_upstream' || typeof decoy.upstream !== 'string' || !isPrivateIp(urlHostname(decoy.upstream))) return false
  if (vhost.user_profile == null) return true
  const profile = asObject(vhost.user_profile)
  if (!profile) return false
  if (profile.secret_mode != null && !WEB_SECRET_MODES.includes(profile.secret_mode)) return false
  return Object.entries(profile).every(
    ([key, limit]) => key === 'secret_mode' || (WEB_PROFILE_LIMITS.includes(key) && (limit == null || (typeof limit === 'number' && Number.isInteger(limit) && limit >= 0 && limit <= UINT32_MAX))),
  )
}

/** Issues the panel would reject, in the order it checks them. Type errors elsewhere are left to the server. */
export function mtprotoConfigIssues(config: Record<string, unknown>): MtprotoConfigIssue[] {
  const issues: MtprotoConfigIssue[] = []
  const add = (issue: MtprotoConfigIssue) => {
    if (!issues.includes(issue)) issues.push(issue)
  }

  const tag = config.inbound_tag ?? DEFAULT_INBOUND_TAG
  const trimmedTag = typeof tag === 'string' ? tag.trim() : ''
  if (!trimmedTag || trimmedTag.includes(',') || trimmedTag.includes('<=>') || [...trimmedTag].length > MAX_INBOUND_TAG_LENGTH) {
    add('inboundTag')
  }

  const server = asObject(config.server)
  const port = server?.port ?? DEFAULT_PORT
  const listeners = listenersOf(config)
  const webListeners = listeners.filter(isWebListener).map(listener => asObject(listener)!)
  if (!isValidPort(port)) {
    add('port')
  } else {
    // The one-port rule is for MTProxy listeners; a WEB listener has its own private port.
    const natives = listeners.filter(isNativeListener)
    if (natives.some(listener => listener.port != null && listener.port !== port)) add('listenerPort')
    const nativePorts = new Set(natives.map(listener => listener.port))
    const badWebListener = webListeners.some(listener => !isPrivateIp(listener.ip) || !isValidPort(listener.port) || listener.port === port || nativePorts.has(listener.port))
    if (badWebListener) add('webListener')
  }

  const modes = resolvedModes(config)
  if (!modes.classic && !modes.secure && !modes.tls) add('modes')

  const domain = asObject(config.censorship)?.tls_domain
  if (domain == null) {
    if (modes.tls) add('tlsDomain')
  } else {
    const trimmed = typeof domain === 'string' ? domain.trim() : ''
    const malformed = !trimmed || /[\s/\\]/.test(trimmed)
    // One trailing dot is allowed, as telemt keeps it.
    const host = trimmed.endsWith('.') ? trimmed.slice(0, -1) : trimmed
    const notForTls = modes.tls && (trimmed.includes(':') || !TLS_HOST_NAME.test(host) || host.toLowerCase().endsWith('.example'))
    if (malformed || notForTls) add('tlsDomain')
  }

  const extraDomains = asObject(config.censorship)?.tls_domains
  if (extraDomains != null && (!Array.isArray(extraDomains) || !extraDomains.every(isExtraTlsDomain))) add('tlsDomains')

  const web = asObject(config.web)
  const enabled = web?.enabled === true
  const vhosts = web?.vhosts
  const hasWebListener = webListeners.length > 0
  // A WEB listener and web.enabled go together.
  if (enabled !== hasWebListener) add('webListener')
  if (vhosts != null && (!Array.isArray(vhosts) || !vhosts.every(isValidWebVhost))) add('webVhost')
  if (enabled && hasWebListener && !(Array.isArray(vhosts) && vhosts.length > 0)) add('webVhost')

  return issues
}
