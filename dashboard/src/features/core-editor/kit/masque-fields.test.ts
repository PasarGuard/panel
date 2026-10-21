import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getInboundFormCapabilities, getOutboundFormCapabilities } from '@pasarguard/xray-config-kit'
import {
  applyMasqueClientAuthMode,
  MASQUE_OUTBOUND_FORM_KEYS,
  MASQUE_TRANSPORT_FORM_KEYS,
  masqueAlpnForMode,
  masqueClientAuthMode,
  masqueHttpMode,
  masqueShownFields,
  parseMasqueMtuInput,
} from '@/features/core-editor/kit/masque-fields'

test('parseMasqueMtuInput accepts 0 or 1280 to 65535', () => {
  assert.deepEqual(parseMasqueMtuInput(''), { ok: true, value: undefined })
  assert.deepEqual(parseMasqueMtuInput('0'), { ok: true, value: 0 })
  assert.deepEqual(parseMasqueMtuInput(' 1280 '), { ok: true, value: 1280 })
  assert.deepEqual(parseMasqueMtuInput('65535'), { ok: true, value: 65535 })
  for (const raw of ['1279', '65536', '1400.5', '1e3', '-1', 'abc']) assert.deepEqual(parseMasqueMtuInput(raw), { ok: false }, raw)
})

test('masqueHttpMode mirrors Xray serverVersions and usesHTTP2', () => {
  for (const [alpn, mode] of [
    [undefined, 'h3'],
    [['h3'], 'h3'],
    [['h2'], 'h2'],
    [['h2', 'http/1.1'], 'h2'],
    [['h3', 'h2'], 'both'],
    [['http/1.1'], 'h3'],
    ['h3,h2', 'both'],
  ] as const)
    assert.equal(masqueHttpMode(alpn, 'server'), mode, JSON.stringify(alpn))
  for (const [alpn, mode] of [
    [undefined, 'h3'],
    [['h2'], 'h2'],
    [['h3', 'h2'], 'h3'],
    [['h2', 'http/1.1'], 'h2'],
  ] as const)
    assert.equal(masqueHttpMode(alpn, 'client'), mode, JSON.stringify(alpn))
  assert.deepEqual(masqueAlpnForMode('both'), ['h3', 'h2'])
  assert.deepEqual(masqueAlpnForMode('h3'), ['h3'])
  assert.deepEqual(masqueAlpnForMode('h2'), ['h2'])
})

test('client auth modes replace each other', () => {
  const warp = { privateKey: 'k', publicKey: 'p', address: ['172.16.0.2/32'] }
  assert.equal(masqueClientAuthMode({}), 'none')
  assert.equal(masqueClientAuthMode({ user: 'alice' }), 'basic')
  assert.equal(masqueClientAuthMode({ pass: 'secret' }), 'basic')
  assert.equal(masqueClientAuthMode({ user: '', pass: '' }), 'none')
  assert.equal(masqueClientAuthMode({ warp: { address: [] }, user: 'alice' }), 'warp')
  assert.deepEqual(applyMasqueClientAuthMode({ path: '/p', warp, user: 'u', pass: 'p' }, 'basic'), { path: '/p', user: 'u', pass: 'p' })
  assert.deepEqual(applyMasqueClientAuthMode({ path: '/p', user: 'u', pass: 'p' }, 'warp'), { path: '/p', warp: { privateKey: '', publicKey: '', address: [] } })
  assert.deepEqual(applyMasqueClientAuthMode({ warp, user: 'u' }, 'warp'), { warp })
  assert.deepEqual(applyMasqueClientAuthMode({ host: 'h', warp, user: 'u', pass: 'p' }, 'none'), { host: 'h' })
})

test('dedicated MASQUE outbound UI covers every kit settings key', () => {
  const keys = getOutboundFormCapabilities().settingsFieldOrderByProtocol['masque'] ?? []
  assert.ok(keys.length > 0)
  for (const key of keys) assert.ok((MASQUE_OUTBOUND_FORM_KEYS as readonly string[]).includes(key), key)
})

test('dedicated MASQUE transport UI covers every kit masque transport key, xmux included', () => {
  const keys = getInboundFormCapabilities().transportSettingsFieldOrderByType['masque'] ?? []
  assert.ok(keys.includes('xmux'))
  for (const key of keys) assert.ok((MASQUE_TRANSPORT_FORM_KEYS as readonly string[]).includes(key), key)
  // Auth mode switches leave xmux alone.
  const xmux = { maxConcurrency: '16-32' }
  assert.deepEqual(applyMasqueClientAuthMode({ user: 'u', pass: 'p', xmux }, 'warp'), { xmux, warp: { privateKey: '', publicKey: '', address: [] } })
  assert.deepEqual(applyMasqueClientAuthMode({ warp: { address: [] }, xmux }, 'none'), { xmux })
})

test('masqueShownFields: the client box leaves security and transport to the stream accordion', () => {
  const client = masqueShownFields('client')
  for (const key of [...MASQUE_OUTBOUND_FORM_KEYS, ...MASQUE_TRANSPORT_FORM_KEYS, 'warp.privateKey', 'warp.publicKey', 'warp.address', 'security', 'transport']) assert.ok(client.includes(key), key)
  for (const key of ['mux', 'clients']) assert.ok(!client.includes(key), key)
  const server = masqueShownFields('server')
  assert.deepEqual([...server].sort(), ['address', 'headers', 'host', 'mtu', 'path', 'remoteDNS'])
})
