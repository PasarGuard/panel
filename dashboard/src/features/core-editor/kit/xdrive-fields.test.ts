import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createDefaultInboundForProtocol, XDRIVE_DEFAULTS } from '@pasarguard/xray-config-kit'
import type { Inbound } from '@pasarguard/xray-config-kit'
import { blockingStreamFieldIssues, streamFieldIssuesForInbound } from '@/features/core-editor/kit/stream-form-fields'
import {
  applyXdriveService,
  defaultXdriveSettings,
  isXdriveGoogleDriveService,
  parseXdriveNumberInput,
  setXdriveGoogleDriveSecret,
  vlessFlowSelectValues,
  vlessVisionFlowHintShown,
  withXdriveInboundFlowIssue,
  XDRIVE_TUNING_FIELDS,
  XDRIVE_UINT32_MAX,
  xdriveGoogleDriveSecrets,
  xdriveServiceSelectOptions,
} from '@/features/core-editor/kit/xdrive-fields'

test('tuning fields are the XDrive numbers the kit documents', () => {
  assert.deepEqual([...XDRIVE_TUNING_FIELDS], Object.keys(XDRIVE_DEFAULTS))
})

test('parseXdriveNumberInput accepts uint32 only', () => {
  assert.equal(XDRIVE_UINT32_MAX, 2 ** 32 - 1)
  assert.deepEqual(parseXdriveNumberInput(''), { ok: true, value: undefined })
  assert.deepEqual(parseXdriveNumberInput(' 300 '), { ok: true, value: 300 })
  assert.deepEqual(parseXdriveNumberInput('0'), { ok: true, value: 0 })
  assert.deepEqual(parseXdriveNumberInput('16777217'), { ok: true, value: 16777217 })
  assert.deepEqual(parseXdriveNumberInput('4294967295'), { ok: true, value: 4294967295 })
  for (const raw of ['4294967296', '-1', '1.5', '1e3', '0x10', '12x']) assert.deepEqual(parseXdriveNumberInput(raw), { ok: false }, raw)
})

test('applyXdriveService keeps only what the service reads', () => {
  const gd = { type: 'xdrive', service: 'Google Drive', remoteFolder: 'xd', secrets: ['a', 'b', 'c'], segmentBytes: 1048576 }
  assert.deepEqual(applyXdriveService(gd, 'local'), { type: 'xdrive', service: 'local', remoteFolder: 'xd', segmentBytes: 1048576 })
  assert.deepEqual(applyXdriveService(gd, 'template'), { type: 'xdrive', service: 'template', remoteFolder: 'xd', secrets: ['a', 'b', 'c'], segmentBytes: 1048576 })
  assert.deepEqual(applyXdriveService({ service: 'template', secrets: ['t0'], template: { auth: { type: 'basic' } } }, 'Google Drive'), { service: 'Google Drive', secrets: ['t0', '', ''] })
  assert.deepEqual(applyXdriveService({ service: 'template', secrets: ['1', '2', '3', '4'] }, 'Google Drive'), { service: 'Google Drive', secrets: ['1', '2', '3'] })
  assert.deepEqual(applyXdriveService({ service: 'local', remoteFolder: '/x' }, 'Google Drive'), { service: 'Google Drive', remoteFolder: '/x', secrets: ['', '', ''] })
  assert.deepEqual(applyXdriveService({ service: 'local', secrets: 'x' }, 'template'), { service: 'template' })
  assert.deepEqual(gd, { type: 'xdrive', service: 'Google Drive', remoteFolder: 'xd', secrets: ['a', 'b', 'c'], segmentBytes: 1048576 })
})

test('both Google Drive spellings are one service and the stored spelling stays', () => {
  assert.equal(isXdriveGoogleDriveService('Google Drive'), true)
  assert.equal(isXdriveGoogleDriveService('google-drive'), true)
  for (const service of ['local', 'template', 'google drive', '', undefined, 1]) assert.equal(isXdriveGoogleDriveService(service), false, String(service))
  const newer = { service: 'google-drive', remoteFolder: 'xd', secrets: ['a'], template: { a: 1 } }
  assert.deepEqual(applyXdriveService(newer, 'Google Drive'), { service: 'google-drive', remoteFolder: 'xd', secrets: ['a', '', ''] })
  assert.deepEqual(applyXdriveService({ service: 'Google Drive', secrets: ['a', 'b', 'c'] }, 'google-drive'), { service: 'Google Drive', secrets: ['a', 'b', 'c'] })
  assert.deepEqual(applyXdriveService(newer, 'local'), { service: 'local', remoteFolder: 'xd' })
  assert.deepEqual(applyXdriveService({ service: 'local' }, 'google-drive'), { service: 'google-drive', secrets: ['', '', ''] })
})

