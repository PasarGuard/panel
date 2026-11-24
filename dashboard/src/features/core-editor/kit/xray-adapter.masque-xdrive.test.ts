import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInboundForProtocol, createDefaultOutbound } from '@pasarguard/xray-config-kit'
import type { Inbound, Outbound, Profile, StreamSettings } from '@pasarguard/xray-config-kit'
import { applyMasqueClientAuthMode } from '@/features/core-editor/kit/masque-fields'
import { stripSparseOutboundEnvelope } from '@/features/core-editor/kit/outbound-editor-json'
import { applyOutboundStreamNetwork, outboundStreamSettingsForProtocolSwitch } from '@/features/core-editor/kit/outbound-stream-dynamic'
import { setRecordKey } from '@/features/core-editor/kit/stream-form-fields'
import { applyXdriveService } from '@/features/core-editor/kit/xdrive-fields'
import { importRawToProfile, profileToPersistedConfig, validateProfileForPersist } from '@/features/core-editor/kit/xray-adapter'

// Characterization tests: the adapter has no MASQUE or XDrive code; the kit models plus its source merge do the work.

// WARP test keys (P-256), accepted by `xray run -test`.
const PK = 'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgzf80S8b2vAe0lzg4YtwU3do/BD5CUepL4DyHi3lQmG6hRANCAARlzud/JhCw2zA2UcfIOIXR3s7GxRhengEyoleDALR2v5oNgR02inyEqaD3EXuTdi6guo3hkjcWPkGCdqD53A7P'
const PUB = 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEhSLswmwFGmTfktgncKzzcZdtIxbSuvrTXVphpb9vySWPrykRZzKhBLH2zgiOU4ARXW4tmLtZtZq/Ezr8onNQBw=='
// A VLESS Encryption pair from `xray vlessenc` (X25519). Xray v26.10.17 runs xdrive only on VLESS with encryption.
const VLESS_DECRYPTION = 'mlkem768x25519plus.native.600s.KGoJgsdMC5rWUr1fnyXxteBAgbbWIQ_YKVnFWpxXBWk'
const VLESS_ENCRYPTION = 'mlkem768x25519plus.native.0rtt.YOJcGyGNg_LvmRbpVL3WdBZ0ajyDnvIzqE-Dp-816zM'

const CERT = { certificateFile: '/etc/ssl/mq.pem', keyFile: '/etc/ssl/mq.key' }
const MASQUE_IN = {
  tag: 'MASQUE',
  listen: '0.0.0.0',
  port: 443,
  protocol: 'masque',
  settings: { users: [], address: ['10.0.0.1/24', 'fd00::1/64'], mtu: 1400, remoteDNS: ['1.1.1.1'] },
  streamSettings: {
    network: 'masque',
    security: 'tls',
    tlsSettings: { serverName: 'example.com', certificates: [CERT] },
    masqueSettings: { path: '/masque', host: 'example.com', headers: { 'X-A': 'b' } },
  },
}
// "Google Drive" is the name Xray v26.9.30 to v26.10.10 knows; XDRIVE_OUT uses the v26.10.17 spelling "google-drive".
const XDRIVE_IN = {
  tag: 'VLESS XDRIVE',
  listen: '0.0.0.0',
  port: 8443,
  protocol: 'vless',
  settings: { clients: [], decryption: VLESS_DECRYPTION },
  streamSettings: {
    method: 'xdrive',
    security: 'none',
    xdriveSettings: { service: 'Google Drive', remoteFolder: 'xd', secrets: ['a', 'b', 'c'], segmentBytes: 1048576, pollIntervalMs: 300 },
  },
}
const XMUX = { maxConcurrency: '16-32' }
const WARP_OUT = {
  protocol: 'masque',
  tag: 'MQ-WARP',
  settings: { address: '162.159.198.1', port: 443, remoteDNS: ['1.1.1.1'] },
  streamSettings: {
    network: 'masque',
    security: 'tls',
    tlsSettings: { serverName: 'consumer-masque.cloudflareclient.com' },
    masqueSettings: { warp: { privateKey: PK, publicKey: PUB, address: ['172.16.0.2/32', '2606:4700:110:8a36::2/128'] }, xmux: XMUX },
  },
}
const XDRIVE_OUT = {
  protocol: 'vless',
  tag: 'VX-OUT',
  settings: { vnext: [{ address: 'www.googleapis.com', port: 443, users: [{ id: '11111111-1111-4111-8111-111111111111', encryption: VLESS_ENCRYPTION }] }] },
  streamSettings: {
    network: 'xdrive',
    security: 'tls',
    tlsSettings: { serverName: 'www.googleapis.com' },
    xdriveSettings: { service: 'google-drive', remoteFolder: 'xd-out', secrets: ['id', 'secret', 'token'] },
  },
  mux: { enabled: true },
}
// Xray v26.10.17 accepts mux on MASQUE outbounds (v26.10.10 and older refuse it), so the editor keeps it.
const MUX_OUT = {
  protocol: 'masque',
  tag: 'MQ-MUX',
  settings: { address: 'mq.example.com', port: 443 },
  streamSettings: { network: 'masque', security: 'tls', tlsSettings: { serverName: 'mq.example.com' }, masqueSettings: { user: 'alice', pass: 'secret' } },
  mux: { enabled: true, concurrency: 8 },
}
const DIRECT = { protocol: 'freedom', tag: 'DIRECT' }
const raw = { log: { loglevel: 'warning' }, inbounds: [MASQUE_IN, XDRIVE_IN], outbounds: [DIRECT, WARP_OUT, XDRIVE_OUT, MUX_OUT] }

