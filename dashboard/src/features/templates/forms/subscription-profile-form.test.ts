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

  it('accepts only Happ routing add/onadd deeplinks', () => {
    expect(parseSubscriptionProfileContent(JSON.stringify({ client: 'happ', happ_deeplink: 'happ://routing/add/e30=' })).success).toBe(true)
    expect(parseSubscriptionProfileContent(JSON.stringify({ client: 'happ', happ_deeplink: 'happ://profile' })).success).toBe(false)
    expect(parseSubscriptionProfileContent(JSON.stringify({ client: 'v2rayn', happ_deeplink: 'happ://routing/onadd/e30=' })).success).toBe(false)
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
    const serialized = JSON.parse(serializeSubscriptionProfile({ ...result.data, client: 'happ', happ_deeplink: 'happ://profile' }))
    expect(serialized.extension).toEqual({ keep: true })
    expect(serialized.pools[0].extension).toBe('pool')
    expect(serialized.happ_deeplink).toBe('happ://profile')
  })
})
