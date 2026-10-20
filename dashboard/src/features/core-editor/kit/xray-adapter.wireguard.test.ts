import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInboundForProtocol } from '@pasarguard/xray-config-kit'
import type { Inbound, Profile } from '@pasarguard/xray-config-kit'
import { importRawToProfile, profileToPersistedConfig, validateProfileForPersist } from '@/features/core-editor/kit/xray-adapter'

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