type Json = Record<string, unknown>
/** `raw` with extra or replaced keys in the XDrive inbound and outbound `xdriveSettings` (spreads keep the key order). */
const withXdriveSettings = (inbound: Json, outbound: Json) => ({
  ...raw,
  inbounds: [MASQUE_IN, { ...XDRIVE_IN, streamSettings: { ...XDRIVE_IN.streamSettings, xdriveSettings: { ...XDRIVE_IN.streamSettings.xdriveSettings, ...inbound } } }],
  outbounds: [DIRECT, WARP_OUT, { ...XDRIVE_OUT, streamSettings: { ...XDRIVE_OUT.streamSettings, xdriveSettings: { ...XDRIVE_OUT.streamSettings.xdriveSettings, ...outbound } } }, MUX_OUT],
})
const imported = (source: unknown = raw) => importRawToProfile(structuredClone(source)).profile
const editIn = (p: Profile, i: number, next: Json): Profile => ({ ...p, inbounds: p.inbounds.map((ib, k) => (k === i ? (next as unknown as Inbound) : ib)) })
const editOut = (p: Profile, i: number, next: Json): Profile => ({ ...p, outbounds: (p.outbounds ?? []).map((ob, k) => (k === i ? (next as unknown as Outbound) : ob)) })
const inboundModel = (p: Profile, i: number) => p.inbounds[i] as unknown as Json
const outboundModel = (p: Profile, i: number) => (p.outbounds ?? [])[i] as unknown as Json
const compiledInbounds = (p: Profile) => profileToPersistedConfig(p).inbounds as Json[]
const compiledOutbounds = (p: Profile) => profileToPersistedConfig(p).outbounds as Json[]
const record = (value: unknown) => value as Json

test('unchanged MASQUE and XDrive configs round trip byte for byte', () => {
  const profile = imported()
  assert.equal(JSON.stringify(profileToPersistedConfig(profile)), JSON.stringify(raw))
  assert.equal(profile.inbounds[0].protocol, 'masque')
  assert.equal((profile.inbounds[1] as unknown as { transport: { type: string } }).transport.type, 'xdrive')
  assert.equal(profile.outbounds?.[1].protocol, 'masque')
  assert.equal(profile.outbounds?.[3].protocol, 'masque')
})

test('imported MASQUE and XDrive configs pass persist validation', () => {
  assert.equal(validateProfileForPersist(imported()).ok, true)
})

