// Exercise the real import/save adapters with backend-managed inbound peers.
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  configFile: false,
  resolve: { alias: { '@': fileURLToPath(new URL('../src', import.meta.url)) } },
  server: { middlewareMode: true },
})

try {
  const xray = await server.ssrLoadModule('/src/features/core-editor/kit/xray-adapter.ts')
  const wg = await server.ssrLoadModule('/src/features/core-editor/kit/wireguard-adapter.ts')
  const key = Buffer.alloc(32, 1).toString('base64')
  const peers = [{ publicKey: key, allowedIPs: ['10.90.0.2/32'] }]
  const raw = {
    inbounds: [
      {
        tag: 'wg',
        protocol: 'wireguard',
        listen: '0.0.0.0',
        port: 51820,
        settings: { secretKey: key, address: ['10.90.0.1/24'], peers, mtu: 1380 },
      },
    ],
    outbounds: [
      {
        tag: 'remote-wg',
        protocol: 'wireguard',
        settings: { secretKey: key, address: ['10.91.0.2/32'], peers: [{ ...peers[0], endpoint: 'example.invalid:51820' }] },
      },
    ],
  }
  const original = structuredClone(raw)
  const { profile } = xray.importRawToProfile(raw)
  assert.deepEqual(profile.inbounds[0].peers, [])
  // Also discard peers added to an already-loaded draft before saving.
  const edited = { ...profile, inbounds: [{ ...profile.inbounds[0], peers }] }
  const result = xray.validateProfileForPersist(edited)
  assert.equal(result.ok, true, JSON.stringify(result))
  assert.deepEqual(result.config.inbounds[0].settings.peers ?? [], [])
  assert.equal(result.config.inbounds[0].settings.secretKey, key)
  assert.deepEqual(result.config.inbounds[0].settings.address, ['10.90.0.1/24'])
  assert.equal(result.config.inbounds[0].settings.mtu, 1380)
  assert.deepEqual(result.config.outbounds[0].settings.peers, raw.outbounds[0].settings.peers)
  assert.deepEqual(raw, original, 'import/save must not mutate the source config')

  const imported = wg.wireGuardConfigToDraft({
    interface_name: 'wg0',
    private_key: key,
    listen_port: 51820,
    address: ['10.90.0.1/24'],
    mtu: 1380,
    peers,
  })
  assert.equal(imported.ok, true)
  assert.equal('peers' in imported.draft.extra, false)
  const saved = wg.getWireGuardPersistConfig({ ...imported.draft, extra: { ...imported.draft.extra, peers } })
  assert.equal(saved.ok, true, JSON.stringify(saved))
  assert.equal('peers' in saved.config, false)
  assert.equal(saved.config.private_key, key)
  assert.equal(saved.config.mtu, 1380)
  console.log('PASS WireGuard inbound peers stay backend-managed across import, draft edits and save; interface settings and outbound peers survive')
} finally {
  await server.close()
}
