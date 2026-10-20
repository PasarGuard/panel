import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const LOCALES = ['en', 'fa', 'ru', 'zh'] as const
type Locale = (typeof LOCALES)[number]

const KEYS = [
  'coreEditor.inbound.wireguard.publicKeyHint',
  'coreEditor.inbound.wireguard.publicKeyUnavailable',
  'coreEditor.inbound.wireguard.addressPoolHint',
  'coreEditor.inbound.wireguard.addressNoPool',
  'coreEditor.inbound.wireguard.addressInvalid',
  'coreEditor.inbound.wireguard.mtuHint',
  'coreEditor.inbound.wireguard.reserved',
  'coreEditor.inbound.wireguard.reservedHint',
  'coreEditor.inbound.wireguard.validation.secretKeyInvalid',
  'coreEditor.inbound.wireguard.validation.portSingle',
  'coreEditor.inbound.wireguard.validation.mtuRange',
  'coreEditor.inbound.wireguard.validation.reservedFormat',
  'coreEditor.outbound.wireguard.kernelModeKernel',
  'coreEditor.outbound.wireguard.kernelModeUserspace',
  'coreEditor.outbound.wireguard.kernelModeHint',
  'coreEditor.outbound.wireguard.legacyFieldHint',
  'coreEditor.outbound.wireguard.dnsHint',
  'coreEditor.outbound.wireguard.dnsAddPlaceholder',
  'coreEditor.outbound.wireguard.dnsItems',
  'coreEditor.outbound.wireguard.noDns',
  'coreEditor.outbound.wireguard.dnsInvalid',
  'coreEditor.outbound.wireguard.dnsNotList',
  'coreEditor.outbound.wireguard.reservedHint',
  'coreEditor.outbound.wireguard.reservedInvalid',
]

const readLocale = (locale: Locale): unknown => JSON.parse(readFileSync(new URL('../../../../public/statics/locales/' + locale + '.json', import.meta.url), 'utf8'))
const messages = Object.fromEntries(LOCALES.map(locale => [locale, readLocale(locale)])) as Record<Locale, unknown>

const lookup = (locale: Locale, key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => (node !== null && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined), messages[locale])

const text = (locale: Locale, key: string): string => {
  const value = lookup(locale, key)
  assert.equal(typeof value, 'string', `${key} missing in ${locale}`)
  return value as string
}

test('new WireGuard strings exist in every locale', () => {
  for (const locale of LOCALES) {
    for (const key of KEYS) {
      const value = text(locale, key)
      assert.notEqual(value.trim(), '', `${key} is empty in ${locale}`)
      assert.doesNotMatch(value, /[–—]/, `${key} in ${locale} contains an en or em dash`)
    }
  }
})

test('sentences are translated', () => {
  for (const key of KEYS) {
    const english = text('en', key)
    if (!english.includes(' ')) continue
    for (const locale of ['fa', 'ru', 'zh'] as const) {
      assert.notEqual(text(locale, key), english, `${key} in ${locale} is still English`)
    }
  }
})

test('placeholders survive translation', () => {
  for (const key of KEYS) {
    const placeholders = text('en', key).match(/\{\{\w+\}\}/g) ?? []
    for (const locale of LOCALES) {
      for (const placeholder of placeholders) {
        assert.ok(text(locale, key).includes(placeholder), `${key} in ${locale} lost ${placeholder}`)
      }
    }
  }
})
