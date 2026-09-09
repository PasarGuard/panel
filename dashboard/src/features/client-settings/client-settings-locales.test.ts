import { describe, expect, test } from 'bun:test'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const files = [
  resolve(import.meta.dir, '../../pages/_dashboard.client-settings.tsx'),
  ...readdirSync(import.meta.dir)
    .filter(name => name.endsWith('.tsx'))
    .map(name => resolve(import.meta.dir, name)),
  resolve(import.meta.dir, 'components/native-configuration-editor.tsx'),
]
const keys = [...new Set(files.flatMap(file => [...readFileSync(file, 'utf8').matchAll(/t\(['"](clientSettings\.[\w.]+)['"]/g)].map(match => match[1])))].sort()
const value = (data: Record<string, unknown>, key: string): unknown =>
  key.split('.').reduce<unknown>((current, part) => (current && typeof current === 'object' ? (current as Record<string, unknown>)[part] : undefined), data)
const locale = (lang: string) => JSON.parse(readFileSync(resolve(import.meta.dir, `../../../public/statics/locales/${lang}.json`), 'utf8'))
const english = locale('en')

describe('client settings localization', () => {
  test('covers the application workspace and native editor', () => expect(keys.length).toBeGreaterThan(120))
  for (const lang of ['en', 'ru', 'fa', 'zh']) {
    test(`all visible strings and interpolation parameters exist in ${lang}`, () => {
      const data = locale(lang)
      for (const key of keys) {
        const translated = value(data, key)
        expect(typeof translated, `${lang}: ${key}`).toBe('string')
        expect(String(translated).trim().length, `${lang}: ${key}`).toBeGreaterThan(0)
        const parameters = (text: unknown) => [...String(text).matchAll(/\{\{(\w+)\}\}/g)].map(match => match[1]).sort()
        expect(parameters(translated), `${lang}: ${key}`).toEqual(parameters(value(english, key)))
      }
    })
  }
})
