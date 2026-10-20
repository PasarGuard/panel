import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getOutboundFormCapabilities } from '@pasarguard/xray-config-kit'
import { normalizeSettingsFromEditor } from '@/features/core-editor/kit/outbound-editor-json'
import {
  applyWireguardKernelTunChoice,
  invalidWireguardRemoteDns,
  migrateWireguardOutboundLegacySettings,
  WIREGUARD_OUTBOUND_FORM_KEYS,
  wireguardKernelTunChoice,
  wireguardOutboundSettingsIssues,
} from '@/features/core-editor/kit/wireguard-outbound-settings'

test('legacy kernelMode becomes noKernelTun', () => {
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: false, mtu: 1280 }), { mtu: 1280, noKernelTun: true })
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: true }), { noKernelTun: false })
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: false, noKernelTun: false }), { noKernelTun: false })
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: 'yes' }), {})
  const plain = { mtu: 1 }
  assert.equal(migrateWireguardOutboundLegacySettings(plain), plain)
})

test('kernel TUN choice reads and writes noKernelTun only', () => {
  assert.equal(wireguardKernelTunChoice({ noKernelTun: true }), 'userspace')
  assert.equal(wireguardKernelTunChoice({ noKernelTun: false }), 'kernel')
  assert.equal(wireguardKernelTunChoice({ kernelMode: false }), 'userspace')
  assert.equal(wireguardKernelTunChoice({ kernelMode: true }), 'kernel')
  assert.equal(wireguardKernelTunChoice({ noKernelTun: true, kernelMode: true }), 'userspace')
  assert.equal(wireguardKernelTunChoice({}), '__default__')
  assert.deepEqual(applyWireguardKernelTunChoice({ kernelMode: false, mtu: 1 }, 'kernel'), { mtu: 1, noKernelTun: false })
  assert.deepEqual(applyWireguardKernelTunChoice({ noKernelTun: true }, '__default__'), {})
  assert.deepEqual(applyWireguardKernelTunChoice({}, 'userspace'), { noKernelTun: true })
})

test('remoteDNS must be IP literals', () => {
  assert.deepEqual(invalidWireguardRemoteDns(['1.1.1.1', '2606:4700:4700::1111', 'dns.google', '1.1.1.1:53', '[2606:4700::1111]', '']), ['dns.google', '1.1.1.1:53', '[2606:4700::1111]'])
  // Xray reads remoteDNS as []string, so a value that is not a list fails to load even when it is an IP.
  assert.deepEqual(invalidWireguardRemoteDns(' 8.8.8.8 '), ['8.8.8.8'])
  assert.deepEqual(invalidWireguardRemoteDns('dns.google'), ['dns.google'])
  assert.deepEqual(invalidWireguardRemoteDns(53), ['53'])
  assert.deepEqual(invalidWireguardRemoteDns(undefined), [])
  assert.deepEqual(invalidWireguardRemoteDns(null), [])
})

test('outbound settings issues flag DNS hostnames, a non-list remoteDNS and bad reserved', () => {
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: ['dns.google'], reserved: [1, 2] }), [{ field: 'remoteDNS', values: ['dns.google'] }, { field: 'reserved' }])
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: ['1.1.1.1'], reserved: 'AQID' }), [])
  assert.deepEqual(wireguardOutboundSettingsIssues({ reserved: '1,2,3' }), [{ field: 'reserved' }])
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: '8.8.8.8' }), [{ field: 'remoteDNS', values: ['8.8.8.8'] }])
})

test('dedicated WireGuard outbound UI covers every kit settings key', () => {
  const keys = getOutboundFormCapabilities().settingsFieldOrderByProtocol['wireguard'] ?? []
  assert.ok(keys.length > 0)
  for (const key of keys) assert.ok((WIREGUARD_OUTBOUND_FORM_KEYS as readonly string[]).includes(key), key)
})

test('normalizeSettingsFromEditor migrates WireGuard legacy keys', () => {
  assert.deepEqual(normalizeSettingsFromEditor('wireguard', { kernelMode: false, mtu: 1280 }), { mtu: 1280, noKernelTun: true })
  assert.deepEqual(normalizeSettingsFromEditor('wireguard', { mtu: 1280 }), { mtu: 1280 })
})
