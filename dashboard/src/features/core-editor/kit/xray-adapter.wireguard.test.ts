import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInboundForProtocol } from '@pasarguard/xray-config-kit'
import type { Inbound, Profile, RawPatch } from '@pasarguard/xray-config-kit'
import { importRawToProfile, profileToPersistedConfig, validateProfileForPersist } from '@/features/core-editor/kit/xray-adapter'
import { normalizeSettingsFromEditor } from '@/features/core-editor/kit/outbound-editor-json'
import { wireguardOutboundSettingsIssues } from '@/features/core-editor/kit/wireguard-outbound-settings'

const SK = 'yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk='
const PEER = { publicKey: 'bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=', endpoint: 'engage.cloudflareclient.com:2408', allowedIPs: ['0.0.0.0/0'] }
const VLESS = { tag: 'VLESS TCP', listen: '0.0.0.0', port: 2053, protocol: 'vless', settings: { clients: [], decryption: 'none' }, streamSettings: { network: 'tcp', security: 'none' } }
const WG = { tag: 'WG', listen: '0.0.0.0', port: 51820, protocol: 'wireguard', settings: { secretKey: SK, address: ['10.8.0.1/24'], mtu: 1420, noKernelTun: true, reserved: [1, 2, 3] } }
const DIRECT = { protocol: 'freedom', tag: 'DIRECT' }
const WARP = {
  protocol: 'wireguard',
  tag: 'WARP',
  settings: { secretKey: SK, address: ['172.16.0.2/32'], mtu: 1280, workers: 2, domainStrategy: 'ForceIPv4', kernelMode: false, remoteDNS: ['1.1.1.1'], reserved: [1, 2, 3], peers: [PEER] },
}
const probe = { log: { loglevel: 'warning' }, inbounds: [VLESS, WG], outbounds: [DIRECT, WARP] }
// Without WARP: kit 0.3.8 still flags WARP workers/remoteDNS, which would hide the result of persist validation.
const minimal = { inbounds: [VLESS], outbounds: [DIRECT] }
const byTag = (list: unknown, tag: string) => (list as Record<string, unknown>[]).find(item => item.tag === tag) as Record<string, unknown>
const withInbound = (raw: typeof minimal, inbound: Record<string, unknown>) => ({ ...structuredClone(raw), inbounds: [...structuredClone(raw.inbounds), inbound] })
const editInbound = (profile: Profile, tag: string, patch: Record<string, unknown>): Profile => ({
  ...profile,
  inbounds: profile.inbounds.map(ib => (ib.tag === tag ? ({ ...ib, ...patch } as Inbound) : ib)),
})
const NOISE = { udp: [{ type: 'noise', settings: { noise: [{ type: 'str', packet: 'abc' }] } }] }

test('probe core round trip stays equal', () => {
  const { profile } = importRawToProfile(structuredClone(probe))
  assert.deepEqual(profileToPersistedConfig(profile), probe)
})

test('an edited WireGuard inbound compiles without network/security', () => {
  const { profile } = importRawToProfile(structuredClone(probe))
  const wg = byTag(profileToPersistedConfig(editInbound(profile, 'WG', { mtu: 1400 })).inbounds, 'WG')
  assert.equal((wg.settings as Record<string, unknown>).mtu, 1400)
  assert.equal('streamSettings' in wg, false)
})

test('WireGuard inbound keeps only sockopt and finalmask', () => {
  const raw = withInbound(minimal, {
    tag: 'WGS',
    port: 51821,
    protocol: 'wireguard',
    settings: { secretKey: SK, address: ['10.9.0.1/24'] },
    streamSettings: { network: 'tcp', security: 'none', sockopt: { mark: 255 }, finalmask: NOISE },
  })
  const { profile } = importRawToProfile(raw)
  assert.deepEqual(byTag(profileToPersistedConfig(profile).inbounds, 'WGS').streamSettings, { sockopt: { mark: 255 }, finalmask: NOISE })
  assert.deepEqual(byTag(profileToPersistedConfig(editInbound(profile, 'WGS', { mtu: 1400 })).inbounds, 'WGS').streamSettings, { sockopt: { mark: 255 }, finalmask: NOISE })
})

test('stale ws/tls from the old generic form is dropped', () => {
  const raw = withInbound(minimal, {
    tag: 'WGX',
    port: 51822,
    protocol: 'wireguard',
    settings: { secretKey: SK, address: ['10.10.0.1/24'] },
    streamSettings: { network: 'ws', security: 'tls', tlsSettings: { serverName: 'a' }, wsSettings: { path: '/x' } },
  })
  const { profile } = importRawToProfile(raw)
  const ib = profile.inbounds.find(i => i.tag === 'WGX') as unknown as Record<string, unknown>
  assert.deepEqual(ib.transport, { type: 'tcp' })
  assert.deepEqual(ib.security, { type: 'none' })
  assert.equal('streamSettings' in byTag(profileToPersistedConfig(profile).inbounds, 'WGX'), false)
  assert.equal(validateProfileForPersist(profile).ok, true)
})

