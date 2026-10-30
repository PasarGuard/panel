import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInboundForProtocol, getInboundFormCapabilities, getOutboundFormCapabilities } from '@pasarguard/xray-config-kit'
import type { Inbound, Security } from '@pasarguard/xray-config-kit'
import {
  applyMasqueClientAuthMode,
  hasMasqueClientOnlySettings,
  MASQUE_CLIENT_ONLY_FIELDS,
  MASQUE_OUTBOUND_FORM_KEYS,
  MASQUE_TRANSPORT_FORM_KEYS,
  masqueAlpnForMode,
  masqueClientAuthMode,
  masqueClientShowsBasicAuthFields,
  masqueHttpMode,
  masqueInboundTlsSecurity,
  masqueShownFields,
  parseMasqueMtuInput,
  removeMasqueClientOnlySettings,
} from '@/features/core-editor/kit/masque-fields'
import { blockingStreamFieldIssues, streamFieldIssuesForInbound } from '@/features/core-editor/kit/stream-form-fields'
import type { StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'

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
    // Xray splits an ALPN string on "," without trimming: " h2" is not h2.
    ['h3, h2', 'h3'],
  ] as const)
    assert.equal(masqueHttpMode(alpn, 'server'), mode, JSON.stringify(alpn))
  for (const [alpn, mode] of [
    [undefined, 'h3'],
    [['h2'], 'h2'],
    [['h3', 'h2'], 'h3'],
    [['h2', 'http/1.1'], 'h2'],
    ['h2,h3', 'h3'],
    ['h2, h3', 'h2'],
  ] as const)
    assert.equal(masqueHttpMode(alpn, 'client'), mode, JSON.stringify(alpn))
  assert.deepEqual(masqueAlpnForMode('both'), ['h3', 'h2'])
  assert.deepEqual(masqueAlpnForMode('h3'), ['h3'])
  assert.deepEqual(masqueAlpnForMode('h2'), ['h2'])
})

