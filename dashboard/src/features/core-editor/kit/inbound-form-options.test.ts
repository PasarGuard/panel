import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInbound, getInboundFormCapabilities } from '@pasarguard/xray-config-kit'
import { getInboundSecuritySelectOptions, getInboundTransportSelectOptions, inboundTransportHasDedicatedForm, kitBuildsInboundTransport } from '@/features/core-editor/kit/inbound-form-options'

const caps = getInboundFormCapabilities()
const BASE = ['tcp', 'grpc', 'xhttp', 'ws', 'httpupgrade', 'kcp']
// Xray v26.10.17 allows the xdrive transport on VLESS inbounds only.
const VLESS_ALL = [...BASE, 'xdrive']

test('transport choices come from the kit per protocol', () => {
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vless', securityType: 'none' }), VLESS_ALL)
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vless', securityType: 'tls' }), VLESS_ALL)
  for (const protocol of ['vmess', 'trojan', 'shadowsocks'] as const) assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol, securityType: 'none' }), BASE, protocol)
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vmess', securityType: 'tls' }), BASE)
})

test('REALITY keeps xdrive out and a stored transport stays selectable', () => {
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vless', securityType: 'reality' }), ['tcp', 'grpc', 'xhttp'])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vless', securityType: 'reality', currentTransportType: 'xdrive' }), ['xdrive', 'tcp', 'grpc', 'xhttp'])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'trojan', securityType: 'reality', currentTransportType: 'xdrive' }), ['xdrive', 'tcp', 'grpc', 'xhttp'])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vmess', securityType: 'none', currentTransportType: 'xdrive' }), ['xdrive', ...BASE])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'vless', securityType: 'none', currentTransportType: 'masque' }), ['masque', ...VLESS_ALL])
})

test('fixed-transport protocols get no transport picker', () => {
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'masque', securityType: 'tls', currentTransportType: 'masque' }), [])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'hysteria', securityType: 'tls', currentTransportType: 'hysteria' }), [])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'wireguard' }), [])
  assert.deepEqual(getInboundTransportSelectOptions(caps, { protocol: 'unmanaged' }), [])
})

test('an older Xray release offers no xdrive', () => {
  assert.deepEqual(getInboundTransportSelectOptions(getInboundFormCapabilities({ xrayVersion: 'v26.9.8' }), { protocol: 'vless', securityType: 'none' }), BASE)
})

test('security choices come from the kit and keep the stored value', () => {
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'vless'), ['none', 'tls', 'reality'])
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'vmess'), ['none', 'tls'])
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'vmess', 'reality'), ['reality', 'none', 'tls'])
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'hysteria'), ['tls'])
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'masque', 'tls'), ['tls'])
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'masque', 'none'), ['none', 'tls'])
  assert.deepEqual(getInboundSecuritySelectOptions(caps, 'wireguard'), [])
})

test('dedicated transport forms', () => {
  for (const type of ['xdrive', 'masque', 'hysteria']) assert.equal(inboundTransportHasDedicatedForm(type), true, type)
  for (const type of ['tcp', 'ws', undefined]) assert.equal(inboundTransportHasDedicatedForm(type), false, String(type))
})

test('kitBuildsInboundTransport says which stored transports the kit can rebuild for vmess, vless, trojan and shadowsocks', () => {
  // The security handler rebuilds only these protocols; hysteria and masque keep their fixed transport.
  for (const protocol of ['vmess', 'vless', 'trojan', 'shadowsocks'] as const) {
    for (const transport of [...BASE, 'xdrive', 'masque'] as const) {
      let built = true
      try {
        createDefaultInbound({ protocol, transport, clientDefaults: 'empty' } as Parameters<typeof createDefaultInbound>[0])
      } catch {
        built = false
      }
      assert.equal(kitBuildsInboundTransport(protocol, transport), built, `${protocol} ${transport}`)
    }
  }
  assert.equal(kitBuildsInboundTransport('vless', 'xdrive'), true)
  assert.equal(kitBuildsInboundTransport('vmess', 'xdrive'), false)
  assert.equal(kitBuildsInboundTransport('vless', 'masque'), false)
})
