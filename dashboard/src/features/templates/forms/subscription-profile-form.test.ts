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
    expect(result.data.health_check.timeout).toBe('30m')
    expect(result.data.health_check.probe_timeout).toBe('5s')
    expect(result.data.routing_rules).toEqual([])
  })

  it('shows effective defaults when editing a saved profile from before those fields existed', () => {
    const original = JSON.stringify({ default_pool: 'primary', pools: [{ id: 'primary' }], extension: 'preserved' })
    const result = parseSubscriptionProfileForEditing(original)

    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.domain_strategy).toBe('AsIs')
    expect(result.data.balancer_strategy).toBe('random')
    expect(result.data.publish_endpoint_configs).toBe(true)
    expect(result.data.extension).toBe('preserved')
    // Parsing supplies display values only; opening the editor does not rewrite
    // the raw saved document until an actual edit calls serialization.
    expect(original).not.toContain('domain_strategy')
    expect(original).not.toContain('balancer_strategy')
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

    const zeroProbe = parseSubscriptionProfileContent(JSON.stringify({ health_check: { probe_timeout: '0s' } }))
    expect(zeroProbe.success).toBe(false)
    if (!zeroProbe.success) expect(zeroProbe.error).toContain('Probe timeout must be greater than zero')
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

  it('carries the tri-state routing switch, not just the off position', () => {
    // The editor used to offer a plain on/off switch, which could express
    // `routing-enable: 0` and "say nothing" but never `routing-enable: 1`.
    const parse = (profile: object) => parseSubscriptionProfileContent(JSON.stringify(profile))
    expect(parse({ client: 'happ', routing_enabled: true }).success).toBe(true)
    expect(parse({ client: 'happ', routing_enabled: false }).success).toBe(true)

    const unset = parse({ client: 'happ' })
    expect(unset.success).toBe(true)
    if (!unset.success) return
    expect(unset.data.routing_enabled ?? null).toBe(null)
  })

  it('defaults the resolver and refuses one no client can express', () => {
    const defaults = parseSubscriptionProfileContent('{}')
    expect(defaults.success).toBe(true)
    if (!defaults.success) return
    expect(defaults.data.dns.servers).toEqual(['1.1.1.1'])

    const parse = (servers: string[]) => parseSubscriptionProfileContent(JSON.stringify({ dns: { servers } })).success
    expect(parse(['9.9.9.9', 'https://dns.quad9.net/dns-query'])).toBe(true)
    // Sing-box needs a host and a path to build a DoH server entry.
    expect(parse(['https://dns.quad9.net'])).toBe(false)
    expect(parse(['dns.quad9.net'])).toBe(false)
    // The backend requires at least one; an empty box must not reach it.
    expect(parse([])).toBe(false)
  })

  it('refuses the resolver forms the backend refuses', () => {
    const parse = (server: string) => parseSubscriptionProfileContent(JSON.stringify({ dns: { servers: [server] } })).success
    // Rejecting here is only worth doing if it matches ProfileDns exactly;
    // otherwise the operator trades an inline message for a raw 422 toast.
    expect(parse('tls://dns.example')).toBe(false)
    expect(parse('http://dns.example/dns-query')).toBe(false)
    // ip_address reads a leading zero as ambiguous octal and refuses it.
    expect(parse('01.1.1.1')).toBe(false)
    // The first thing an operator types once they learn a DoH port is allowed.
    expect(parse('1.1.1.1:53')).toBe(false)
    // A DoH port must survive, and so must the shapes that carry one badly.
    expect(parse('https://dns.example:8443/dns-query')).toBe(true)
    expect(parse('https://[2606:4700::1111]/dns-query')).toBe(true)
    // Everything the backend does accept still passes.
    expect(parse('9.9.9.9')).toBe(true)
    expect(parse('2606:4700:4700::1111')).toBe(true)
    expect(parse('https://dns.example/dns-query')).toBe(true)
  })

  it('keeps the balancer tuning the backend reads', () => {
    const result = parseSubscriptionProfileContent(JSON.stringify({ balancer_strategy: 'leastLoad', balancer_settings: { expected: 2, baselines: ['1500ms'] } }))
    expect(result.success).toBe(true)
    if (!result.success) return
    expect(result.data.balancer_settings).toEqual({ expected: 2, baselines: ['1500ms'] })

    const parse = (settings: object) => parseSubscriptionProfileContent(JSON.stringify({ balancer_settings: settings })).success
    // Xray parses a baseline as a duration; a bare number is dropped silently.
    expect(parse({ baselines: ['1500'] })).toBe(false)
    expect(parse({ expected: 0 })).toBe(false)
    // Both knobs are optional, and an absent object is the common case.
    expect(parse({})).toBe(true)
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

  it('round-trips advanced raw fields while editing server-group settings', () => {
    const result = parseSubscriptionProfileForEditing(
      JSON.stringify({
        pools: [{ id: 'primary' }],
        dns: { servers: ['9.9.9.9'] },
        routing_rules: [{ type: 'field', outboundTag: 'direct' }],
        domain_strategy: 'IPIfNonMatch',
        client: 'happ',
        routing_payload: 'happ://routing/off',
      }),
    )

    expect(result.success).toBe(true)
    if (!result.success) return
    const serialized = JSON.parse(serializeSubscriptionProfile({ ...result.data, balancer_strategy: 'roundRobin' }))
    expect(serialized.dns).toEqual({ servers: ['9.9.9.9'] })
    expect(serialized.routing_rules).toEqual([{ type: 'field', outboundTag: 'direct' }])
    expect(serialized.domain_strategy).toBe('IPIfNonMatch')
    expect(serialized.client).toBe('happ')
    expect(serialized.routing_payload).toBe('happ://routing/off')
  })
})
