import { describe, expect, test } from 'bun:test'
import { createManagedProtocolPreset } from '../src/lib/managed-protocol-preset'

describe('managed protocol preset', () => {
  test('contains all protocols with unique ports, tags and paths', () => {
    const config = createManagedProtocolPreset()
    expect(config.inbounds.map(i => i.protocol)).toEqual(['vless', 'vmess', 'trojan'])
    expect(new Set(config.inbounds.map(i => i.port)).size).toBe(3)
    expect(new Set(config.inbounds.map(i => i.tag)).size).toBe(3)
    expect(new Set(config.inbounds.map(i => i.streamSettings.wsSettings.path)).size).toBe(3)
    for (const inbound of config.inbounds) {
      expect(inbound.listen).toBe('127.0.0.1')
      expect(inbound.settings.clients).toEqual([])
      expect(inbound.streamSettings.network).toBe('ws')
    }
    expect(config.inbounds[0].settings.decryption).toBe('none')
  })
  test('creates fresh objects and has no undeclared geoip asset dependency', () => {
    const first = createManagedProtocolPreset()
    first.inbounds[0].port = 12345
    expect(createManagedProtocolPreset().inbounds[0].port).toBe(10001)
    expect(JSON.stringify(createManagedProtocolPreset())).not.toContain('geoip:')
  })
})


test('dashboard preset matches the validated CLI generator', () => {
  const script = new URL('../../scripts/generate_xray_config.py', import.meta.url).pathname
  const generated = Bun.spawnSync(['python3', script, '--behind-tls-proxy'])
  expect(generated.exitCode).toBe(0)
  expect(createManagedProtocolPreset()).toEqual(JSON.parse(new TextDecoder().decode(generated.stdout)))
})
