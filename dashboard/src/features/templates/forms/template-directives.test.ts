import { describe, expect, it } from 'bun:test'

import {
  hasServerGroupDirective,
  insertExampleOnOwnLine,
  mergeXrayServerGroupDirective,
  SERVER_GROUP_EXAMPLES,
  supportsServerGroups,
  XRAY_SERVER_GROUP_DIRECTIVE,
  xrayDirectiveCopiesAllServersPerHost,
} from './template-directives'

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
    expect(hasServerGroupDirective('mode: rule\n  # pasarguard: put groups here')).toBe(false)
    expect(hasServerGroupDirective('{"remarks": "pasarguard: DE"}')).toBe(false)
  })

  it('detects the directive as a YAML list item and in flow mappings', () => {
    expect(hasServerGroupDirective('groups:\n- pasarguard: {}')).toBe(true)
    expect(hasServerGroupDirective('- {name: DE, pasarguard: {select: {}}}')).toBe(true)
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

  it('inserts the Xray example in single mode', () => {
    expect(XRAY_SERVER_GROUP_DIRECTIVE.mode).toBe('single')
    expect(xrayDirectiveCopiesAllServersPerHost(JSON.stringify({ pasarguard: XRAY_SERVER_GROUP_DIRECTIVE }))).toBe(false)
  })

  it('warns about per-host configs that copy every server', () => {
    expect(xrayDirectiveCopiesAllServersPerHost('{"pasarguard": {"mode": "per_host", "inject": [{"select": {}}]}}')).toBe(true)
    expect(xrayDirectiveCopiesAllServersPerHost('{"pasarguard": {"inject": [{"tag_prefix": "p"}]}}')).toBe(true)
    expect(xrayDirectiveCopiesAllServersPerHost('{"pasarguard": {"inject": [{"select": {"host_ids": [1]}}]}}')).toBe(false)
    expect(xrayDirectiveCopiesAllServersPerHost('{"pasarguard": {"mode": "single", "inject": [{}]}}')).toBe(false)
    expect(xrayDirectiveCopiesAllServersPerHost('{"outbounds": []}')).toBe(false)
    expect(xrayDirectiveCopiesAllServersPerHost('{"pasarguard": ')).toBe(false)
  })

  it('puts an inserted example on lines of its own', () => {
    const example = 'proxy-groups:\n- name: DE'
    expect(insertExampleOnOwnLine('mode: rule\nrules: []\n', 0, example)).toBe(`${example}\nmode: rule\nrules: []\n`)
    expect(insertExampleOnOwnLine('mode: rule\nrules: []\n', 2, example)).toBe(`mode: rule\n${example}\nrules: []\n`)
    expect(insertExampleOnOwnLine('mode: rule\nrules: []\n', 11, example)).toBe(`mode: rule\n${example}\nrules: []\n`)
    expect(insertExampleOnOwnLine('mode: rule', 4, example)).toBe(`mode: rule\n${example}\n`)
    expect(insertExampleOnOwnLine('mode: rule', 10, example)).toBe(`mode: rule\n${example}\n`)
    expect(insertExampleOnOwnLine('mode: rule\n', 11, example)).toBe(`mode: rule\n${example}\n`)
    expect(insertExampleOnOwnLine('', 0, example)).toBe(`${example}\n`)
  })

  it('does not touch invalid JSON, non-objects or an existing directive', () => {
    expect(mergeXrayServerGroupDirective('{"log": ').status).toBe('invalid')
    expect(mergeXrayServerGroupDirective('[1, 2]').status).toBe('invalid')
    expect(mergeXrayServerGroupDirective('null').status).toBe('invalid')
    expect(mergeXrayServerGroupDirective('{"pasarguard": {"mode": "single"}}').status).toBe('exists')
  })
})