test('the service select offers one Google Drive item in the stored spelling', () => {
  assert.deepEqual(xdriveServiceSelectOptions('Google Drive'), ['local', 'Google Drive', 'template'])
  assert.deepEqual(xdriveServiceSelectOptions('google-drive'), ['local', 'google-drive', 'template'])
  assert.deepEqual(xdriveServiceSelectOptions('local'), ['local', 'Google Drive', 'template'])
  assert.deepEqual(xdriveServiceSelectOptions(undefined), ['local', 'Google Drive', 'template'])
  assert.deepEqual(xdriveServiceSelectOptions(''), ['local', 'Google Drive', 'template'])
  // An unknown stored service stays first so the select stays controlled; the kit reports it.
  assert.deepEqual(xdriveServiceSelectOptions('dropbox'), ['dropbox', 'local', 'Google Drive', 'template'])
})

test('Google Drive secrets stay three trimmed entries', () => {
  assert.deepEqual(xdriveGoogleDriveSecrets({ secrets: ['a'] }), ['a', '', ''])
  assert.deepEqual(xdriveGoogleDriveSecrets({ secrets: 'a' }), ['', '', ''])
  assert.deepEqual(xdriveGoogleDriveSecrets({ secrets: ['a', 7, 'c', 'd'] }), ['a', '', 'c'])
  assert.deepEqual(setXdriveGoogleDriveSecret({ service: 'Google Drive', secrets: ['a'] }, 2, '  token  '), { service: 'Google Drive', secrets: ['a', '', 'token'] })
  // `parseTrimmedTextInput` gives undefined for an empty input; Google Drive keeps the slot as ''.
  assert.deepEqual(setXdriveGoogleDriveSecret({ service: 'google-drive', secrets: ['a', 'b', 'c', 'd'] }, 0, undefined), { service: 'google-drive', secrets: ['', 'b', 'c'] })
  const stored = { secrets: ['a', 'b', 'c'] }
  setXdriveGoogleDriveSecret(stored, 1, 'x')
  assert.deepEqual(stored, { secrets: ['a', 'b', 'c'] })
})

test('defaultXdriveSettings matches the kit default transport', () => {
  assert.deepEqual(defaultXdriveSettings(), { service: 'Google Drive', remoteFolder: '', secrets: ['', '', ''] })
  const first = defaultXdriveSettings()
  ;(first.secrets as string[])[0] = 'changed'
  first.remoteFolder = 'changed'
  assert.deepEqual(defaultXdriveSettings(), { service: 'Google Drive', remoteFolder: '', secrets: ['', '', ''] })
})

// The server half of a VLESS Encryption pair from `xray vlessenc` (X25519): Xray v26.10.17 runs xdrive only on VLESS with decryption.
const VLESS_DECRYPTION = 'mlkem768x25519plus.native.600s.KGoJgsdMC5rWUr1fnyXxteBAgbbWIQ_YKVnFWpxXBWk'
const XDRIVE_IN = {
  ...createDefaultInboundForProtocol({ protocol: 'vless', transport: 'xdrive', clientDefaults: 'empty' }),
  tag: 'XD',
  port: 8443,
  decryption: VLESS_DECRYPTION,
  transport: { type: 'xdrive', service: 'local', remoteFolder: '/x' },
} as unknown as Inbound
const FLOW_MESSAGE = 'XDrive does not support VLESS flow.'