test('both Google Drive spellings round trip unchanged and stay through edits', () => {
  for (const [inService, outService] of [
    ['Google Drive', 'google-drive'],
    ['google-drive', 'Google Drive'],
  ]) {
    const source = withXdriveSettings({ service: inService }, { service: outService })
    const profile = imported(source)
    assert.equal(JSON.stringify(profileToPersistedConfig(profile)), JSON.stringify(source))
    assert.equal(validateProfileForPersist(profile).ok, true)

    const ib = inboundModel(profile, 1)
    const ob = outboundModel(profile, 2)
    const obStream = record(ob.streamSettings)
    const edited = editOut(editIn(profile, 1, { ...ib, transport: setRecordKey(record(ib.transport), 'remoteFolder', 'xd-2') }), 2, {
      ...ob,
      streamSettings: { ...obStream, xdriveSettings: setRecordKey(record(obStream.xdriveSettings), 'remoteFolder', 'xd-out-2') },
    })
    const inStream = record(compiledInbounds(edited)[1].streamSettings)
    const outStream = record(compiledOutbounds(edited)[2].streamSettings)
    assert.deepEqual(inStream.xdriveSettings, { ...XDRIVE_IN.streamSettings.xdriveSettings, service: inService, remoteFolder: 'xd-2' })
    assert.deepEqual(outStream.xdriveSettings, { ...XDRIVE_OUT.streamSettings.xdriveSettings, service: outService, remoteFolder: 'xd-out-2' })
  }
})

test('edited MASQUE inbound compiles what the form wrote', () => {
  const profile = imported()
  const ib = inboundModel(profile, 0)
  const next = setRecordKey({ ...ib, mtu: 1350, security: { ...record(ib.security), alpn: ['h2'] }, transport: { type: 'masque', path: '/m2', host: 'example.com' } }, 'remoteDNS', undefined)
  assert.deepEqual(compiledInbounds(editIn(profile, 0, next))[0], {
    tag: 'MASQUE',
    port: 443,
    protocol: 'masque',
    settings: { users: [], address: ['10.0.0.1/24', 'fd00::1/64'], mtu: 1350 },
    streamSettings: {
      network: 'masque',
      security: 'tls',
      tlsSettings: { serverName: 'example.com', certificates: [CERT], alpn: ['h2'] },
      masqueSettings: { path: '/m2', host: 'example.com' },
    },
  })
})

test('switching an imported XDrive inbound from Google Drive to local drops secrets and keeps the method key', () => {
  for (const service of ['Google Drive', 'google-drive']) {
    const profile = imported(withXdriveSettings({ service }, {}))
    const ib = inboundModel(profile, 1)
    const transport = setRecordKey(applyXdriveService(record(ib.transport), 'local'), 'remoteFolder', '/srv/xd')
    assert.deepEqual(
      compiledInbounds(editIn(profile, 1, { ...ib, transport }))[1].streamSettings,
      { method: 'xdrive', security: 'none', xdriveSettings: { service: 'local', remoteFolder: '/srv/xd', segmentBytes: 1048576, pollIntervalMs: 300 } },
      service,
    )
  }
})

test('switching an imported WARP outbound to user and password leaves no warp', () => {
  const profile = imported()
  const ob = outboundModel(profile, 1)
  const stream = record(ob.streamSettings)
  const masqueSettings = { ...applyMasqueClientAuthMode(record(stream.masqueSettings), 'basic'), user: 'alice', pass: 'secret' }
  const settings = setRecordKey(record(ob.settings), 'remoteDNS', undefined)
  assert.deepEqual(compiledOutbounds(editOut(profile, 1, { ...ob, settings, streamSettings: { ...stream, masqueSettings } }))[1], {
    protocol: 'masque',
    tag: 'MQ-WARP',
    settings: { address: '162.159.198.1', port: 443 },
    streamSettings: {
      network: 'masque',
      security: 'tls',
      tlsSettings: { serverName: 'consumer-masque.cloudflareclient.com' },
      masqueSettings: { xmux: XMUX, user: 'alice', pass: 'secret' },
    },
  })
})

test('a removed MASQUE xmux key stays removed', () => {
  const profile = imported()
  const ob = outboundModel(profile, 1)
  const stream = record(ob.streamSettings)
  const masqueSettings = setRecordKey(record(stream.masqueSettings), 'xmux', undefined)
  const compiled = compiledOutbounds(editOut(profile, 1, { ...ob, streamSettings: { ...stream, masqueSettings } }))[1]
  assert.deepEqual(compiled, { ...WARP_OUT, streamSettings: { ...WARP_OUT.streamSettings, masqueSettings: { warp: WARP_OUT.streamSettings.masqueSettings.warp } } })
})

test('a MASQUE outbound keeps its mux through an edit', () => {
  const profile = imported()
  const ob = outboundModel(profile, 3)
  const compiled = compiledOutbounds(editOut(profile, 3, { ...ob, settings: { ...record(ob.settings), port: 8443 } }))[3]
  assert.deepEqual(compiled, { ...MUX_OUT, settings: { ...MUX_OUT.settings, port: 8443 } })
})

