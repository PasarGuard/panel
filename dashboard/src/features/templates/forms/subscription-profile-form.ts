import { z } from 'zod'

const PROFILE_ID_PATTERN = /^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$/
const INTERVAL_PATTERN = /^\d+(?:ms|s|m|h)$/
const TIMEOUT_PATTERN = /^\d+(?:ms|s|m|h)$/
const HAPP_ROUTING_PREFIXES = ['happ://routing/add/', 'happ://routing/onadd/', 'happ://routing/off'] as const
// INCY parses the link whatever the scheme, and also takes the bare payload.
const INCY_ROUTING_PREFIXES = ['happ://routing/', 'incy://routing/', '://routing/'] as const

const isBase64 = (value: string) => /^[A-Za-z0-9+/]+={0,2}$/.test(value) && value.length % 4 === 0

function durationMilliseconds(value: string): number {
  const match = /^(\d+)(ms|s|m|h)$/.exec(value)
  if (!match) return Number.NaN
  const multipliers = { ms: 1, s: 1_000, m: 60_000, h: 3_600_000 } as const
  return Number(match[1]) * multipliers[match[2] as keyof typeof multipliers]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && !Array.isArray(value) && typeof value === 'object'
}

export const profilePoolSchema = z
  .object({
    id: z.string().min(1).max(64).regex(PROFILE_ID_PATTERN, "Use lowercase letters, numbers, '_' or '-'."),
    // Display label only; `id` stays machine-readable because routing rules address it.
    title: z.string().max(64).nullable().optional(),
    fallback_pool: z.string().max(64).regex(PROFILE_ID_PATTERN, "Use lowercase letters, numbers, '_' or '-'.").nullable().optional(),
    enabled: z.boolean().default(true),
  })
  .passthrough()

export const subscriptionProfileSchema = z
  .object({
    schema_version: z.literal(1).default(1),
    default_pool: z.string().min(1).max(64).regex(PROFILE_ID_PATTERN, "Use lowercase letters, numbers, '_' or '-'.").default('primary'),
    pools: z
      .array(profilePoolSchema)
      .min(1, 'Add at least one pool.')
      .default([{ id: 'primary', enabled: true }]),
    health_check: z
      .object({
        url: z.string().min(1).max(2048).default('https://www.gstatic.com/generate_204'),
        interval: z.string().regex(INTERVAL_PATTERN, 'Use a duration such as 30s, 3m or 1h.').default('3m'),
        tolerance: z.number().int().min(0).max(65535).default(50),
        timeout: z.string().regex(TIMEOUT_PATTERN, 'Use a duration such as 500ms, 5s, 2m or 1h.').default('30m'),
        // leastPing/leastLoad need measured latency, which only burstObservatory collects.
        burst: z.boolean().default(false),
      })
      .passthrough()
      .default({}),
    routing_rules: z.array(z.record(z.unknown())).default([]),
    // Under AsIs, Xray never resolves a domain, so IP rules (geoip:*) never match.
    domain_strategy: z.enum(['AsIs', 'IPIfNonMatch', 'IPOnDemand']).default('AsIs'),
    balancer_strategy: z.enum(['random', 'roundRobin', 'leastPing', 'leastLoad']).default('random'),
    publish_endpoint_configs: z.boolean().default(true),
    client: z.enum(['generic', 'happ', 'incy', 'v2raytun']).default('generic'),
    routing_payload: z
      .string()
      .max(2048)
      .transform(value => value.trim() || null)
      .nullable()
      .optional(),
    // Happ only: `routing-enable: 0` switches its routing off outright.
    routing_enabled: z.boolean().nullable().optional(),
  })
  .passthrough()
  .superRefine((profile, context) => {
    const poolIds = profile.pools.map(pool => pool.id)
    const uniquePoolIds = new Set(poolIds)

    if (uniquePoolIds.size !== poolIds.length) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['pools'], message: 'Pool names must be unique.' })
    }
    const enabledPoolIds = new Set(profile.pools.filter(pool => pool.enabled).map(pool => pool.id))
    if (!uniquePoolIds.has(profile.default_pool)) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['default_pool'], message: 'Default pool must reference a configured pool.' })
    } else if (!enabledPoolIds.has(profile.default_pool)) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['default_pool'], message: 'Default pool must be enabled.' })
    }

    profile.pools.forEach((pool, index) => {
      if (!pool.fallback_pool) return
      if (pool.fallback_pool === pool.id) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['pools', index, 'fallback_pool'], message: 'A pool cannot fall back to itself.' })
      } else if (!uniquePoolIds.has(pool.fallback_pool)) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['pools', index, 'fallback_pool'], message: 'Fallback must reference a configured pool.' })
      } else if (!enabledPoolIds.has(pool.fallback_pool)) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['pools', index, 'fallback_pool'], message: 'Fallback pool must be enabled.' })
      }
    })

    if (durationMilliseconds(profile.health_check.timeout) < durationMilliseconds(profile.health_check.interval)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['health_check', 'timeout'],
        message: 'Timeout must be greater than or equal to interval.',
      })
    }

    // All three clients read the `routing` header but disagree on its value.
    const payload = profile.routing_payload
    if (payload) {
      const reject = (message: string) => context.addIssue({ code: z.ZodIssueCode.custom, path: ['routing_payload'], message })
      if (profile.client === 'generic') {
        reject('Pick the client first: a generic profile sends no routing header.')
      } else if (profile.client === 'happ' && !HAPP_ROUTING_PREFIXES.some(prefix => payload.startsWith(prefix))) {
        reject('Happ expects a happ://routing/add, /onadd or /off link.')
      } else if (profile.client === 'incy' && !INCY_ROUTING_PREFIXES.some(prefix => payload.startsWith(prefix)) && !isBase64(payload)) {
        reject('INCY expects a ://routing/... link or bare base64.')
      } else if (profile.client === 'v2raytun' && !isBase64(payload)) {
        reject('v2rayTun expects bare base64 and does not decode a deeplink.')
      }
    }
    if (profile.routing_enabled != null && profile.client !== 'happ') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['routing_enabled'],
        message: 'routing-enable is only supported by Happ.',
      })
    }
  })

