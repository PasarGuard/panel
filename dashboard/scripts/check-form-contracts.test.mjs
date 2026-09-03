// Node >= 22.18: node --test scripts/check-form-contracts.test.mjs
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { zodResolver } from '@hookform/resolvers/zod'
import { HostFormSchema, hostFormDefaultValues, mapHostTransportSettingsForApi, parseNoisePacketInput } from '../src/features/hosts/forms/host-form.ts'
import { subscriptionSchema, withCustomVariableDefaults, normalizeCustomVariablesForPayload } from '../src/features/subscriptions/components/subscription-settings-schema.ts'

const host = { ...hostFormDefaultValues, remark: 'Test', address: ['example.invalid'], inbound_tag: 'test' }

test('subscription resolver applies defaults before submission without mutating input', async () => {
  const input = { rules: [], custom_variables: [{ key: 'CUSTOM_HOST' }, { value: 'draft' }] }
  const original = structuredClone(input)
  const result = await zodResolver(subscriptionSchema)(input, undefined, { fields: {}, shouldUseNativeValidation: false })
  assert.deepEqual(result.errors, {})
  assert.deepEqual(result.values.custom_variables, [
    { key: 'CUSTOM_HOST', value: '' },
    { key: '', value: 'draft' },
  ])
  assert.deepEqual(input, original)
  assert.deepEqual(subscriptionSchema.parse({ rules: [] }).custom_variables, [])
})

test('watched custom variables keep incomplete rows and whitespace until submission', () => {
  const input = [{ key: 'CUSTOM_HOST', value: '  example.invalid  ' }, {}, { value: 'draft' }]
  const display = withCustomVariableDefaults(input)
  assert.deepEqual(display, [
    { key: 'CUSTOM_HOST', value: '  example.invalid  ' },
    { key: '', value: '' },
    { key: '', value: 'draft' },
  ])
  assert.deepEqual(withCustomVariableDefaults(undefined), [])
  assert.deepEqual(input[1], {})
  assert.deepEqual(normalizeCustomVariablesForPayload(display), [{ key: 'CUSTOM_HOST', value: 'example.invalid' }])
})

test('subscription validation still rejects duplicate and reserved variable keys', () => {
  for (const keys of [['CUSTOM_HOST', 'CUSTOM_HOST'], ['USERNAME']]) {
    const result = subscriptionSchema.safeParse({ rules: [], custom_variables: keys.map(key => ({ key, value: '' })) })
    assert.equal(result.success, false)
    assert.ok(result.error.issues.some(issue => issue.path[0] === 'custom_variables'))
  }
})

test('host uplink chunk sizes preserve single values, ranges and 16 digit values', () => {
  for (const size of ['100', '100-200', '9999999999999999', '']) {
    const parsed = HostFormSchema.parse({ ...host, transport_settings: { xhttp_settings: { uplink_chunk_size: size } } })
    assert.equal(parsed.transport_settings.xhttp_settings.uplink_chunk_size, size)
    assert.equal(mapHostTransportSettingsForApi(parsed.transport_settings).xhttp_settings.uplink_chunk_size, size)
  }
})

test('host uplink validation rejects malformed ranges and overlong values', () => {
  for (const size of ['100-', 'a', '1-2-3', '10000000000000000', '-1']) {
    assert.equal(HostFormSchema.safeParse({ ...host, transport_settings: { xhttp_settings: { uplink_chunk_size: size } } }).success, false)
  }
})

test('host submit uses API XMux aliases and preserves zero keepalive', () => {
  const settings = {
    xhttp_settings: {
      uplink_chunk_size: '100-200',
      no_grpc_header: false,
      xmux: {
        max_concurrency: '1-4',
        max_connections: '2',
        c_max_reuse_times: '3',
        h_max_reusable_secs: '4-8',
        h_max_request_times: '5',
        h_keep_alive_period: 0,
      },
    },
    grpc_settings: { idle_timeout: 0 },
  }
  const original = structuredClone(settings)
  const payload = mapHostTransportSettingsForApi(settings)
  assert.deepEqual(payload.xhttp_settings.xmux, {
    maxConcurrency: '1-4',
    maxConnections: '2',
    cMaxReuseTimes: '3',
    hMaxReusableSecs: '4-8',
    hMaxRequestTimes: '5',
    hKeepAlivePeriod: 0,
  })
  assert.equal(payload.xhttp_settings.uplink_chunk_size, '100-200')
  assert.equal(payload.xhttp_settings.no_grpc_header, false)
  assert.deepEqual(payload.grpc_settings, { idle_timeout: 0 })
  assert.deepEqual(settings, original)
})

test('hosts without XHTTP or XMux do not gain those settings', () => {
  assert.equal(mapHostTransportSettingsForApi(undefined), undefined)
  assert.deepEqual(mapHostTransportSettingsForApi({ grpc_settings: { idle_timeout: 5 } }), { grpc_settings: { idle_timeout: 5 }, xhttp_settings: undefined })
  assert.equal(mapHostTransportSettingsForApi({ xhttp_settings: {} }).xhttp_settings.xmux, undefined)
})

test('API noise packet arrays, numeric zero delays, nulls and omitted fields survive validation', () => {
  for (const noise of [{ type: 'array', packet: [0, 1, 255], delay: 0 }, { type: 'str', packet: 'hello', delay: '10-20' }, { type: 'rand', packet: null, delay: null }, { type: 'rand' }]) {
    const parsed = HostFormSchema.parse({ ...host, noise_settings: { xray: [noise] } })
    assert.deepEqual(parsed.noise_settings.xray[0], { ...noise, apply_to: 'ip' })
  }
})

test('array noise editing parses integer arrays while string noise remains literal', () => {
  assert.deepEqual(parseNoisePacketInput('[0, 1, 255]', 'array'), [0, 1, 255])
  assert.equal(parseNoisePacketInput('[0, 1]', 'str'), '[0, 1]')
  for (const text of ['[1,', '[1.5]', '["1"]', '', 'hello']) {
    assert.equal(parseNoisePacketInput(text, 'array'), text)
  }
})
