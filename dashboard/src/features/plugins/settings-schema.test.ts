import { test } from 'node:test'
import assert from 'node:assert/strict'

import { fieldKind, fromFormValues, schemaFields, toFormValues } from './settings-schema.ts'

const schema = {
  type: 'object',
  required: ['days'],
  properties: {
    days: { type: 'integer', title: 'Days', minimum: 1, default: 7 },
    ratio: { type: 'number' },
    text: { type: 'string' },
    enabled: { type: 'boolean' },
    mode: { type: 'string', enum: ['a', 'b'] },
    tags: { type: 'array', items: { type: 'string' } },
    plans: { type: 'object' },
  },
}

test('maps schema types to field kinds', () => {
  const kinds = Object.fromEntries(schemaFields(schema).map(field => [field.name, field.kind]))
  assert.deepEqual(kinds, {
    days: 'integer',
    ratio: 'number',
    text: 'string',
    enabled: 'boolean',
    mode: 'enum',
    tags: 'string-array',
    plans: 'json',
  })
  assert.equal(fieldKind({ type: ['integer', 'null'] }), 'integer')
  assert.equal(fieldKind({ type: 'array', items: { type: 'integer' } }), 'json')
  const days = schemaFields(schema)[0]
  assert.equal(days.label, 'Days')
  assert.equal(days.required, true)
  assert.equal(days.minimum, 1)
})

test('round-trips settings through form values', () => {
  const fields = schemaFields(schema)
  const settings = { days: 7, ratio: 0.5, text: 'hi', enabled: true, mode: 'b', tags: ['x', 'y'], plans: { gold: 'Gold' }, hidden: 1 }
  const values = toFormValues(fields, settings)
  assert.equal(values.tags, 'x\ny')
  assert.equal(values.days, '7')
  const { data, errors } = fromFormValues(fields, values, settings)
  assert.deepEqual(errors, {})
  assert.deepEqual(data, settings)
})

test('reports invalid numbers and JSON', () => {
  const fields = schemaFields(schema)
  const values = { ...toFormValues(fields, {}), days: '1.5', ratio: 'abc', plans: '{bad' }
  const { errors } = fromFormValues(fields, values)
  assert.deepEqual(errors, { days: 'number', ratio: 'number', plans: 'json' })
})

test('keeps null and missing keys when other fields are saved', () => {
  const fields = schemaFields({
    type: 'object',
    properties: {
      token: { type: ['string', 'null'], default: null },
      limit: { type: ['integer', 'null'] },
      note: { type: 'string' },
      title: { type: 'string' },
      mode: { type: 'string', enum: ['a', 'b'] },
      days: { type: 'integer' },
    },
  })
  assert.equal(fields[0].nullable, true)
  assert.equal(fields[2].nullable, false)
  const settings = { token: null, limit: null, title: 'old', days: 3 }
  const values = { ...toFormValues(fields, settings), days: '5', title: '' }
  const { data, errors } = fromFormValues(fields, values, settings)
  assert.deepEqual(errors, {})
  // null stays null, an absent optional string or enum is not sent as '', a cleared text field is ''
  assert.deepEqual(data, { token: null, limit: null, title: '', days: 5 })
  assert.equal('note' in data, false)
  assert.equal('mode' in data, false)
})