test('withXdriveInboundFlowIssue blocks an inbound-level flow on a VLESS XDrive inbound without clients', () => {
  assert.deepEqual(streamFieldIssuesForInbound(XDRIVE_IN), [])
  const withFlow = { ...XDRIVE_IN, flow: 'xtls-rprx-vision' } as unknown as Inbound
  const kitIssues = streamFieldIssuesForInbound(withFlow)
  // The kit flags the inbound flow only through a client that inherits it, and this inbound has no clients.
  assert.deepEqual(kitIssues, [])
  const issues = withXdriveInboundFlowIssue(kitIssues, withFlow, FLOW_MESSAGE)
  assert.deepEqual(blockingStreamFieldIssues(issues), [{ field: 'flow', code: 'XCK_SEMANTIC_XDRIVE_VLESS_FLOW', severity: 'error', message: FLOW_MESSAGE }])
  assert.deepEqual(kitIssues, [])
})

test('withXdriveInboundFlowIssue adds nothing when the kit reports the flow or the rule does not apply', () => {
  // A client without its own flow inherits the inbound flow, so the kit itself reports it on `flow`.
  const inherited = { ...XDRIVE_IN, flow: 'xtls-rprx-vision', clients: [{ protocol: 'vless', id: '11111111-1111-4111-8111-111111111111', email: 'a' }] } as unknown as Inbound
  const kitIssues = streamFieldIssuesForInbound(inherited)
  assert.equal(kitIssues.filter(issue => issue.field === 'flow').length, 1)
  assert.deepEqual(withXdriveInboundFlowIssue(kitIssues, inherited, FLOW_MESSAGE), kitIssues)

  const unchanged: Array<[string, Inbound]> = [
    ['no flow', XDRIVE_IN],
    ['empty flow', { ...XDRIVE_IN, flow: '' } as unknown as Inbound],
    ['blank flow', { ...XDRIVE_IN, flow: '  ' } as unknown as Inbound],
    ['tcp', { ...createDefaultInboundForProtocol({ protocol: 'vless', transport: 'tcp', security: 'tls', clientDefaults: 'empty' }), flow: 'xtls-rprx-vision' } as unknown as Inbound],
    ['vmess', { ...createDefaultInboundForProtocol({ protocol: 'vmess', clientDefaults: 'empty' }), transport: { type: 'xdrive', service: 'local', remoteFolder: '/x' } } as unknown as Inbound],
  ]
  for (const [label, inbound] of unchanged) {
    const issues = streamFieldIssuesForInbound(inbound)
    assert.deepEqual(withXdriveInboundFlowIssue(issues, inbound, FLOW_MESSAGE), issues, label)
  }
})

test('a VLESS Flow select (inbound or outbound) offers no flow on xdrive, but a stored flow stays visible', () => {
  const vision = ['xtls-rprx-vision']
  assert.deepEqual(vlessFlowSelectValues('xdrive', '', vision), [])
  assert.deepEqual(vlessFlowSelectValues('xdrive', '  ', vision), [])
  assert.deepEqual(vlessFlowSelectValues('xdrive', 'xtls-rprx-vision', vision), ['xtls-rprx-vision'])
  assert.deepEqual(vlessFlowSelectValues('XDrive', 'xtls-rprx-vision', []), ['xtls-rprx-vision'])
  // Other transports offer what the transport and security allow.
  assert.deepEqual(vlessFlowSelectValues('tcp', '', vision), vision)
  assert.deepEqual(vlessFlowSelectValues('tcp', 'xtls-rprx-vision', []), [])
  assert.deepEqual(vlessFlowSelectValues('xhttp', '', vision), vision)
  // Outbound: both Vision flows; on xdrive only the stored one (the kit error says to remove it).
  const outboundVision = ['xtls-rprx-vision', 'xtls-rprx-vision-udp443']
  assert.deepEqual(vlessFlowSelectValues('xdrive', 'xtls-rprx-vision-udp443', outboundVision), ['xtls-rprx-vision-udp443'])
  assert.deepEqual(vlessFlowSelectValues('xdrive', '', outboundVision), [])
  assert.deepEqual(vlessFlowSelectValues('', '', outboundVision), outboundVision)
})

test('the Vision hint under a VLESS Flow select stays hidden on xdrive, which offers no flow', () => {
  assert.equal(vlessVisionFlowHintShown('tcp', false), true)
  assert.equal(vlessVisionFlowHintShown('', false), true)
  assert.equal(vlessVisionFlowHintShown('tcp', true), false)
  assert.equal(vlessVisionFlowHintShown('xdrive', false), false)
  assert.equal(vlessVisionFlowHintShown(' XDrive ', false), false)
})