test('a MASQUE inbound turning to TLS keeps the HTTP version its select showed', () => {
  // Without TLS the select reads no ALPN; the new TLS settings write that version, not a different default.
  const shown = masqueHttpMode(undefined, 'server')
  const securities: Security[] = [{ type: 'none' }, { type: 'reality', serverNames: ['a.example'], privateKey: 'k', shortIds: [''], target: 'a.example:443' }]
  for (const security of securities) {
    const next = masqueInboundTlsSecurity(security)
    assert.deepEqual(next, { type: 'tls', serverName: '', alpn: ['h3'] }, security.type)
    assert.equal(masqueHttpMode(next.alpn, 'server'), shown, security.type)
  }
  // A TLS security stays as it is, with its own HTTP version.
  const stored = { type: 'tls' as const, serverName: 'mq.example', alpn: ['h2' as const] }
  assert.equal(masqueInboundTlsSecurity(stored), stored)
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

test('masqueShownFields: the client box shows user and pass only with Basic auth and warp only with WARP', () => {
  // The outbound stream accordion shows `security` and `transport` under its own selects.
  const always = [...MASQUE_OUTBOUND_FORM_KEYS, 'path', 'host', 'headers', 'xmux', 'security', 'transport']
  const sorted = (keys: readonly string[]) => [...keys].sort()
  assert.deepEqual(sorted(masqueShownFields('client', 'none')), sorted(always))
  assert.deepEqual(sorted(masqueShownFields('client', 'basic')), sorted([...always, 'user', 'pass']))
  assert.deepEqual(sorted(masqueShownFields('client', 'warp')), sorted([...always, 'warp', 'warp.privateKey', 'warp.publicKey', 'warp.address']))
  // Every transport key the form owns is shown in some mode.
  const anyMode = new Set((['none', 'basic', 'warp'] as const).flatMap(mode => masqueShownFields('client', mode)))
  for (const key of MASQUE_TRANSPORT_FORM_KEYS) assert.ok(anyMode.has(key), key)
  for (const key of ['mux', 'clients', 'mtu']) assert.ok(!anyMode.has(key), key)
})

test('masqueShownFields: WARP with a stored user or pass also shows the user and password inputs', () => {
  // Xray refuses user/pass next to warp (the kit's WARP_AUTH_CONFLICT), so the inputs stay until both are cleared.
  const warp = { privateKey: 'k', publicKey: 'p', address: [] }
  const sorted = (keys: readonly string[]) => [...keys].sort()
  const warpOnly = sorted(masqueShownFields('client', 'warp', { warp }))
  assert.ok(!warpOnly.includes('user') && !warpOnly.includes('pass'))
  for (const stale of [{ user: 'a:b' }, { pass: 'secret' }, { user: 'alice', pass: 'secret' }]) {
    const transport = { warp, ...stale }
    assert.equal(masqueClientAuthMode(transport), 'warp')
    assert.equal(masqueClientShowsBasicAuthFields(transport, 'warp'), true, JSON.stringify(stale))
    assert.deepEqual(sorted(masqueShownFields('client', 'warp', transport)), sorted([...warpOnly, 'user', 'pass']), JSON.stringify(stale))
  }
  assert.equal(masqueClientShowsBasicAuthFields({ warp, user: '', pass: '' }, 'warp'), false)
  assert.equal(masqueClientShowsBasicAuthFields({}, 'basic'), true)
  assert.equal(masqueClientShowsBasicAuthFields({ user: 'alice' }, 'none'), false)
  // The server box never has user or password inputs; it lists those issues by its remove action.
  assert.deepEqual(masqueShownFields('server', 'warp', { warp, user: 'u' }), masqueShownFields('server'))
})

test('masqueShownFields: the server box shows the client-only fields next to their remove action', () => {
  assert.deepEqual([...MASQUE_CLIENT_ONLY_FIELDS].sort(), ['pass', 'user', 'warp', 'warp.address', 'warp.privateKey', 'warp.publicKey', 'xmux'])
  assert.deepEqual([...masqueShownFields('server')].sort(), ['address', 'headers', 'host', 'mtu', 'path', 'remoteDNS', ...MASQUE_CLIENT_ONLY_FIELDS].sort())
  for (const mode of ['none', 'basic', 'warp'] as const) assert.deepEqual(masqueShownFields('server', mode), masqueShownFields('server'))
})

test('client-only settings on a MASQUE server: detected like the kit does and removable', () => {
  assert.equal(hasMasqueClientOnlySettings({ type: 'masque', path: '/p', host: 'h', headers: { 'X-A': 'b' } }), false)
  assert.equal(hasMasqueClientOnlySettings({ user: '', pass: null, xmux: {} }), false)
  for (const transport of [{ user: 'u' }, { pass: 'p' }, { warp: {} }, { xmux: { maxConcurrency: '16-32' } }]) assert.equal(hasMasqueClientOnlySettings(transport), true, JSON.stringify(transport))

  const transport = {
    type: 'masque',
    path: '/p',
    host: 'example.com',
    user: 'a:b',
    pass: 'p',
    warp: { privateKey: 'x', publicKey: 'y', address: [] },
    xmux: { maxConnections: 1, maxConcurrency: 2 },
  }
  const inbound = { ...createDefaultInboundForProtocol({ protocol: 'masque', clientDefaults: 'empty' }), tag: 'MQ', port: 443, transport } as unknown as Inbound
  const clientOnly = (issues: readonly StreamFieldIssue[]) => issues.filter(issue => (MASQUE_CLIENT_ONLY_FIELDS as readonly string[]).includes(issue.field))
  const before = streamFieldIssuesForInbound(inbound)
  // Xray checks these on the server too, so some of them block; every one lands on a field the server box shows.
  assert.deepEqual([...new Set(clientOnly(before).map(issue => issue.field))].sort(), [...MASQUE_CLIENT_ONLY_FIELDS].sort())
  assert.ok(blockingStreamFieldIssues(before).length > 0)
  for (const issue of before) assert.ok(masqueShownFields('server').includes(issue.field), issue.field)

  const cleaned = removeMasqueClientOnlySettings(transport)
  assert.deepEqual(cleaned, { type: 'masque', path: '/p', host: 'example.com' })
  assert.equal(transport.user, 'a:b', 'input not mutated')
  assert.equal(hasMasqueClientOnlySettings(cleaned), false)
  const after = streamFieldIssuesForInbound({ ...inbound, transport: cleaned } as unknown as Inbound)
  assert.deepEqual(clientOnly(after), [])
  assert.deepEqual(blockingStreamFieldIssues(after), [])
})