test('leaving the xdrive network drops xdriveSettings from the outbound', () => {
  const profile = imported()
  const ob = outboundModel(profile, 2)
  const streamSettings = applyOutboundStreamNetwork(record(ob.streamSettings), 'tcp')
  assert.deepEqual(compiledOutbounds(editOut(profile, 2, { ...ob, streamSettings }))[2].streamSettings, {
    network: 'tcp',
    security: 'tls',
    tlsSettings: { serverName: 'www.googleapis.com' },
  })
})

test('unknown keys stay where the kit source merge keeps them', () => {
  const withXdrive = withXdriveSettings({}, { extraY: 3 })
  const masqueIn = {
    ...MASQUE_IN,
    settings: { ...MASQUE_IN.settings, fooSet: 1 },
    streamSettings: { ...MASQUE_IN.streamSettings, masqueSettings: { ...MASQUE_IN.streamSettings.masqueSettings, barK: 2 } },
  }
  const source = { ...withXdrive, inbounds: [masqueIn, XDRIVE_IN] }
  const profile = imported(source)
  assert.equal(JSON.stringify(profileToPersistedConfig(profile)), JSON.stringify(source))
  const ib = inboundModel(profile, 0)
  const ob = outboundModel(profile, 2)
  const obStream = record(ob.streamSettings)
  const edited = editOut(editIn(profile, 0, { ...ib, mtu: 1350 }), 2, {
    ...ob,
    streamSettings: { ...obStream, xdriveSettings: setRecordKey(record(obStream.xdriveSettings), 'remoteFolder', 'xd-2') },
  })
  const config = profileToPersistedConfig(edited)
  const compiledMasque = (config.inbounds as Json[])[0]
  const compiledXdrive = (config.outbounds as Json[])[2]
  assert.equal(record(compiledMasque.settings).mtu, 1350)
  assert.equal(record(compiledMasque.settings).fooSet, 1)
  assert.equal(record(record(compiledMasque.streamSettings).masqueSettings).barK, 2)
  assert.equal(record(record(compiledXdrive.streamSettings).xdriveSettings).remoteFolder, 'xd-2')
  assert.equal(record(record(compiledXdrive.streamSettings).xdriveSettings).extraY, 3)
})

test('new MASQUE inbound and outbound from the editor compile and pass persist validation', () => {
  const profile = imported()
  const inbound = {
    ...createDefaultInboundForProtocol({ protocol: 'masque', clientDefaults: 'empty' }),
    tag: 'MQNEW',
    port: 4443,
    security: { type: 'tls', serverName: 'mq.example.com', alpn: ['h3', 'h2'], certificates: [CERT] },
  }
  const base = stripSparseOutboundEnvelope(
    createDefaultOutbound({ protocol: 'masque', tag: 'MQ-BASIC', streamSettings: outboundStreamSettingsForProtocolSwitch(undefined, 'masque') as StreamSettings }) as Json,
  )
  const outbound = { ...base, settings: { address: 'mq.example.com', port: 443 }, streamSettings: { ...record(base.streamSettings), masqueSettings: { user: 'alice', pass: 'secret' } } }
  const next: Profile = { ...profile, inbounds: [...profile.inbounds, inbound as unknown as Inbound], outbounds: [...(profile.outbounds ?? []), outbound as unknown as Outbound] }
  const config = profileToPersistedConfig(next)
  assert.deepEqual((config.inbounds as Json[])[2], {
    tag: 'MQNEW',
    port: 4443,
    protocol: 'masque',
    settings: { users: [], address: ['10.14.0.1/16', 'fd14::1/64'] },
    streamSettings: { network: 'masque', security: 'tls', tlsSettings: { serverName: 'mq.example.com', alpn: ['h3', 'h2'], certificates: [CERT] }, masqueSettings: {} },
  })
  assert.deepEqual((config.outbounds as Json[])[4], {
    tag: 'MQ-BASIC',
    protocol: 'masque',
    settings: { address: 'mq.example.com', port: 443 },
    streamSettings: { network: 'masque', security: 'tls', masqueSettings: { user: 'alice', pass: 'secret' } },
  })
  assert.equal(validateProfileForPersist(next).ok, true)
})
