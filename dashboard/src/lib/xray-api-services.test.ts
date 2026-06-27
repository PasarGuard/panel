import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  CANONICAL_API_SERVICES,
  findUnknownApiServices,
  getSelectedOptional,
  OPTIONAL_API_SERVICES,
  REQUIRED_API_SERVICES,
  setOptionalService,
} from './xray-api-services.ts'

test('getSelectedOptional: no api yields empty', () => {
  assert.deepEqual(getSelectedOptional({}), [])
})

test('getSelectedOptional: reads optional services case-insensitively', () => {
  assert.deepEqual(getSelectedOptional({ api: { services: ['routingservice'] } }), ['RoutingService'])
})

test('getSelectedOptional: ignores required and unknown services', () => {
  assert.deepEqual(getSelectedOptional({ api: { services: ['HandlerService', 'Foo'] } }), [])
})

test('getSelectedOptional: non-object input is safe', () => {
  assert.deepEqual(getSelectedOptional(null), [])
})

test('findUnknownApiServices: flags unrecognized names, preserving order', () => {
  assert.deepEqual(
    findUnknownApiServices({ api: { services: ['RoutingService', 'Foo', 'RoutigService'] } }),
    ['Foo', 'RoutigService'],
  )
})

test('findUnknownApiServices: known names (any case) are not flagged', () => {
  assert.deepEqual(findUnknownApiServices({ api: { services: ['routingservice', 'StatsService'] } }), [])
})

test('setOptionalService: enabling creates api.services', () => {
  assert.deepEqual(setOptionalService({}, 'RoutingService', true), { api: { services: ['RoutingService'] } })
})

test('setOptionalService: enabling dedupes case-insensitively to canonical', () => {
  assert.deepEqual(
    setOptionalService({ api: { services: ['routingservice'] } }, 'RoutingService', true),
    { api: { services: ['RoutingService'] } },
  )
})

test('setOptionalService: disabling removes the service and drops an empty api', () => {
  assert.deepEqual(setOptionalService({ api: { services: ['RoutingService'] } }, 'RoutingService', false), {})
})

test('setOptionalService: disabling preserves other api keys', () => {
  assert.deepEqual(
    setOptionalService({ api: { services: ['RoutingService'], tag: 'API' } }, 'RoutingService', false),
    { api: { tag: 'API' } },
  )
})

test('setOptionalService: preserves other config keys and untouched (unknown) services', () => {
  assert.deepEqual(
    setOptionalService({ inbounds: [], api: { services: ['Foo'] } }, 'RoutingService', true),
    { inbounds: [], api: { services: ['Foo', 'RoutingService'] } },
  )
})

test('setOptionalService: unknown service name is a no-op', () => {
  assert.deepEqual(setOptionalService({ api: { services: [] } }, 'Nope', true), { api: { services: [] } })
})

test('allowlist constants are exactly the expected canonical names (drift guard)', () => {
  assert.deepEqual([...REQUIRED_API_SERVICES], ['HandlerService', 'LoggerService', 'StatsService'])
  assert.deepEqual([...OPTIONAL_API_SERVICES], ['RoutingService', 'ObservatoryService', 'ReflectionService'])
})

test('CANONICAL_API_SERVICES maps exactly REQUIRED ∪ OPTIONAL (both directions)', () => {
  const all = [...REQUIRED_API_SERVICES, ...OPTIONAL_API_SERVICES]
  for (const name of all) {
    assert.equal(CANONICAL_API_SERVICES[name.toLowerCase()], name)
  }
  assert.deepEqual(
    Object.keys(CANONICAL_API_SERVICES).sort(),
    all.map(n => n.toLowerCase()).sort(),
  )
})

test('getSelectedOptional: trims and dedupes whitespace/case variants', () => {
  assert.deepEqual(getSelectedOptional({ api: { services: ['  routingservice ', 'RoutingService'] } }), ['RoutingService'])
})
