import { test } from 'node:test'
import assert from 'node:assert/strict'

import { getCountryCodes, getCountryFlag, getCountryName, getCountryOptions, normalizeCountryCode } from './countries.ts'

test('country codes are discovered at runtime from Intl region data', () => {
  const codes = getCountryCodes()
  assert.ok(codes.length >= 240, `expected most ISO regions, got ${codes.length}`)
  for (const code of ['DE', 'US', 'RU', 'IR', 'CN', 'NL', 'FI']) assert.ok(codes.includes(code), code)
  for (const code of codes) assert.match(code, /^[A-Z]{2}$/)
  for (const code of ['AA', 'QO', 'XA', 'XB', 'ZZ']) assert.ok(!codes.includes(code), `pseudo-region ${code} must be skipped`)
  assert.ok(codes.includes('XK'))
  assert.equal(new Set(codes).size, codes.length)
})

test('flag emoji is built from regional indicator symbols', () => {
  assert.equal(getCountryFlag('DE'), '\u{1F1E9}\u{1F1EA}')
  assert.equal(getCountryFlag('us'), '\u{1F1FA}\u{1F1F8}')
  assert.equal(getCountryFlag(null), '')
  assert.equal(getCountryFlag(''), '')
  assert.equal(getCountryFlag('DEU'), '')
  assert.equal(getCountryFlag('1A'), '')
})

test('country names follow the requested language and fall back to the code', () => {
  assert.equal(getCountryName('DE', 'en'), 'Germany')
  assert.equal(getCountryName('de', 'ru'), 'Германия')
  assert.equal(getCountryName(undefined), '')
})

test('normalization uppercases valid codes and rejects the rest', () => {
  assert.equal(normalizeCountryCode(' nl '), 'NL')
  assert.equal(normalizeCountryCode(''), null)
  assert.equal(normalizeCountryCode('NLD'), null)
})

test('options are sorted by localized name', () => {
  const options = getCountryOptions('en')
  assert.equal(options.length, getCountryCodes().length)
  const names = options.map(option => option.name)
  assert.deepEqual(names, [...names].sort(new Intl.Collator(['en']).compare))
})

test('deprecated aliases and non-country groupings are not offered', () => {
  const codes = getCountryCodes()
  for (const code of ['DD', 'UK', 'SU', 'YU', 'CS', 'AN', 'EU', 'EZ', 'UN', 'ZZ', 'QO']) {
    assert.ok(!codes.includes(code), `${code} should not be listed`)
  }
  for (const code of ['DE', 'GB', 'RU', 'RS', 'CW', 'XK']) {
    assert.ok(codes.includes(code), `${code} should be listed`)
  }
  const names = getCountryOptions('en').map(option => option.name)
  assert.equal(new Set(names).size, names.length)
})