test('a new WireGuard inbound from the editor keeps FinalMask and passes validation', () => {
  const SALAMANDER = { udp: [{ type: 'salamander', settings: { password: 'x' } }] }
  const { profile } = importRawToProfile(structuredClone(minimal))
  const draft = {
    ...createDefaultInboundForProtocol({ protocol: 'wireguard', clientDefaults: 'empty' }),
    tag: 'WGNEW',
    port: 51821,
    secretKey: SK,
    publicKey: undefined,
    address: ['10.8.0.1/24'],
    peers: [],
    noKernelTun: undefined,
    reserved: [1, 2, 3],
    streamAdvanced: { finalmask: SALAMANDER },
  } as Inbound
  const next: Profile = { ...profile, inbounds: [...profile.inbounds, draft] }
  const wg = byTag(profileToPersistedConfig(next).inbounds, 'WGNEW')
  const settings = wg.settings as Record<string, unknown>
  assert.equal(settings.secretKey, SK)
  assert.deepEqual(settings.address, ['10.8.0.1/24'])
  assert.equal(settings.mtu, 1420)
  assert.deepEqual(settings.reserved, [1, 2, 3])
  assert.equal('noKernelTun' in settings, false)
  assert.equal('publicKey' in settings, false)
  assert.deepEqual(wg.streamSettings, { finalmask: SALAMANDER })
  assert.equal(validateProfileForPersist(next).ok, true)
})

test('keys removed from a WireGuard outbound in the editor stay removed', () => {
  const { profile } = importRawToProfile(structuredClone(probe))
  const settings = { secretKey: SK, address: ['172.16.0.2/32'], mtu: 1280, noKernelTun: true, reserved: [1, 2, 3], peers: [PEER] }
  const next: Profile = { ...profile, outbounds: profile.outbounds?.map(o => (o.tag === 'WARP' ? ({ ...o, settings } as typeof o) : o)) }
  assert.deepEqual(byTag(profileToPersistedConfig(next).outbounds, 'WARP').settings, settings)
})

const PEER2 = { publicKey: 'HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw=', endpoint: '203.0.113.7:51820', allowedIPs: ['10.0.0.0/8'] }
const editOutboundSettings = (profile: Profile, tag: string, settings: Record<string, unknown>): Profile => ({
  ...profile,
  outbounds: profile.outbounds?.map(o => (o.tag === tag ? ({ ...o, settings } as typeof o) : o)),
})

test('a legacy local DNS profile survives unrelated edits, and the outbound check flags it', () => {
  const legacySettings = { secretKey: SK, address: ['172.16.0.2/32'], mtu: 1280, remoteDNS: ['local'], peers: [PEER] }
  const { profile } = importRawToProfile({ inbounds: [VLESS], outbounds: [DIRECT, { ...WARP, settings: legacySettings }] })
  const settings = normalizeSettingsFromEditor('wireguard', { ...legacySettings, mtu: 1400 })
  assert.deepEqual(wireguardOutboundSettingsIssues(settings), [{ field: 'remoteDNS', values: ['"local"'], notList: false }])
  const next = editOutboundSettings(profile, 'WARP', settings)
  assert.deepEqual(byTag(profileToPersistedConfig(next).outbounds, 'WARP').settings, settings)
  assert.equal(validateProfileForPersist(next).ok, true)
})

test('matching WireGuard outbounds retain raw settings patches without restoring deleted settings or peers', () => {
  const cases: { raw: RawPatch[]; settings: Record<string, unknown> | undefined }[] = [
    { raw: [{ op: 'replace', path: '/settings', value: { mtu: 1400, peers: [PEER2] } }], settings: { mtu: 1400, peers: [PEER2] } },
    { raw: [{ op: 'replace', path: '/settings/mtu', value: 1400 }, { op: 'add', path: '/settings/noKernelTun', value: true }], settings: { ...WARP.settings, mtu: 1400, noKernelTun: true } },
    { raw: [{ op: 'remove', path: '/settings/remoteDNS' }, { op: 'remove', path: '/settings/peers/0' }], settings: { ...WARP.settings, remoteDNS: undefined, peers: [] } },
    { raw: [{ op: 'remove', path: '/settings' }], settings: undefined },
  ]
  for (const { raw, settings } of cases) {
    const { profile } = importRawToProfile(structuredClone(probe))
    const next: Profile = { ...profile, outbounds: profile.outbounds?.map(o => (o.tag === 'WARP' ? ({ ...o, raw } as typeof o) : o)) }
    const before = structuredClone(next)
    const warp = byTag(profileToPersistedConfig(next).outbounds, 'WARP')
    assert.deepEqual(warp.settings, settings === undefined ? undefined : JSON.parse(JSON.stringify(settings)), JSON.stringify(raw))
    assert.deepEqual(next, before)
  }
})

