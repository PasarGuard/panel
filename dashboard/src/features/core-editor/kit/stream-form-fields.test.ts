import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInboundForProtocol, validateInboundDraft, validateOutboundDraft } from '@pasarguard/xray-config-kit'
import type { Inbound, Issue, Outbound } from '@pasarguard/xray-config-kit'
import {
  blockingStreamFieldIssues,
  cleanStringList,
  formatJsonObjectInput,
  formatNumberInput,
  formatTextInput,
  inboundStreamFieldIssues,
  isPlainObject,
  outboundStreamAccordionBlockingIssues,
  outboundStreamFieldIssues,
  parseJsonObjectInput,
  parsePortInput,
  parseTrimmedTextInput,
  setRecordKey,
  streamFieldIssuesForInbound,
  streamFieldIssuesForOutbound,
  streamIssueSetGained,
  streamIssueSetKey,
  syncTypedText,
} from '@/features/core-editor/kit/stream-form-fields'
import type { StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'

// A VLESS Encryption pair from `xray vlessenc` (X25519). Xray v26.10.17 runs xdrive only on VLESS with encryption.
const VLESS_DECRYPTION = 'mlkem768x25519plus.native.600s.KGoJgsdMC5rWUr1fnyXxteBAgbbWIQ_YKVnFWpxXBWk'
const VLESS_ENCRYPTION = 'mlkem768x25519plus.native.0rtt.YOJcGyGNg_LvmRbpVL3WdBZ0ajyDnvIzqE-Dp-816zM'
const XDRIVE_IN = { ...createDefaultInboundForProtocol({ protocol: 'vless', transport: 'xdrive', clientDefaults: 'empty' }), tag: 'XD', port: 8443, decryption: VLESS_DECRYPTION } as unknown as Inbound
const XDRIVE_OUT = {
  protocol: 'vless',
  tag: 'VX',
  settings: { address: 'a', port: 443, id: '11111111-1111-4111-8111-111111111111', encryption: VLESS_ENCRYPTION },
  streamSettings: { method: 'xdrive', security: 'none', xdriveSettings: { service: 'local' } },
  mux: { enabled: true },
} as unknown as Outbound

test('parsePortInput accepts one port from 1 to 65535', () => {
  assert.deepEqual(parsePortInput(''), { ok: true, value: undefined })
  assert.deepEqual(parsePortInput(' 443 '), { ok: true, value: 443 })
  assert.deepEqual(parsePortInput('65535'), { ok: true, value: 65535 })
  for (const raw of ['0', '65536', '1e3', '-1', '44.3', '0x10', '443,8443', 'abc']) assert.deepEqual(parsePortInput(raw), { ok: false }, raw)
})

test('parseJsonObjectInput accepts objects only', () => {
  assert.deepEqual(parseJsonObjectInput('  '), { ok: true, value: undefined })
  assert.deepEqual(parseJsonObjectInput('{}'), { ok: true, value: {} })
  assert.deepEqual(parseJsonObjectInput('{"auth":{"type":"basic"}}'), { ok: true, value: { auth: { type: 'basic' } } })
  assert.deepEqual(parseJsonObjectInput('{"X-A":"b"}', { stringValues: true }), { ok: true, value: { 'X-A': 'b' } })
  for (const raw of ['[1]', '"x"', 'null', '1', '{']) assert.deepEqual(parseJsonObjectInput(raw), { ok: false }, raw)
  for (const raw of ['{"X-A":1}', '{"X-A":null}', '{"X-A":["b"]}']) assert.deepEqual(parseJsonObjectInput(raw, { stringValues: true }), { ok: false }, raw)
  assert.equal(formatJsonObjectInput({ 'X-A': 'b' }), '{\n  "X-A": "b"\n}')
  assert.equal(formatJsonObjectInput(undefined), '')
  assert.equal(formatJsonObjectInput([1]), '')
})

test('syncTypedText keeps typed text that does not parse or matches the stored value', () => {
  const format = (v: number | undefined) => (v === undefined ? '' : String(v))
  assert.equal(syncTypedText('44x', 443, parsePortInput, format), '44x')
  assert.equal(syncTypedText(' 443 ', 443, parsePortInput, format), ' 443 ')
  assert.equal(syncTypedText('443', 8443, parsePortInput, format), '8443')
  assert.equal(syncTypedText('443', undefined, parsePortInput, format), '')
  const headers = (raw: string) => parseJsonObjectInput(raw, { stringValues: true })
  assert.equal(syncTypedText('{"X-A": "b"}', { 'X-A': 'b' }, headers, formatJsonObjectInput), '{"X-A": "b"}')
  assert.equal(syncTypedText('{"X-A": "b"}', undefined, headers, formatJsonObjectInput), '')
  assert.equal(formatNumberInput(443), '443')
  assert.equal(formatNumberInput(0), '0')
  assert.equal(formatNumberInput(undefined), '')
  assert.equal(syncTypedText('0443', 443, parsePortInput, formatNumberInput), '0443')
})

test('isPlainObject accepts JSON objects only', () => {
  assert.equal(isPlainObject({}), true)
  assert.equal(isPlainObject({ a: 1 }), true)
  for (const value of [null, undefined, [], [1], 'x', 1, true]) assert.equal(isPlainObject(value), false, JSON.stringify(value))
})

test('parseTrimmedTextInput writes the trimmed value and keeps the typed spaces', () => {
  assert.deepEqual(parseTrimmedTextInput(''), { ok: true, value: undefined })
  assert.deepEqual(parseTrimmedTextInput('   '), { ok: true, value: undefined })
  assert.deepEqual(parseTrimmedTextInput(' /srv/my folder '), { ok: true, value: '/srv/my folder' })
  assert.equal(formatTextInput('/srv/xd'), '/srv/xd')
  assert.equal(formatTextInput(undefined), '')
  assert.equal(formatTextInput(5), '')
  // The model holds "/srv/my" while the input keeps the space typed before the next word.
  assert.equal(syncTypedText('/srv/my ', '/srv/my', parseTrimmedTextInput, formatTextInput), '/srv/my ')
  assert.equal(syncTypedText(' ', undefined, parseTrimmedTextInput, formatTextInput), ' ')
  assert.equal(syncTypedText('/srv/my ', '/srv/other', parseTrimmedTextInput, formatTextInput), '/srv/other')
})

test('cleanStringList trims and drops blanks', () => {
  assert.deepEqual(cleanStringList([' 10.14.0.1/16 ', '', '  ', 'fd14::1/64']), ['10.14.0.1/16', 'fd14::1/64'])
  assert.deepEqual(cleanStringList(undefined), [])
  assert.deepEqual(cleanStringList('1.1.1.1'), [])
  const record = { a: 1, b: 2 }
  assert.deepEqual(setRecordKey(record, 'a', undefined), { b: 2 })
  assert.deepEqual(setRecordKey(record, 'c', 'x'), { a: 1, b: 2, c: 'x' })
  assert.deepEqual(record, { a: 1, b: 2 })
})

test('inboundStreamFieldIssues maps MASQUE pool, MTU, DNS, path and header issues to their fields', () => {
  const base = { ...createDefaultInboundForProtocol({ protocol: 'masque', clientDefaults: 'empty' }), tag: 'MQ', port: 443 }
  const draft = {
    ...base,
    address: ['10.0.0.0/24', '10.1.0.1/16'],
    mtu: 1000,
    remoteDNS: ['dns.google'],
    security: { type: 'none' },
    transport: { type: 'masque', path: 'masque', headers: { Host: 'x' }, user: 'u' },
  } as unknown as Inbound
  const issues = inboundStreamFieldIssues(validateInboundDraft(draft))
  assert.deepEqual(
    issues.map(i => [i.field, i.severity, i.code]),
    [
      ['security', 'error', 'XCK_SEMANTIC_MASQUE_TLS_REQUIRED'],
      ['address', 'error', 'XCK_SEMANTIC_MASQUE_ADDRESS_NOT_HOST'],
      ['address', 'error', 'XCK_SEMANTIC_MASQUE_ADDRESS_FAMILY_DUPLICATE'],
      ['mtu', 'error', 'XCK_SEMANTIC_MASQUE_MTU'],
      ['remoteDNS', 'error', 'XCK_SEMANTIC_MASQUE_REMOTE_DNS_INVALID'],
      ['path', 'error', 'XCK_SEMANTIC_MASQUE_PATH'],
      ['headers', 'error', 'XCK_SEMANTIC_MASQUE_HEADER'],
      ['user', 'warning', 'XCK_SEMANTIC_MASQUE_CLIENT_ONLY_FIELD'],
    ],
  )
  assert.equal(issues[1].message, "10.0.0.0/24 is a network or broadcast address, not the server's host address. Use the server's own address inside the subnet, for example 10.0.0.1/24.")
  const vlessWithMasque = { ...createDefaultInboundForProtocol({ protocol: 'vless', clientDefaults: 'empty' }), tag: 'V', port: 1, transport: { type: 'masque' } } as unknown as Inbound
  assert.deepEqual(
    inboundStreamFieldIssues(validateInboundDraft(vlessWithMasque)).map(i => i.field),
    ['transport'],
  )
})

test('inboundStreamFieldIssues keeps schema errors on the MASQUE inbound mtu, address and remoteDNS', () => {
  // A schema failure hides the kit's semantic checks, so these errors are the only ones the dialog gets.
  const base = { ...createDefaultInboundForProtocol({ protocol: 'masque', clientDefaults: 'empty' }), tag: 'MQ', port: 443 }
  for (const [patch, field] of [
    [{ mtu: '1400x' }, 'mtu'],
    [{ address: '10.14.0.1/16' }, 'address'],
    [{ address: [5] }, 'address'],
    [{ remoteDNS: [1] }, 'remoteDNS'],
  ] as const) {
    const issues = streamFieldIssuesForInbound({ ...base, ...patch } as unknown as Inbound)
    assert.deepEqual(
      issues.map(i => [i.field, i.severity, i.code]),
      [[field, 'error', 'XCK_SCHEMA_INVALID_PROFILE']],
      JSON.stringify(patch),
    )
    assert.equal(blockingStreamFieldIssues(issues).length, 1, JSON.stringify(patch))
  }
  // Other top-level schema errors stay with the generic form.
  assert.deepEqual(inboundStreamFieldIssues(validateInboundDraft({ ...base, tag: 5 } as unknown as Inbound)), [])
})

test('inboundStreamFieldIssues maps XDrive issues and drops the missing-clients warning', () => {
  const xd = XDRIVE_IN
  assert.deepEqual(
    inboundStreamFieldIssues(validateInboundDraft(xd)).map(i => [i.field, i.severity]),
    [
      ['remoteFolder', 'error'],
      ['secrets', 'error'],
    ],
  )
  const capped = { ...xd, transport: { type: 'xdrive', service: 'template', template: { a: 1 }, segmentBytes: 16777217, concurrency: 65 } } as unknown as Inbound
  const issues = inboundStreamFieldIssues(validateInboundDraft(capped))
  assert.deepEqual(
    issues.map(i => [i.field, i.severity]),
    [
      ['segmentBytes', 'warning'],
      ['concurrency', 'warning'],
    ],
  )
  assert.deepEqual(blockingStreamFieldIssues(issues), [])
  const wrongType = { ...xd, transport: { type: 'xdrive', service: 'local', remoteFolder: '/x', segmentBytes: '12x' } } as unknown as Inbound
  assert.deepEqual(
    inboundStreamFieldIssues(validateInboundDraft(wrongType)).map(i => [i.field, i.code]),
    [['segmentBytes', 'XCK_SCHEMA_INVALID_PROFILE']],
  )
})

test('outboundStreamFieldIssues maps settings, masqueSettings, warp and mux issues', () => {
  const ob = {
    protocol: 'masque',
    tag: 'MQO',
    settings: { address: '', port: 0, remoteDNS: ['dns.google'] },
    streamSettings: {
      network: 'masque',
      security: 'none',
      masqueSettings: { user: 'a:b', pass: 'p', warp: { privateKey: 'x', publicKey: 'y', address: ['1.1.1.1/32', '2.2.2.2/32'] }, headers: { Authorization: 'x', 'Capsule-Protocol': '?1' } },
    },
    mux: { enabled: true },
  } as unknown as Outbound
  assert.deepEqual(
    outboundStreamFieldIssues(validateOutboundDraft(ob)).map(i => i.field),
    ['security', 'mux', 'address', 'port', 'remoteDNS', 'user', 'headers', 'headers', 'warp', 'warp.privateKey', 'warp.publicKey', 'warp.address'],
  )
  const vx = XDRIVE_OUT
  assert.deepEqual(
    outboundStreamFieldIssues(validateOutboundDraft(vx)).map(i => i.field),
    ['remoteFolder'],
  )
  const masqueOnVless = { ...vx, streamSettings: { network: 'masque', security: 'tls' } } as unknown as Outbound
  assert.deepEqual(
    outboundStreamFieldIssues(validateOutboundDraft(masqueOnVless)).map(i => i.field),
    ['transport'],
  )
})

test('stream field issues map the XDrive VLESS rules to decryption, encryption, flow, mux and port', () => {
  const inbound = { ...XDRIVE_IN, decryption: 'none', port: '8443-8444', transport: { type: 'xdrive', service: 'local', remoteFolder: '/x' } } as unknown as Inbound
  assert.deepEqual(
    inboundStreamFieldIssues(validateInboundDraft(inbound)).map(i => [i.field, i.code]),
    [
      ['decryption', 'XCK_SEMANTIC_XDRIVE_VLESS_ENCRYPTION'],
      ['port', 'XCK_SEMANTIC_XDRIVE_SINGLE_PORT'],
    ],
  )
  const outbound = {
    ...XDRIVE_OUT,
    settings: { address: 'a', port: 443, id: '11111111-1111-4111-8111-111111111111', encryption: 'none', flow: 'xtls-rprx-vision' },
    streamSettings: { method: 'xdrive', security: 'none', xdriveSettings: { service: 'local', remoteFolder: '/x' } },
    mux: undefined,
  } as unknown as Outbound
  const issues = outboundStreamFieldIssues(validateOutboundDraft(outbound))
  assert.deepEqual(
    issues.map(i => [i.field, i.code]),
    [
      ['flow', 'XCK_SEMANTIC_XDRIVE_VLESS_FLOW'],
      ['encryption', 'XCK_SEMANTIC_XDRIVE_VLESS_ENCRYPTION'],
      ['mux', 'XCK_SEMANTIC_XDRIVE_MUX_REQUIRED'],
    ],
  )
  assert.deepEqual(
    blockingStreamFieldIssues(issues).map(i => i.field),
    ['flow', 'encryption', 'mux'],
  )
})

test('stream field issues put MASQUE xmux problems on the xmux field', () => {
  const masque = {
    protocol: 'masque',
    tag: 'MQO',
    settings: { address: '162.159.198.1', port: 443 },
    streamSettings: { network: 'masque', security: 'tls', masqueSettings: { xmux: { maxConnections: 4, maxConcurrency: '16-32' } } },
  } as unknown as Outbound
  const conflict = outboundStreamFieldIssues(validateOutboundDraft(masque))
  assert.deepEqual(
    conflict.map(i => [i.field, i.severity, i.code]),
    [['xmux', 'error', 'XCK_SEMANTIC_MASQUE_XMUX_CONFLICT']],
  )
  assert.equal(conflict[0].message, 'MASQUE xmux cannot set both maxConnections and maxConcurrency. Keep one of maxConnections or maxConcurrency, or set the other to 0.')
  assert.equal(blockingStreamFieldIssues(conflict).length, 1)
  const fixed = { ...masque, streamSettings: { network: 'masque', security: 'tls', masqueSettings: { xmux: { maxConcurrency: '16-32' } } } } as unknown as Outbound
  assert.deepEqual(outboundStreamFieldIssues(validateOutboundDraft(fixed)), [])
  const server = {
    ...createDefaultInboundForProtocol({ protocol: 'masque', clientDefaults: 'empty' }),
    tag: 'MQ',
    port: 443,
    transport: { type: 'masque', xmux: { maxConcurrency: '16-32' } },
  } as unknown as Inbound
  const serverIssues = inboundStreamFieldIssues(validateInboundDraft(server))
  assert.deepEqual(
    serverIssues.map(i => [i.field, i.severity, i.code]),
    [['xmux', 'warning', 'XCK_SEMANTIC_MASQUE_CLIENT_ONLY_FIELD']],
  )
  assert.deepEqual(blockingStreamFieldIssues(serverIssues), [])
})

test('streamFieldIssuesForInbound and streamFieldIssuesForOutbound report only for MASQUE and XDrive', () => {
  // A schema error of another transport stays with the generic form (inbound) ...
  const ws = { ...createDefaultInboundForProtocol({ protocol: 'vless', transport: 'ws', clientDefaults: 'empty' }), tag: 'W', port: 2, transport: { type: 'ws', path: 1 } } as unknown as Inbound
  assert.deepEqual(
    inboundStreamFieldIssues(validateInboundDraft(ws)).map(i => i.field),
    ['path'],
  )
  assert.deepEqual(streamFieldIssuesForInbound(ws), [])
  const masque = { ...createDefaultInboundForProtocol({ protocol: 'masque', clientDefaults: 'empty' }), tag: 'MQ', port: 443, mtu: 1000 } as unknown as Inbound
  assert.deepEqual(
    streamFieldIssuesForInbound(masque).map(i => i.field),
    ['mtu'],
  )
  assert.deepEqual(
    streamFieldIssuesForInbound(XDRIVE_IN).map(i => i.field),
    ['remoteFolder', 'secrets'],
  )
  const vlessWithMasque = { ...createDefaultInboundForProtocol({ protocol: 'vless', clientDefaults: 'empty' }), tag: 'V', port: 1, transport: { type: 'masque' } } as unknown as Inbound
  assert.deepEqual(
    streamFieldIssuesForInbound(vlessWithMasque).map(i => i.field),
    ['transport'],
  )
  // ... and a stale masqueSettings block on a ws outbound has no MASQUE form to fix it in (outbound).
  const wsOut = {
    protocol: 'vless',
    tag: 'VW',
    settings: { address: 'a', port: 443, id: '11111111-1111-4111-8111-111111111111', encryption: 'none' },
    streamSettings: { network: 'ws', security: 'none', masqueSettings: { user: 'a:b' } },
  } as unknown as Outbound
  assert.deepEqual(
    outboundStreamFieldIssues(validateOutboundDraft(wsOut)).map(i => i.field),
    ['user'],
  )
  assert.deepEqual(streamFieldIssuesForOutbound(wsOut), [])
  const masqueOut = { protocol: 'masque', tag: 'MQO', settings: { address: 'a', port: 443 }, streamSettings: { network: 'masque', security: 'none' } } as unknown as Outbound
  assert.deepEqual(
    streamFieldIssuesForOutbound(masqueOut).map(i => i.field),
    ['security'],
  )
  const xdriveOut = { ...XDRIVE_OUT, streamSettings: { method: 'XDrive', security: 'none', xdriveSettings: { service: 'local' } } } as unknown as Outbound
  assert.deepEqual(
    streamFieldIssuesForOutbound(xdriveOut).map(i => i.field),
    ['remoteFolder'],
  )
  const masqueOnVless = { ...wsOut, streamSettings: { network: 'masque', security: 'tls' } } as unknown as Outbound
  assert.deepEqual(
    streamFieldIssuesForOutbound(masqueOnVless).map(i => i.field),
    ['transport'],
  )
})

test('blockingStreamFieldIssues keeps errors except backend-managed clients', () => {
  const list = [
    { field: 'clients', severity: 'error', code: 'XCK_SEMANTIC_MASQUE_CLIENT_EMAIL', message: 'm' },
    { field: 'mtu', severity: 'error', code: 'XCK_SEMANTIC_MASQUE_MTU', message: 'm' },
    { field: 'segmentBytes', severity: 'warning', code: 'XCK_SEMANTIC_XDRIVE_SEGMENT_BYTES_CAPPED', message: 'm' },
  ] as const
  assert.deepEqual(
    blockingStreamFieldIssues(list).map(i => i.field),
    ['mtu'],
  )
})

test('stream issue mapping decodes JSON pointers and keeps the input order', () => {
  const issue = (code: string, path: string): Issue => ({ code, severity: 'info', category: 'semantic', path, message: 'm' })
  assert.deepEqual(
    inboundStreamFieldIssues([
      issue('XCK_SEMANTIC_XDRIVE_A', '/transport/a~1b~01'),
      issue('XCK_OTHER', '/transport/path'),
      issue('XCK_SEMANTIC_MASQUE_B', '/transport'),
      issue('XCK_SEMANTIC_MASQUE_C', ''),
    ]),
    [
      { field: 'a/b~1', code: 'XCK_SEMANTIC_XDRIVE_A', severity: 'info', message: 'm' },
      { field: '', code: 'XCK_SEMANTIC_MASQUE_B', severity: 'info', message: 'm' },
      { field: '', code: 'XCK_SEMANTIC_MASQUE_C', severity: 'info', message: 'm' },
    ],
  )
  assert.deepEqual(
    outboundStreamFieldIssues([
      issue('XCK_SCHEMA_INVALID_PROFILE', '/streamSettings/method'),
      issue('XCK_SCHEMA_INVALID_PROFILE', '/settings/address'),
      issue('XCK_SEMANTIC_MASQUE_D', '/streamSettings/xdriveSettings/warp'),
    ]).map(i => i.field),
    ['transport', 'warp'],
  )
})

test('outboundStreamAccordionBlockingIssues: the blocking issues the Stream & Security accordion shows', () => {
  const issue = (field: string, severity: StreamFieldIssue['severity'] = 'error'): StreamFieldIssue => ({ field, severity, code: 'XCK_SEMANTIC_MASQUE_TEST', message: field })
  const issues = [issue('security'), issue('transport'), issue('user'), issue('remoteFolder'), issue('mux', 'warning'), issue('encryption')]
  // MASQUE: the box outside the accordion shows everything but the security and transport selects' messages.
  assert.deepEqual(
    outboundStreamAccordionBlockingIssues(issues, 'masque', 'masque').map(i => i.field),
    ['security', 'transport'],
  )
  // XDrive: the XDrive box sits inside the accordion, so every blocking issue is there (warnings never open it).
  assert.deepEqual(
    outboundStreamAccordionBlockingIssues(issues, 'vless', 'XDrive').map(i => i.field),
    ['security', 'transport', 'user', 'remoteFolder', 'encryption'],
  )
  // Any other outbound: only the select messages (for example a stored masque network on VLESS).
  assert.deepEqual(
    outboundStreamAccordionBlockingIssues(issues, 'vless', 'masque').map(i => i.field),
    ['security', 'transport'],
  )
  assert.deepEqual(outboundStreamAccordionBlockingIssues([issue('security', 'warning')], 'masque', 'masque'), [])
  // Wired to the kit: an imported MASQUE outbound without TLS.
  const masqueNoTls = { protocol: 'masque', tag: 'm', settings: { address: 'a.com', port: 443 }, streamSettings: { network: 'masque', security: 'none' } } as unknown as Outbound
  assert.deepEqual(
    outboundStreamAccordionBlockingIssues(streamFieldIssuesForOutbound(masqueNoTls), 'masque', 'masque').map(i => i.code),
    ['XCK_SEMANTIC_MASQUE_TLS_REQUIRED'],
  )
})

test('streamIssueSetGained: the Stream & Security accordion opens only when its blocking set gains an issue', () => {
  const issue = (field: string, code: string): StreamFieldIssue => ({ field, code, severity: 'error', message: `${field} ${code}` })
  const tls = issue('security', 'XCK_SEMANTIC_MASQUE_TLS_REQUIRED')
  const folder = issue('remoteFolder', 'XCK_SEMANTIC_XDRIVE_REMOTE_FOLDER_REQUIRED')
  const secrets = issue('secrets', 'XCK_SEMANTIC_XDRIVE_SECRETS_REQUIRED')
  assert.equal(streamIssueSetKey([]), '')
  // Order and repeats do not change the key; messages are not part of it.
  assert.equal(streamIssueSetKey([folder, tls, folder]), streamIssueSetKey([tls, { ...folder, message: 'other text' }]))
  const one = streamIssueSetKey([tls])
  const two = streamIssueSetKey([tls, folder])
  // Mounting with blocking issues opens it (the seed compares against no issues).
  assert.equal(streamIssueSetGained('', one), true)
  assert.equal(streamIssueSetGained('', ''), false)
  assert.equal(streamIssueSetGained(one, two), true)
  // Fixing one of two issues, or all of them, leaves a collapsed section collapsed.
  assert.equal(streamIssueSetGained(two, one), false)
  assert.equal(streamIssueSetGained(two, ''), false)
  assert.equal(streamIssueSetGained(two, two), false)
  // Swapping one issue for another is a gain.
  assert.equal(streamIssueSetGained(two, streamIssueSetKey([tls, secrets])), true)
  // The same field with another code is another issue.
  assert.equal(streamIssueSetGained(one, streamIssueSetKey([issue('security', 'XCK_SEMANTIC_MASQUE_OTHER')])), true)
})
