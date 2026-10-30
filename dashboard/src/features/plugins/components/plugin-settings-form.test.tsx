import { test } from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from 'i18next'
import { I18nextProvider } from 'react-i18next'

import { PluginSettingsForm } from '@/features/plugins/components/plugin-settings-form'
import { getGetPluginSettingsQueryKey } from '@/service/api'

// A separate instance: keys are rendered as text and nothing suspends while translations load
const i18nForTest = i18n.createInstance()
void i18nForTest.init({ lng: 'en', resources: {}, initAsync: false, react: { useSuspense: false } })

const schema = { type: 'object', properties: { text: { type: 'string' }, enabled: { type: 'boolean' } } }

const render = (state: { data?: Record<string, unknown>; error?: Error }) => {
  const client = new QueryClient({ defaultOptions: { queries: { retryOnMount: false, staleTime: Infinity } } })
  const query = client.getQueryCache().build(client, { queryKey: getGetPluginSettingsQueryKey('banner') })
  query.setState(
    state.error
      ? { status: 'error', error: state.error, fetchStatus: 'idle', data: undefined, dataUpdatedAt: 0, errorUpdatedAt: Date.now() }
      : { status: 'success', data: state.data, fetchStatus: 'idle', dataUpdatedAt: Date.now() },
  )
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18nForTest}>
      <QueryClientProvider client={client}>
        <PluginSettingsForm pluginId="banner" schema={schema} />
      </QueryClientProvider>
    </I18nextProvider>,
  )
}

const submitButton = (html: string) => html.match(/<button[^>]*type="submit"[^>]*>/)?.[0] ?? ''

test('settings that failed to load cannot be saved over', () => {
  const html = render({ error: new Error('boom') })
  assert.ok(html.includes('role="alert"'), 'load error is shown')
  assert.ok(/\sdisabled=""/.test(submitButton(html)), 'save is disabled')
  assert.ok(/<input[^>]*id="plugin-field-text"[^>]*disabled=""/.test(html), 'fields are disabled')
})

test('loaded settings can be edited and saved', () => {
  const html = render({ data: { text: 'hi', enabled: true } })
  assert.ok(!html.includes('role="alert"'))
  assert.ok(!/\sdisabled=""/.test(submitButton(html)))
})
