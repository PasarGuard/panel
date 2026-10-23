import { test } from 'node:test'
import assert from 'node:assert/strict'

import { isNoteOnlyCoreEdit, type CoreConfigFormValues } from '@/features/nodes/forms/core-config-form'

const saved: Partial<CoreConfigFormValues> = {
  name: 'main',
  type: 'xray',
  config: JSON.stringify({ inbounds: [], outbounds: [{ tag: 'direct', protocol: 'freedom' }] }, null, 2),
  fallback_id: ['a', 'b'],
  excluded_inbound_ids: [],
  restart_nodes: true,
  note: 'EU config',
}

test('only the note changed', () => {
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: 'edited' }), true)
  // Reformatted JSON, reordered tags and the restart toggle are not changes.
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: '', config: JSON.stringify(JSON.parse(saved.config!)), fallback_id: ['b', 'a'], restart_nodes: false }), true)
})

test('no note change or other changes are not note-only', () => {
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved }), false)
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: '  EU config ' }), false)
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: 'edited', name: 'renamed' }), false)
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: 'edited', config: '{"inbounds": []}' }), false)
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: 'edited', fallback_id: ['a'] }), false)
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: 'edited', excluded_inbound_ids: ['x'] }), false)
  assert.equal(isNoteOnlyCoreEdit(saved, { ...saved, note: 'edited', type: 'wg' }), false)
  assert.equal(isNoteOnlyCoreEdit(undefined, { ...saved, note: 'edited' }), false)
})