export type SubscriptionProfileFormValue = z.infer<typeof subscriptionProfileSchema>

export type SubscriptionProfileParseResult = { success: true; data: SubscriptionProfileFormValue } | { success: false; error: string }

export function parseSubscriptionProfileContent(content: string): SubscriptionProfileParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Invalid JSON' }
  }

  const result = subscriptionProfileSchema.safeParse(parsed)
  if (!result.success) {
    const issue = result.error.issues[0]
    const location = issue.path.length ? `${issue.path.join('.')}: ` : ''
    return { success: false, error: `${location}${issue.message}` }
  }
  return { success: true, data: result.data }
}

export function parseSubscriptionProfileForEditing(content: string): SubscriptionProfileParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Invalid JSON' }
  }

  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    return { success: false, error: 'Profile content must be a JSON object.' }
  }
  const profile = parsed as Record<string, unknown>
  if (profile.pools !== undefined && !Array.isArray(profile.pools)) {
    return { success: false, error: 'The pools field must be an array. Use Raw JSON to repair this profile.' }
  }
  if (Array.isArray(profile.pools) && profile.pools.some(pool => !isRecord(pool))) {
    return { success: false, error: 'Every pools item must be an object. Use Raw JSON to repair this profile.' }
  }
  if (profile.health_check !== undefined && (!profile.health_check || Array.isArray(profile.health_check) || typeof profile.health_check !== 'object')) {
    return { success: false, error: 'The health_check field must be an object. Use Raw JSON to repair this profile.' }
  }
  if (profile.routing_rules !== undefined && !Array.isArray(profile.routing_rules)) {
    return { success: false, error: 'The routing_rules field must be an array. Use Raw JSON to repair this profile.' }
  }
  if (Array.isArray(profile.routing_rules) && profile.routing_rules.some(rule => !isRecord(rule))) {
    return { success: false, error: 'Every routing_rules item must be an object. Use Raw JSON to repair this profile.' }
  }

  return {
    success: true,
    data: {
      ...profile,
      schema_version: (profile.schema_version as 1 | undefined) ?? 1,
      default_pool: (profile.default_pool as string | undefined) ?? 'primary',
      pools: (profile.pools as SubscriptionProfileFormValue['pools'] | undefined)?.map(pool => ({
        ...pool,
        enabled: pool.enabled ?? true,
      })) ?? [{ id: 'primary', enabled: true }],
      health_check: {
        url: 'https://www.gstatic.com/generate_204',
        interval: '3m',
        tolerance: 50,
        timeout: '30m',
        ...(profile.health_check as Partial<SubscriptionProfileFormValue['health_check']> | undefined),
      },
      routing_rules: (profile.routing_rules as SubscriptionProfileFormValue['routing_rules'] | undefined) ?? [],
      client: (profile.client as SubscriptionProfileFormValue['client'] | undefined) ?? 'generic',
    } as SubscriptionProfileFormValue,
  }
}

export function serializeSubscriptionProfile(profile: SubscriptionProfileFormValue): string {
  return JSON.stringify(profile, null, 2)
}
