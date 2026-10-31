import { test } from 'node:test'
import assert from 'node:assert/strict'
import i18next from 'i18next'

import { translateHtml } from './html-translation'

const i18n = i18next.createInstance()
await i18n.init({
  lng: 'en',
  interpolation: { escapeValue: false },
  resources: { en: { translation: { prompt: 'Remove the <b>{{name}}</b> node?' } } },
})

test('escapes interpolated names but keeps the markup of the translation', () => {
  assert.equal(translateHtml(i18n.t, 'prompt', { name: '<img src=x onerror=alert(1)>' }), 'Remove the <b>&lt;img src=x onerror=alert(1)&gt;</b> node?')
})

test('escapes names in the default value of a missing key', () => {
  assert.equal(translateHtml(i18n.t, 'missing', { name: '<svg onload=x>', defaultValue: 'Reset <b>{{name}}</b>?' }), 'Reset <b>&lt;svg onload=x&gt;</b>?')
})

test('the global setting still leaves values raw, so plain t() must not feed dangerouslySetInnerHTML', () => {
  assert.equal(i18n.t('prompt', { name: '<i>x</i>' }), 'Remove the <b><i>x</i></b> node?')
})
