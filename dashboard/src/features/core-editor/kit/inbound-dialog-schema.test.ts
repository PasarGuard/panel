import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getInboundFormCapabilities } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'
import { createInboundDialogSchema } from '@/features/core-editor/kit/inbound-dialog-schema'

const t = ((key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key) as unknown as TFunction
const schema = createInboundDialogSchema(getInboundFormCapabilities(), t)
const SK = 'yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk='
const base = { protocol: 'wireguard', tag: 'WG', port: '51820', wgSecretKey: SK, wgMtu: '', wgReserved: '' }
const issuesOf = (values: Record<string, string>) => {
  const r = schema.safeParse(values)
  return r.success ? [] : r.error.issues
}
const issuePaths = (values: Record<string, string>) => issuesOf(values).map(i => i.path.join('.'))
const messagesAt = (path: string, values: Record<string, string>) =>
  issuesOf(values)
    .filter(i => i.path.join('.') === path)
    .map(i => i.message)
const MTU_RANGE = 'MTU must be a whole number from 576 to 9000.'
const RESERVED_FORMAT = 'Reserved must be three numbers from 0 to 255, for example 1, 2, 3.'
const SECRET_KEY_INVALID = 'Secret key must be a 32-byte WireGuard key (base64 or 64 hex characters).'

test('a valid WireGuard inbound form passes', () => {
  assert.deepEqual(issuePaths(base), [])
  assert.deepEqual(issuePaths({ ...base, wgMtu: '1420', wgReserved: '1, 2, 3', wgSecretKey: 'c809f3e5317e9575c9b5ed78b638b7ce530dabe85ddab614220241801ddf0669' }), [])
})
test('WireGuard needs one port', () => {
  for (const port of ['', '51820-51830', '51820,51821', '0', '65536', 'env:WG_PORT']) {
    assert.deepEqual(messagesAt('port', { ...base, port }), ['WireGuard needs one port from 1 to 65535.'], port)
  }
})
test('WireGuard MTU range', () => {
  for (const wgMtu of ['575', '9001', '1420.5', 'abc']) assert.deepEqual(messagesAt('wgMtu', { ...base, wgMtu }), [MTU_RANGE], wgMtu)
  for (const wgMtu of ['576', '9000']) assert.deepEqual(issuePaths({ ...base, wgMtu }), [])
})
test('WireGuard reserved format', () => {
  for (const wgReserved of ['1,2', '1,2,3,4', '256,0,0', 'a,b,c']) assert.deepEqual(messagesAt('wgReserved', { ...base, wgReserved }), [RESERVED_FORMAT], wgReserved)
})
test('WireGuard secret key format', () => {
  assert.deepEqual(messagesAt('wgSecretKey', { ...base, wgSecretKey: '' }), ['Secret Key is required'])
  for (const wgSecretKey of ['abc', 'A'.repeat(42) + '==']) assert.deepEqual(messagesAt('wgSecretKey', { ...base, wgSecretKey }), [SECRET_KEY_INVALID], wgSecretKey)
})
test('other protocols keep port lists', () => {
  assert.deepEqual(issuePaths({ protocol: 'vless', tag: 'V', port: '443,1000-2000' }), [])
  assert.deepEqual(issuePaths({ protocol: 'vless', tag: 'V', port: '' }), [])
  assert.deepEqual(messagesAt('port', { protocol: 'vless', tag: 'V', port: '0' }), ['Port must be a port number or list like 443, 1000-2000,444.'])
})
