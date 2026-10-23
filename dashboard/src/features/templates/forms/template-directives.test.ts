import { describe, expect, it } from 'bun:test'

import { hasServerGroupDirective, mergeXrayServerGroupDirective, SERVER_GROUP_EXAMPLES, supportsServerGroups, XRAY_SERVER_GROUP_DIRECTIVE } from './template-directives'

describe('server group directive', () => {
  it('detects the directive in JSON and YAML templates', () => {
    expect(hasServerGroupDirective('{"outbounds": [], "pasarguard": {"mode": "single"}}')).toBe(true)
    expect(hasServerGroupDirective('proxy-groups:\n- name: PROXY\n  pasarguard: {include-proxies: true}')).toBe(true)
    expect(Object.values(SERVER_GROUP_EXAMPLES).every(hasServerGroupDirective)).toBe(true)
  })

  it('ignores templates without the directive', () => {
    expect(hasServerGroupDirective('{"remarks": "PasarGuard", "outbounds": []}')).toBe(false)
    expect(hasServerGroupDirective('{"remarks": "pasarguard"}')).toBe(false)
    expect(hasServerGroupDirective('')).toBe(false)
    expect(hasServerGroupDirective(undefined)).toBe(false)
  })

  it('is offered only for subscription templates', () => {
    expect(supportsServerGroups('xray_subscription')).toBe(true)
    expect(supportsServerGroups('singbox_subscription')).toBe(true)
    expect(supportsServerGroups('clash_subscription')).toBe(true)
    expect(supportsServerGroups('user_agent')).toBe(false)
    expect(supportsServerGroups('grpc_user_agent')).toBe(false)
  })

  it('merges the directive into an Xray template and keeps the rest', () => {
    const result = mergeXrayServerGroupDirective('{"log": {"loglevel": "warning"}, "outbounds": []}')
    expect(result.status).toBe('merged')
    if (result.status !== 'merged') return
    expect(JSON.parse(result.content)).toEqual({ log: { loglevel: 'warning' }, outbounds: [], pasarguard: XRAY_SERVER_GROUP_DIRECTIVE })
  })

  it('does not touch invalid JSON, non-objects or an existing directive', () => {
    expect(mergeXrayServerGroupDirective('{"log": ').status).toBe('invalid')
    expect(mergeXrayServerGroupDirective('[1, 2]').status).toBe('invalid')
    expect(mergeXrayServerGroupDirective('null').status).toBe('invalid')
    expect(mergeXrayServerGroupDirective('{"pasarguard": {"mode": "single"}}').status).toBe('exists')
  })
})