test('profile raw settings patches retain precedence on a matching WireGuard outbound', () => {
  const { profile } = importRawToProfile(structuredClone(probe))
  const next: Profile = { ...profile, raw: { ...profile.raw, patches: [{ op: 'replace', path: '/outbounds/1/settings', value: { mtu: 1400 } }] } }
  assert.deepEqual(byTag(profileToPersistedConfig(next).outbounds, 'WARP').settings, { mtu: 1400 })
})

test('a compiled WireGuard outbound whose tag differs from the model at that index is left alone', () => {
  const { profile } = importRawToProfile(structuredClone(probe))
  // A raw patch renames the compiled outbound and adds a settings key the model settings lack.
  const raw = [
    { op: 'replace', path: '/tag', value: 'WARP-RAW' },
    { op: 'add', path: '/settings/extra', value: 7 },
  ]
  const next: Profile = { ...profile, outbounds: profile.outbounds?.map(o => (o.tag === 'WARP' ? ({ ...o, raw } as typeof o) : o)) }
  const warp = byTag(profileToPersistedConfig(next).outbounds, 'WARP-RAW')
  assert.equal((warp.settings as Record<string, unknown>).extra, 7)
})

test('WireGuard inbound stream keys match sockopt and finalmask case-insensitively', () => {
  const raw = withInbound(minimal, {
    tag: 'WGC',
    port: 51823,
    protocol: 'wireguard',
    settings: { secretKey: SK, address: ['10.11.0.1/24'] },
    streamSettings: { network: 'tcp', security: 'none', sockOpt: { mark: 7 }, finalMask: NOISE },
  })
  const { profile } = importRawToProfile(raw)
  const expected = { sockOpt: { mark: 7 }, finalMask: NOISE }
  assert.deepEqual(byTag(profileToPersistedConfig(profile).inbounds, 'WGC').streamSettings, expected)
  assert.deepEqual(byTag(profileToPersistedConfig(editInbound(profile, 'WGC', { mtu: 1400 })).inbounds, 'WGC').streamSettings, expected)
})

test('a WireGuard inbound with tcp extras keeps the unchanged import verbatim', () => {
  // VLESS without `security`: a compiled (non-verbatim) save would add security "none" to it.
  const vless = { tag: 'VLESS PLAIN', listen: '0.0.0.0', port: 2054, protocol: 'vless', settings: { clients: [], decryption: 'none' }, streamSettings: { network: 'tcp' } }
  const wg = {
    tag: 'WGT',
    port: 51824,
    protocol: 'wireguard',
    settings: { secretKey: SK, address: ['10.12.0.1/24'] },
    streamSettings: { network: 'tcp', security: 'none', tcpSettings: { acceptProxyProtocol: false, header: { type: 'none' } } },
  }
  const raw = { inbounds: [vless, wg], outbounds: [DIRECT] }
  const { profile } = importRawToProfile(structuredClone(raw))
  const ib = profile.inbounds.find(i => i.tag === 'WGT') as unknown as Record<string, unknown>
  assert.deepEqual(ib.transport, { type: 'tcp', acceptProxyProtocol: false, header: { type: 'none' } })
  const { streamSettings: _dropped, ...wgWithoutStream } = wg
  assert.deepEqual(profileToPersistedConfig(profile), { ...raw, inbounds: [vless, wgWithoutStream] })
  assert.equal('streamSettings' in byTag(profileToPersistedConfig(editInbound(profile, 'WGT', { mtu: 1400 })).inbounds, 'WGT'), false)
})

test('a peer keepAlive removed in the WireGuard outbound editor stays removed', () => {
  const warp = { protocol: 'wireguard', tag: 'WARP', settings: { secretKey: SK, address: ['172.16.0.2/32'], peers: [{ ...PEER, keepAlive: 25 }] } }
  const { profile } = importRawToProfile({ inbounds: [VLESS], outbounds: [DIRECT, warp] })
  const settings = { secretKey: SK, address: ['172.16.0.2/32'], peers: [PEER] }
  assert.deepEqual(byTag(profileToPersistedConfig(editOutboundSettings(profile, 'WARP', settings)).outbounds, 'WARP').settings, settings)
})

test('deleting the first of two WireGuard outbound peers does not leak its fields into the other', () => {
  const warp = { protocol: 'wireguard', tag: 'WARP', settings: { secretKey: SK, address: ['172.16.0.2/32'], peers: [{ ...PEER, keepAlive: 25, preSharedKey: SK }, PEER2] } }
  const { profile } = importRawToProfile({ inbounds: [VLESS], outbounds: [DIRECT, warp] })
  const settings = { secretKey: SK, address: ['172.16.0.2/32'], peers: [PEER2] }
  assert.deepEqual(byTag(profileToPersistedConfig(editOutboundSettings(profile, 'WARP', settings)).outbounds, 'WARP').settings, settings)
})
