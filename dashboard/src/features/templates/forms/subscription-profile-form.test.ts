import { describe, expect, it } from 'bun:test'
import { parseSubscriptionProfileContent, parseSubscriptionProfileForEditing, serializeSubscriptionProfile } from './subscription-profile-form'

describe('subscription profile form helpers', () => {
  it('applies backend-compatible defaults to a minimal profile', () => {
    const result = parseSubscriptionProfileContent('{}')

    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.default_pool).toBe('primary')
    expect(result.data.pools).toEqual([{ id: 'primary', enabled: true }])
    expect(result.data.health_check.interval).toBe('3m')
    expect(result.data.routing_rules).toEqual([])
  })

  it('rejects invalid pool references', () => {
    const result = parseSubscriptionProfileContent(JSON.stringify({ default_pool: 'primary', pools: [{ id: 'primary', fallback_pool: 'missing' }] }))

    expect(result.success).toBe(false)
    if (result.success) return
    expect(result.error).toContain('Fallback must reference a configured pool')
  })

  it('matches backend health timeout validation', () => {
    const result = parseSubscriptionProfileContent(JSON.stringify({ health_check: { interval: '3m', timeout: '5s' } }))

    expect(result.success).toBe(false)
    if (result.success) return
    expect(result.error).toContain('Timeout must be greater than or equal to interval')
  })

  it('validates the routing payload against the declared client', () => {
    const parse = (profile: object) => parseSubscriptionProfileContent(JSON.stringify(profile)).success
    // Happ takes its own deeplink and nothing else.
    expect(parse({ client: 'happ', routing_payload: 'happ://routing/add/e30=' })).toBe(true)
    expect(parse({ client: 'happ', routing_payload: 'happ://profile' })).toBe(false)
    expect(parse({ client: 'happ', routing_payload: 'e30=' })).toBe(false)
    // INCY ignores the scheme and also accepts the bare payload.
    expect(parse({ client: 'incy', routing_payload: '://routing/onadd/e30=' })).toBe(true)
    expect(parse({ client: 'incy', routing_payload: 'e30=' })).toBe(true)
    // v2rayTun decodes base64 directly; a deeplink there silently does nothing.
    expect(parse({ client: 'v2raytun', routing_payload: 'e30=' })).toBe(true)
    expect(parse({ client: 'v2raytun', routing_payload: 'happ://routing/onadd/e30=' })).toBe(false)
    // A generic profile emits no header, so a payload would be dropped.
    expect(parse({ client: 'generic', routing_payload: 'e30=' })).toBe(false)
    // routing-enable exists only in Happ.
    expect(parse({ client: 'happ', routing_enabled: false })).toBe(true)
    expect(parse({ client: 'incy', routing_enabled: false })).toBe(false)
  })

  it('still accepts happ_deeplink from profiles written before the rename', () => {
    const result = parseSubscriptionProfileContent(JSON.stringify({ client: 'happ', happ_deeplink: 'happ://routing/add/e30=' }))
    expect(result.success).toBe(true)
  })

  it('rejects non-object pool and routing rule entries without throwing', () => {
    expect(() => parseSubscriptionProfileForEditing(JSON.stringify({ pools: [null] }))).not.toThrow()
    expect(parseSubscriptionProfileForEditing(JSON.stringify({ pools: [null] })).success).toBe(false)
    expect(() => parseSubscriptionProfileForEditing(JSON.stringify({ routing_rules: ['invalid'] }))).not.toThrow()
    expect(parseSubscriptionProfileForEditing(JSON.stringify({ routing_rules: ['invalid'] })).success).toBe(false)
  })

  it('preserves extension fields through structured serialization', () => {
    const result = parseSubscriptionProfileForEditing(
      JSON.stringify({ schema_version: 1, default_pool: 'primary', pools: [{ id: 'primary', enabled: true, extension: 'pool' }], extension: { keep: true } }),
    )

    expect(result.success).toBe(true)
    if (!result.success) return
    const serialized = JSON.parse(serializeSubscriptionProfile({ ...result.data, client: 'happ', routing_payload: 'happ://routing/off' }))
    expect(serialized.extension).toEqual({ keep: true })
    expect(serialized.pools[0].extension).toBe('pool')
    expect(serialized.routing_payload).toBe('happ://routing/off')
  })
})
