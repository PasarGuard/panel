import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  clientProfileFormDefaultValues,
  clientProfileFormSchema,
  clientProfileFormToPayload,
  clientProfileToFormValues,
  DEFAULT_TEMPLATE_VALUE,
  profileIdsToDetach,
  type ClientProfileFormValues,
} from './client-profile-form'

const withValues = (patch: Partial<ClientProfileFormValues>): ClientProfileFormValues => ({ ...structuredClone(clientProfileFormDefaultValues), name: 'Happ', ...patch })

test('empty form sends inherit (null) for every override and no templates', () => {
  const payload = clientProfileFormToPayload(withValues({ name: '  Happ  ', note: '   ' }))
  assert.deepEqual(payload, {
    name: 'Happ',
    note: null,
    templates: {},
    settings: {
      profile_title: null,
      support_url: null,
      announce: null,
      announce_url: null,
      update_interval: null,
      randomize_order: null,
      response_headers: {},
      remove_response_headers: [],
      custom_variables: [],
    },
  })
})

test('filled form maps templates, trimmed texts, interval and tri-state randomize', () => {
  const payload = clientProfileFormToPayload(
    withValues({
      templates: { xray_subscription: '3', singbox_subscription: DEFAULT_TEMPLATE_VALUE, clash_subscription: '7' },
      profile_title: ' VIP ',
      support_url: 'https://t.me/support',
      announce: 'Hello',
      announce_url: '',
      update_interval: ' 6 ',
      randomize_order: 'off',
    }),
  )
  assert.deepEqual(payload.templates, { xray_subscription: 3, clash_subscription: 7 })
  assert.equal(payload.settings?.profile_title, 'VIP')
  assert.equal(payload.settings?.support_url, 'https://t.me/support')
  assert.equal(payload.settings?.announce, 'Hello')
  assert.equal(payload.settings?.announce_url, null)
  assert.equal(payload.settings?.update_interval, 6)
  assert.equal(payload.settings?.randomize_order, false)
  assert.equal(clientProfileFormToPayload(withValues({ randomize_order: 'on' })).settings?.randomize_order, true)
  assert.equal(clientProfileFormToPayload(withValues({ randomize_order: 'inherit' })).settings?.randomize_order, null)
})

test('headers and variables: blank rows dropped, removed headers deduplicated case-insensitively', () => {
  const payload = clientProfileFormToPayload(
    withValues({
      response_headers: [
        { key: ' X-Plan ', value: '{USERNAME}' },
        { key: '', value: '' },
      ],
      remove_response_headers: ['Announce', ' announce ', '', 'Profile-Title'],
      custom_variables: [
        { key: 'CUSTOM_HOST', value: 'a.example.com' },
        { key: '', value: '' },
      ],
    }),
  )
  assert.deepEqual(payload.settings?.response_headers, { 'X-Plan': '{USERNAME}' })
  assert.deepEqual(payload.settings?.remove_response_headers, ['Announce', 'Profile-Title'])
  assert.deepEqual(payload.settings?.custom_variables, [{ key: 'CUSTOM_HOST', value: 'a.example.com' }])
})

test('API profile round-trips through the form unchanged', () => {
  const profile = {
    name: 'Happ',
    note: 'for iOS',
    templates: { singbox_subscription: 12 },
    settings: {
      profile_title: 'VIP',
      support_url: null,
      announce: null,
      announce_url: 'https://example.com',
      update_interval: 24,
      randomize_order: true,
      response_headers: { 'X-A': '1' },
      remove_response_headers: ['Announce'],
      custom_variables: [{ key: 'CUSTOM_X', value: 'y' }],
    },
  }
  const values = clientProfileToFormValues(profile)
  assert.equal(values.templates.singbox_subscription, '12')
  assert.equal(values.templates.xray_subscription, DEFAULT_TEMPLATE_VALUE)
  assert.equal(values.support_url, '')
  assert.equal(values.update_interval, '24')
  assert.equal(values.randomize_order, 'on')
  assert.deepEqual(clientProfileFormToPayload(values), profile)
})

test('old profile without settings/templates opens as all-inherit', () => {
  const values = clientProfileToFormValues({ name: 'Old', note: null })
  assert.equal(values.randomize_order, 'inherit')
  assert.equal(values.update_interval, '')
  assert.deepEqual(values.response_headers, [])
  assert.equal(clientProfileToFormValues({ name: 'Old', settings: { randomize_order: false } }).randomize_order, 'off')
})

test('schema rejects bad interval, header names, duplicate and built-in variables', () => {
  const issues = (patch: Partial<ClientProfileFormValues>) => {
    const result = clientProfileFormSchema.safeParse(withValues(patch))
    return result.success ? [] : result.error.issues.map(issue => issue.message)
  }
  assert.deepEqual(issues({}), [])
  assert.deepEqual(issues({ update_interval: '0' }), ['clientProfiles.validation.wholeNumber'])
  assert.deepEqual(issues({ update_interval: '1.5' }), ['clientProfiles.validation.wholeNumber'])
  assert.deepEqual(issues({ response_headers: [{ key: 'Bad Header', value: 'x' }] }), ['clientProfiles.validation.headerName'])
  assert.deepEqual(
    issues({
      response_headers: [
        { key: 'X-A', value: '1' },
        { key: 'x-a', value: '2' },
      ],
    }),
    ['clientProfiles.validation.duplicateHeader'],
  )
  assert.deepEqual(issues({ remove_response_headers: ['ok', 'not ok'] }), ['clientProfiles.validation.headerName'])
  assert.deepEqual(issues({ custom_variables: [{ key: 'USERNAME', value: 'x' }] }), ['clientProfiles.validation.variableBuiltin'])
  assert.deepEqual(
    issues({
      custom_variables: [
        { key: 'CUSTOM_A', value: '1' },
        { key: 'CUSTOM_A', value: '2' },
      ],
    }),
    ['clientProfiles.validation.variableDuplicate'],
  )
  assert.deepEqual(issues({ custom_variables: [{ key: '', value: 'orphan' }] }), ['clientProfiles.validation.variableKey'])
  assert.deepEqual(issues({ name: '   ' }), ['validation.required'])
})

test('detaching selected users from their profiles', () => {
  const loaded = [
    { id: 1, client_profile_id: 5 },
    { id: 2, client_profile_id: null },
    { id: 3, client_profile_id: 5 },
    { id: 4, client_profile_id: 9 },
  ]
  assert.deepEqual(profileIdsToDetach([1, 2, 3], loaded, [5, 9, 11]), [5])
  assert.deepEqual(profileIdsToDetach([2], loaded, [5, 9, 11]), [])
  assert.deepEqual(profileIdsToDetach([1, 4], loaded, [5, 9, 11]), [5, 9])
  // A selected user that is not loaded (another page): fall back to every profile
  assert.deepEqual(profileIdsToDetach([1, 42], loaded, [5, 9, 11]), [5, 9, 11])
})
