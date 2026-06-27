// Always-injected by the node (backend/xray/config.go: requiredAPIServices).
// Shown locked in the UI; never written to the config by the panel.
export const REQUIRED_API_SERVICES = ['HandlerService', 'LoggerService', 'StatsService'] as const

// Optional services an admin may opt into (node allowlist minus the required ones).
export const OPTIONAL_API_SERVICES = ['RoutingService', 'ObservatoryService', 'ReflectionService'] as const

// Lowercase -> canonical name. Mirrors canonicalAPIServices in the node's
// backend/xray/config.go. Ceiling: there is no automatic drift detection — this
// map must be synced by hand when xray-core changes its API services. The unit
// test pins the expected names so a stale edit fails loudly.
export const CANONICAL_API_SERVICES: Record<string, string> = {
  reflectionservice: 'ReflectionService',
  handlerservice: 'HandlerService',
  loggerservice: 'LoggerService',
  statsservice: 'StatsService',
  observatoryservice: 'ObservatoryService',
  routingservice: 'RoutingService',
}

function readApiServices(config: unknown): string[] {
  if (typeof config !== 'object' || config === null) return []
  const api = (config as Record<string, unknown>).api
  if (typeof api !== 'object' || api === null) return []
  const services = (api as Record<string, unknown>).services
  if (!Array.isArray(services)) return []
  return services.filter((s): s is string => typeof s === 'string')
}

// Optional services currently present in the config, canonicalized and deduped.
export function getSelectedOptional(config: unknown): string[] {
  const optional = new Set<string>(OPTIONAL_API_SERVICES.map(s => s.toLowerCase()))
  const selected: string[] = []
  const seen = new Set<string>()
  for (const raw of readApiServices(config)) {
    const key = raw.trim().toLowerCase()
    if (optional.has(key) && !seen.has(key)) {
      seen.add(key)
      selected.push(CANONICAL_API_SERVICES[key])
    }
  }
  return selected
}

// Service names present in the config that are not in the node allowlist.
export function findUnknownApiServices(config: unknown): string[] {
  const unknown: string[] = []
  const seen = new Set<string>()
  for (const raw of readApiServices(config)) {
    const key = raw.trim().toLowerCase()
    if (key === '' || seen.has(key)) continue
    seen.add(key)
    if (!CANONICAL_API_SERVICES[key]) unknown.push(raw)
  }
  return unknown
}

// Return a new config with `service` added or removed from api.services.
// Only `api.services` is touched; other api/config keys are preserved. An empty
// services array is removed, and an api object with no remaining keys is dropped.
export function setOptionalService(
  config: Record<string, unknown>,
  service: string,
  enabled: boolean,
): Record<string, unknown> {
  const key = service.trim().toLowerCase()
  const canonical = CANONICAL_API_SERVICES[key]
  if (!canonical) return config

  const next: Record<string, unknown> = { ...config }
  const api: Record<string, unknown> =
    typeof next.api === 'object' && next.api !== null ? { ...(next.api as Record<string, unknown>) } : {}

  const current = Array.isArray(api.services)
    ? (api.services as unknown[]).filter((s): s is string => typeof s === 'string')
    : []

  const filtered = current.filter(s => s.trim().toLowerCase() !== key)
  if (enabled) filtered.push(canonical)

  if (filtered.length > 0) {
    api.services = filtered
    next.api = api
    return next
  }

  delete api.services
  if (Object.keys(api).length === 0) {
    delete next.api
  } else {
    next.api = api
  }
  return next
}
