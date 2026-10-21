import { test } from 'node:test'
import assert from 'node:assert/strict'

import { XDRIVE_DEFAULTS } from '@pasarguard/xray-config-kit'
import {
  applyXdriveService,
  defaultXdriveSettings,
  isXdriveGoogleDriveService,
  parseXdriveNumberInput,
  setXdriveGoogleDriveSecret,
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
