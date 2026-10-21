// Test support for the *-locales.test.ts suites only: it imports node:test and typescript, so app code must not import it.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import ts from 'typescript'

const LOCALES = ['en', 'fa', 'ru', 'zh'] as const
type Locale = (typeof LOCALES)[number]

const SRC_DIR = new URL('../../../', import.meta.url)
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
 * Every `t('<key>')` call in the dashboard source whose key matches `keyPattern`, with its English
 * `defaultValue`. Key literals used any other way are returned as `stray`, so a key this scan cannot follow
 * fails the test instead of going unchecked. Test files are skipped; a file is parsed only when its text
 * matches `keyPattern` without its leading `^`.
 */
function scanLocaleKeys(keyPattern: RegExp): { usages: Usage[]; stray: string[] } {
  const prefilter = new RegExp(keyPattern.source.replace(/^\^/, ''), keyPattern.flags)
  const usages: Usage[] = []
  const stray: string[] = []
  for (const file of readdirSync(SRC_DIR, { recursive: true, encoding: 'utf8' })) {
    if (!/\.tsx?$/.test(file) || /\.test\.tsx?$/.test(file)) continue
    const source = readFileSync(new URL(file, SRC_DIR), 'utf8')
    if (!prefilter.test(source)) continue
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    const visit = (node: ts.Node) => {
      if ((ts.isStringLiteralLike(node) || ts.isTemplateHead(node)) && keyPattern.test(node.text)) {
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

const readLocale = (locale: Locale): unknown => JSON.parse(readFileSync(new URL('../../../../public/statics/locales/' + locale + '.json', import.meta.url), 'utf8'))
const messages = Object.fromEntries(LOCALES.map(locale => [locale, readLocale(locale)])) as Record<Locale, unknown>

const lookup = (locale: Locale, key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => (node !== null && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined), messages[locale])

const text = (locale: Locale, key: string): string => {
  const value = lookup(locale, key)
  assert.equal(typeof value, 'string', `${key} missing in ${locale}`)
  return value as string
}

/**
 * Registers five tests, named `${label}: ...`, for the `t()` keys matching `keyPattern`: the source scan
 * finds every `sentinelKeys` entry and a literal English default for each call, every locale has a non-empty
 * string with no en or em dash, en equals the source defaults, sentences are translated, and `{{placeholders}}`
 * survive translation.
 */
export function defineLocaleKeySuite(label: string, keyPattern: RegExp, sentinelKeys: readonly string[]): void {
  const { usages, stray } = scanLocaleKeys(keyPattern)
  const keys = [...new Set(usages.map(usage => usage.key))].sort()

  test(`${label}: the source scan finds the t() keys and their English defaults`, () => {
    for (const key of sentinelKeys) assert.ok(keys.includes(key), `${key} not found in the source`)
    assert.deepEqual(stray, [])
    for (const usage of usages) assert.equal(typeof usage.defaultValue, 'string', `${usage.key} in ${usage.file} has no string defaultValue`)
  })

  test(`${label}: strings exist in every locale`, () => {
    for (const locale of LOCALES) {
      for (const key of keys) {
        const value = text(locale, key)
        assert.notEqual(value.trim(), '', `${key} is empty in ${locale}`)
        assert.doesNotMatch(value, DASHES, `${key} in ${locale} contains an en or em dash`)
      }
    }
  })

  test(`${label}: English strings match the source defaults`, () => {
    for (const usage of usages) assert.equal(text('en', usage.key), usage.defaultValue, `${usage.key} in ${usage.file}`)
  })

  test(`${label}: sentences are translated`, () => {
    for (const key of keys) {
      const english = text('en', key)
      if (!english.includes(' ')) continue
      for (const locale of ['fa', 'ru', 'zh'] as const) {
        assert.notEqual(text(locale, key), english, `${key} in ${locale} is still English`)
      }
    }
  })

  test(`${label}: placeholders survive translation`, () => {
    for (const key of keys) {
      const placeholders = text('en', key).match(/\{\{\w+\}\}/g) ?? []
      for (const locale of LOCALES) {
        for (const placeholder of placeholders) {
          assert.ok(text(locale, key).includes(placeholder), `${key} in ${locale} lost ${placeholder}`)
        }
      }
    }
  })
}
