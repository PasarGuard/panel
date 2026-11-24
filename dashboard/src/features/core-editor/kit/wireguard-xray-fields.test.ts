import { test } from 'node:test'
import assert from 'node:assert/strict'

import type { Inbound } from '@pasarguard/xray-config-kit'
import {
  applyWireguardInboundFormValues,
  classifyWireguardAddresses,
  deriveWireguardPublicKey,
  formatWireguardReserved,
  isIpAddress,
  normalizeWireguardInboundForCommit,
  parseIpOrCidr,
  parseWireguardInboundPort,
  parseWireguardKey,
  parseWireguardMtuInput,
  parseWireguardReservedInput,
  wireguardInboundAddresses,
  wireguardInboundFormTexts,
  wireguardReservedBytes,
  wireguardReservedInputMatches,
} from '@/features/core-editor/kit/wireguard-xray-fields'

const SK = 'yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk='
const PK = 'HIgo9xNzJMWLKASShiTqIybxZ0U3wGLiUeJ1PKf8ykw='

test('deriveWireguardPublicKey accepts every encoding Xray and the backend accept', () => {
  for (const key of [
    SK,
    ` ${SK} `,
    'c809f3e5317e9575c9b5ed78b638b7ce530dabe85ddab614220241801ddf0669',
    'C809F3E5317E9575C9B5ED78B638B7CE530DABE85DDAB614220241801DDF0669',
    'yAnz5TF-lXXJte14tji3zlMNq-hd2rYUIgJBgB3fBmk',
    'yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk',
  ]) {
    assert.equal(deriveWireguardPublicKey(key), PK, key)
  }
})
test('parseWireguardKey rejects near misses', () => {
  assert.equal(parseWireguardKey(SK)?.length, 32)
  for (const key of ['', 'abc', 'A'.repeat(42) + '==', 'yAnz5TF+lXXJte14tji3zlMNq-hd2rYUIgJBgB3fBmk=', 'g'.repeat(64), SK + '=', SK.slice(0, -2)]) {
    assert.equal(parseWireguardKey(key), null, key)
    assert.equal(deriveWireguardPublicKey(key), '', key)
  }
})
test('parseWireguardMtuInput keeps the backend range 576 to 9000', () => {
  assert.deepEqual(parseWireguardMtuInput(''), { ok: true, value: undefined })
  assert.deepEqual(parseWireguardMtuInput('  '), { ok: true, value: undefined })
  assert.deepEqual(parseWireguardMtuInput(' 1420 '), { ok: true, value: 1420 })
  assert.deepEqual(parseWireguardMtuInput('576'), { ok: true, value: 576 })
  assert.deepEqual(parseWireguardMtuInput('9000'), { ok: true, value: 9000 })
  for (const raw of ['575', '9001', '1420.5', '1e3', '-1420', 'abc', '0']) assert.deepEqual(parseWireguardMtuInput(raw), { ok: false }, raw)
})
test('parseWireguardReservedInput accepts comma lists and JSON arrays', () => {
  assert.deepEqual(parseWireguardReservedInput(''), { ok: true, value: undefined })
  assert.deepEqual(parseWireguardReservedInput('1,2,3'), { ok: true, value: [1, 2, 3] })
  assert.deepEqual(parseWireguardReservedInput(' 1, 2 , 3 '), { ok: true, value: [1, 2, 3] })
  assert.deepEqual(parseWireguardReservedInput('[0,255,7]'), { ok: true, value: [0, 255, 7] })
  assert.deepEqual(parseWireguardReservedInput('[ 0, 255, 7 ]'), { ok: true, value: [0, 255, 7] })
  for (const raw of ['1,2', '1,2,3,4', '256,0,0', '-1,0,0', '1.5,2,3', 'a,b,c', '[1,2]', '1,,3', 'AQID', '[1,2,3', '1 2 3']) assert.deepEqual(parseWireguardReservedInput(raw), { ok: false }, raw)
})
test('stored reserved values: lists, base64 and junk', () => {
  assert.deepEqual(wireguardReservedBytes([1, 2, 3]), [1, 2, 3])
  assert.deepEqual(wireguardReservedBytes('AQID'), [1, 2, 3])
  assert.deepEqual(wireguardReservedBytes(undefined), [])
  assert.deepEqual(wireguardReservedBytes([]), [])
  assert.deepEqual(wireguardReservedBytes(''), [])
  for (const v of [[1, 2], [256, 0, 0], [1.5, 2, 3], 'AQ==', '1,2,3', 7]) assert.equal(wireguardReservedBytes(v), null, JSON.stringify(v))
  assert.equal(formatWireguardReserved([1, 2, 3]), '1, 2, 3')
  assert.equal(formatWireguardReserved('AQID'), '1, 2, 3')
  assert.equal(formatWireguardReserved(undefined), '')
  assert.equal(formatWireguardReserved('1,2,3'), '1,2,3')
  assert.equal(wireguardReservedInputMatches('1,2,3', 'AQID'), true)
  assert.equal(wireguardReservedInputMatches('', undefined), true)
  assert.equal(wireguardReservedInputMatches('1,2', [1, 2, 3]), false)
})
test('parseWireguardInboundPort only accepts one port from 1 to 65535', () => {
  assert.equal(parseWireguardInboundPort(51820), 51820)
  assert.equal(parseWireguardInboundPort('51820'), 51820)
  assert.equal(parseWireguardInboundPort(' 51820 '), 51820)
  assert.equal(parseWireguardInboundPort('65535'), 65535)
  for (const v of ['51820-51830', '51820,51821', 0, '0', 65536, 'env:WG_PORT', '', undefined, 51820.5, '0x10', '5e4']) assert.equal(parseWireguardInboundPort(v), null, String(v))
})
test('classifyWireguardAddresses follows the backend allocatable rule plus Xray netip parsing (leading-zero prefixes)', () => {
  assert.deepEqual(
    classifyWireguardAddresses([
      '10.8.0.1/24',
      '10.0.0.0/30',
      'fd00::1/64',
      'fd00::/126',
      '::ffff:10.0.0.1/120',
      '10.0.0.1',
      '10.0.0.0/31',
      '10.0.0.1/32',
      'fd00::/127',
      'fd00::1',
      '010.0.0.1/24',
      '10.0.0.1/33',
      '10.0.0.1/024',
      'fd00::g/64',
      '1.2.3',
      '10.0.0.256/24',
      'fd00:::1/64',
      'example.com',
    ]),
    {
      allocatable: ['10.8.0.1/24', '10.0.0.0/30', 'fd00::1/64', 'fd00::/126', '::ffff:10.0.0.1/120'],
      unmanaged: ['10.0.0.1', '10.0.0.0/31', '10.0.0.1/32', 'fd00::/127', 'fd00::1'],
      invalid: ['010.0.0.1/24', '10.0.0.1/33', '10.0.0.1/024', 'fd00::g/64', '1.2.3', '10.0.0.256/24', 'fd00:::1/64', 'example.com'],
    },
  )
  assert.deepEqual(parseIpOrCidr('1:2:3:4:5:6:7:8/64'), { version: 6, prefix: 64 })
  assert.equal(parseIpOrCidr('1:2:3:4:5:6:7:8:9'), null)
  assert.equal(isIpAddress('1.1.1.1'), true)
  assert.equal(isIpAddress('1.1.1.1/32'), false)
  assert.deepEqual(wireguardInboundAddresses([' 10.8.0.1/24 ', '']), ['10.8.0.1/24'])
  assert.deepEqual(wireguardInboundAddresses(undefined), [])
})
test('applyWireguardInboundFormValues writes parsed MTU and reserved', () => {
  const ib = { kind: 'inbound', protocol: 'wireguard', tag: 'WG', secretKey: SK, peers: [], mtu: 1420, reserved: '1,2,3' } as unknown as Inbound
  assert.deepEqual(applyWireguardInboundFormValues(ib, { mtu: '1400', reserved: '1, 2, 3' }), { ...ib, mtu: 1400, reserved: [1, 2, 3] })
  const cleared = applyWireguardInboundFormValues(ib, { mtu: '', reserved: '' }) as unknown as Record<string, unknown>
  assert.equal('mtu' in cleared, false)
  assert.equal('reserved' in cleared, false)
  assert.equal(applyWireguardInboundFormValues(ib, { mtu: '1', reserved: 'x' }), ib)
  const vless = { kind: 'inbound', protocol: 'vless', tag: 'V' } as unknown as Inbound
  assert.equal(applyWireguardInboundFormValues(vless, { mtu: '1400', reserved: '' }), vless)
})
test('applyWireguardInboundFormValues writes the MTU and keeps the stored reserved when only the reserved text is bad', () => {
  const ib = { kind: 'inbound', protocol: 'wireguard', tag: 'WG', secretKey: SK, peers: [], mtu: 1420, reserved: '1,2,3' } as unknown as Inbound
  assert.deepEqual(applyWireguardInboundFormValues(ib, { mtu: '1400', reserved: 'x' }), { ...ib, mtu: 1400, reserved: '1,2,3' })
})
test('wireguardInboundFormTexts keeps typed text that does not parse or parses to the stored value', () => {
  const wg = (fields: Record<string, unknown>) => ({ kind: 'inbound', protocol: 'wireguard', tag: 'WG', ...fields }) as unknown as Inbound
  // "9999" fails the range, so the 999 patched at the third keystroke must not replace it.
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 999 }), { mtu: '9999', reserved: '' }), { mtu: '9999', reserved: '' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 600, reserved: [1, 2, 3] }), { mtu: '0600', reserved: '1,2,3' }), { mtu: '0600', reserved: '1,2,3' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ reserved: 'AQID' }), { mtu: '', reserved: '[1,2,3]' }), { mtu: '', reserved: '[1,2,3]' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 1420, reserved: [1, 2, 30] }), { mtu: '14', reserved: '1, 2' }), { mtu: '14', reserved: '1, 2' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ reserved: [1, 2, 30] }), { mtu: '', reserved: '1, 2, 300' }), { mtu: '', reserved: '1, 2, 300' })
})
test('wireguardInboundFormTexts shows the stored value when the typed text parses to another value or nothing is typed yet', () => {
  const wg = (fields: Record<string, unknown>) => ({ kind: 'inbound', protocol: 'wireguard', tag: 'WG', ...fields }) as unknown as Inbound
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 1500, reserved: [4, 5, 6] }), { mtu: '1400', reserved: '1, 2, 3' }), { mtu: '1500', reserved: '4, 5, 6' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 1420, reserved: 'AQID' }), { mtu: '', reserved: '' }), { mtu: '1420', reserved: '1, 2, 3' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 1420, reserved: 'AQID' })), { mtu: '1420', reserved: '1, 2, 3' })
  assert.deepEqual(wireguardInboundFormTexts(wg({ mtu: 100, reserved: [1, 2] })), { mtu: '100', reserved: '[1,2]' })
  const vless = { kind: 'inbound', protocol: 'vless', tag: 'V', mtu: 1400 } as unknown as Inbound
  assert.deepEqual(wireguardInboundFormTexts(vless, { mtu: '9999', reserved: '1, 2' }), { mtu: '', reserved: '' })
})
test('normalizeWireguardInboundForCommit trims the secret key, port and address entries and writes MTU and reserved', () => {
  const ib = {
    kind: 'inbound',
    protocol: 'wireguard',
    tag: 'WG',
    port: ' 51820 ',
    secretKey: `  ${SK}\n`,
    address: [' 10.8.0.1/24 ', '', '  ', 'fd00::1/64'],
    peers: [],
    reserved: 'AQID',
  } as unknown as Inbound
  assert.deepEqual(normalizeWireguardInboundForCommit(ib, { mtu: '1400', reserved: '1, 2, 3' }), {
    ...ib,
    port: 51820,
    secretKey: SK,
    address: ['10.8.0.1/24', 'fd00::1/64'],
    mtu: 1400,
    reserved: [1, 2, 3],
  })
  const untouched = { kind: 'inbound', protocol: 'wireguard', tag: 'WG', port: '1000-2000', secretKey: SK, address: [], peers: [] } as unknown as Inbound
  assert.deepEqual(normalizeWireguardInboundForCommit(untouched, { mtu: '', reserved: '' }), untouched)
  const vless = { kind: 'inbound', protocol: 'vless', tag: 'V', port: ' 443 ' } as unknown as Inbound
  assert.equal(normalizeWireguardInboundForCommit(vless, { mtu: '1400', reserved: '' }), vless)
})
