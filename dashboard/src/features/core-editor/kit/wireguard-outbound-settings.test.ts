import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getOutboundFormCapabilities } from '@pasarguard/xray-config-kit'
import { normalizeSettingsFromEditor } from '@/features/core-editor/kit/outbound-editor-json'
import {
  applyWireguardKernelTunChoice,
  applyWireguardOutboundReservedInput,
  invalidWireguardRemoteDns,
  migrateWireguardOutboundLegacySettings,
  WIREGUARD_OUTBOUND_FORM_KEYS,
  wireguardKernelTunChoice,
  wireguardOutboundIssueMessage,
  wireguardOutboundSettingsIssues,
} from '@/features/core-editor/kit/wireguard-outbound-settings'

const t = (key: string, options?: Record<string, unknown>): string => String(options?.defaultValue ?? key).replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name]))

test('legacy kernelMode becomes noKernelTun', () => {
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: false, mtu: 1280 }), { mtu: 1280, noKernelTun: true })
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: true }), { noKernelTun: false })
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: false, noKernelTun: false }), { noKernelTun: false })
  assert.deepEqual(migrateWireguardOutboundLegacySettings({ kernelMode: true, noKernelTun: 'false' }), { noKernelTun: false })
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
  assert.deepEqual(invalidWireguardRemoteDns(['1.1.1.1', '2606:4700:4700::1111', 'dns.google', '1.1.1.1:53', '[2606:4700::1111]', '']), ['"dns.google"', '"1.1.1.1:53"', '"[2606:4700::1111]"', '""'])
  // Xray passes each raw entry to netip.MustParseAddr, so padded entries panic the core too.
  assert.deepEqual(invalidWireguardRemoteDns([' 1.1.1.1', '8.8.8.8', 53, {}]), ['" 1.1.1.1"', '53', '{}'])
  // Xray reads remoteDNS as []string, so a value that is not a list fails to load even when it is an IP.
  assert.deepEqual(invalidWireguardRemoteDns(' 8.8.8.8 '), ['" 8.8.8.8 "'])
  assert.deepEqual(invalidWireguardRemoteDns('dns.google'), ['"dns.google"'])
  assert.deepEqual(invalidWireguardRemoteDns(53), ['53'])
  assert.deepEqual(invalidWireguardRemoteDns(undefined), [])
  assert.deepEqual(invalidWireguardRemoteDns(null), [])
})

test('the local DNS sentinel passes only as a single entry for a known target before v26.9.30', () => {
  for (const version of ['v26.9.29', 'v26.9.9', '26.9.9', 'v26.9.8', '26.3.27']) {
    assert.deepEqual(invalidWireguardRemoteDns(['local'], version), [])
    assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: ['local'], mtu: 1400 }, version), [])
  }
  // Xray v26.9.30 and newer panic at startup on "local"; an unknown target counts as the newest Xray.
  for (const version of [undefined, '', 'custom', 'V26.9.9', 'v26.9.9-rc1', ' v26.9.9', 'v26.9.30', '26.10.1', '27.1.1']) {
    assert.deepEqual(invalidWireguardRemoteDns(['local'], version), ['"local"'])
    assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: ['local'] }, version), [{ field: 'remoteDNS', values: ['"local"'], notList: false }])
  }
  assert.deepEqual(invalidWireguardRemoteDns(['local', '1.1.1.1'], 'v26.9.9'), ['"local"'])
  assert.deepEqual(invalidWireguardRemoteDns([' local '], 'v26.9.9'), ['" local "'])
  assert.deepEqual(invalidWireguardRemoteDns('local', 'v26.9.9'), ['"local"'])
})

test('outbound settings issues flag DNS hostnames, a non-list remoteDNS and bad reserved', () => {
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: ['dns.google'], reserved: [1, 2] }), [{ field: 'remoteDNS', values: ['"dns.google"'], notList: false }, { field: 'reserved' }])
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: ['1.1.1.1'], reserved: 'AQID' }), [])
  assert.deepEqual(wireguardOutboundSettingsIssues({ reserved: '1,2,3' }), [{ field: 'reserved' }])
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: '8.8.8.8' }), [{ field: 'remoteDNS', values: ['"8.8.8.8"'], notList: true }])
  assert.deepEqual(wireguardOutboundSettingsIssues({ remoteDNS: [' 1.1.1.1', ''] }), [{ field: 'remoteDNS', values: ['" 1.1.1.1"', '""'], notList: false }])
})

test('reserved input writes the byte list, removes the key when empty and keeps unparsable text so Modify stays blocked', () => {
  const base = { mtu: 1280, reserved: [9, 9, 9] }
  assert.deepEqual(applyWireguardOutboundReservedInput(base, '1,2,3'), { mtu: 1280, reserved: [1, 2, 3] })
  assert.deepEqual(applyWireguardOutboundReservedInput(base, '[1, 2, 3]'), { mtu: 1280, reserved: [1, 2, 3] })
  assert.deepEqual(applyWireguardOutboundReservedInput(base, ''), { mtu: 1280 })
  assert.deepEqual(applyWireguardOutboundReservedInput(base, '  '), { mtu: 1280 })
  assert.deepEqual(applyWireguardOutboundReservedInput(base, '1,2'), { mtu: 1280, reserved: '1,2' })
  assert.deepEqual(applyWireguardOutboundReservedInput(base, '1, 2, 300'), { mtu: 1280, reserved: '1, 2, 300' })
  assert.deepEqual(base, { mtu: 1280, reserved: [9, 9, 9] })
  assert.deepEqual(wireguardOutboundSettingsIssues(applyWireguardOutboundReservedInput(base, '1,2')), [{ field: 'reserved' }])
})

test('a typed 4-character base64 reserved text is stored raw and read as three bytes', () => {
  const next = applyWireguardOutboundReservedInput({ mtu: 1280 }, 'AQID')
  assert.deepEqual(next, { mtu: 1280, reserved: 'AQID' })
  assert.deepEqual(wireguardOutboundSettingsIssues(next), [])
})

test('issue messages quote each bad DNS entry and cover a non-list remoteDNS and bad reserved', () => {
  const messages = (settings: Record<string, unknown>) => wireguardOutboundSettingsIssues(settings).map(issue => wireguardOutboundIssueMessage(t, issue))
  assert.deepEqual(messages({ remoteDNS: [' 1.1.1.1', '', 'dns.google', '8.8.8.8'], reserved: '1,2' }), [
    'DNS servers must be IP addresses: " 1.1.1.1", "", "dns.google"',
    'Reserved must be three numbers from 0 to 255, for example 1, 2, 3.',
  ])
  assert.deepEqual(messages({ remoteDNS: '8.8.8.8' }), ['DNS servers must be a list of IP addresses. Edit the list to save it as one.'])
  assert.deepEqual(messages({ remoteDNS: ['1.1.1.1'], reserved: [1, 2, 3] }), [])
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
