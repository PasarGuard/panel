import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import ts from 'typescript'

const LOCALES = ['en', 'fa', 'ru', 'zh'] as const
type Locale = (typeof LOCALES)[number]

const SRC_DIR = new URL('../../../', import.meta.url)
const WIREGUARD_KEY = /^coreEditor\.(inbound|outbound)\.wireguard\./
const DASHES = /[\u2013\u2014]/

type Usage = { file: string; key: string; defaultValue: string | undefined }

const defaultValueOf = (options: ts.Expression | undefined): string | undefined => {
  if (!options || !ts.isObjectLiteralExpression(options)) return undefined
  for (const property of options.properties) {
    if (ts.isPropertyAssignment(property) && ts.isIdentifier(property.name) && property.name.text === 'defaultValue' && ts.isStringLiteralLike(property.initializer)) {
      return property.initializer.text
    }
  }
  return undefined
}

/**
 * Every `t('coreEditor.inbound.wireguard...')` / `t('coreEditor.outbound.wireguard...')` call in the dashboard
 * source, with its English `defaultValue`. Key literals used any other way are returned as `stray`, so a key
 * this scan cannot follow fails the test instead of going unchecked.
 */
function scanWireguardKeys(): { usages: Usage[]; stray: string[] } {
  const usages: Usage[] = []
  const stray: string[] = []
  for (const file of readdirSync(SRC_DIR, { recursive: true, encoding: 'utf8' })) {
    if (!/\.tsx?$/.test(file) || /\.test\.tsx?$/.test(file)) continue
    const source = readFileSync(new URL(file, SRC_DIR), 'utf8')
    if (!/coreEditor\.(inbound|outbound)\.wireguard\./.test(source)) continue
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    const visit = (node: ts.Node) => {
      if ((ts.isStringLiteralLike(node) || ts.isTemplateHead(node)) && WIREGUARD_KEY.test(node.text)) {
        const call = node.parent
        const isKey = ts.isStringLiteralLike(node) && ts.isCallExpression(call) && ts.isIdentifier(call.expression) && call.expression.text === 't' && call.arguments[0] === node
        if (isKey) usages.push({ file, key: node.text, defaultValue: defaultValueOf(call.arguments[1]) })
        else stray.push(`${file}: ${node.text}`)
      }
      ts.forEachChild(node, visit)
    }
    visit(tree)
  }
  return { usages, stray }
}

const { usages: USAGES, stray: STRAY } = scanWireguardKeys()
const KEYS = [...new Set(USAGES.map(usage => usage.key))].sort()

const readLocale = (locale: Locale): unknown => JSON.parse(readFileSync(new URL('../../../../public/statics/locales/' + locale + '.json', import.meta.url), 'utf8'))
const messages = Object.fromEntries(LOCALES.map(locale => [locale, readLocale(locale)])) as Record<Locale, unknown>

const lookup = (locale: Locale, key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => (node !== null && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined), messages[locale])

const text = (locale: Locale, key: string): string => {
  const value = lookup(locale, key)
  assert.equal(typeof value, 'string', `${key} missing in ${locale}`)
  return value as string
}

test('the source scan finds the WireGuard t() keys and their English defaults', () => {
  assert.ok(KEYS.includes('coreEditor.inbound.wireguard.validation.secretKeyInvalid'))
  assert.ok(KEYS.includes('coreEditor.outbound.wireguard.dnsNotList'))
  assert.deepEqual(STRAY, [])
  for (const usage of USAGES) assert.equal(typeof usage.defaultValue, 'string', `${usage.key} in ${usage.file} has no string defaultValue`)
})

test('WireGuard strings exist in every locale', () => {
  for (const locale of LOCALES) {
    for (const key of KEYS) {
      const value = text(locale, key)
      assert.notEqual(value.trim(), '', `${key} is empty in ${locale}`)
      assert.doesNotMatch(value, DASHES, `${key} in ${locale} contains an en or em dash`)
    }
  }
})

test('English strings match the source defaults', () => {
  for (const usage of USAGES) assert.equal(text('en', usage.key), usage.defaultValue, `${usage.key} in ${usage.file}`)
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
