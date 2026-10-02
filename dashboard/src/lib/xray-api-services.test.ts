import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  CANONICAL_API_SERVICES,
  findUnknownApiServices,
  getSelectedOptional,
  OPTIONAL_API_SERVICES,
  REQUIRED_API_SERVICES,
  setOptionalService,
  setRawOptionalService,
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

// Required services are node-injected; the panel must never write (or strip) them.
test('setOptionalService: enabling a required service is a no-op', () => {
  const config = { api: { services: ['RoutingService'] } }
  assert.equal(setOptionalService(config, 'HandlerService', true), config)
})

test('setOptionalService: disabling a required service is a no-op', () => {
  const config = { api: { services: ['StatsService'] } }
  assert.equal(setOptionalService(config, 'StatsService', false), config)
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

// Regression: the kit re-emits `api` from `raw.source`, so a removal expressed only
// on `raw.topLevel` is undone (Save never enables). setRawOptionalService must edit both.
test('setRawOptionalService: disabling the last service clears api from BOTH source and topLevel', () => {
  const raw = {
    source: { api: { services: ['RoutingService'] }, log: { loglevel: 'warning' } },
    topLevel: { api: { services: ['RoutingService'] } },
  }
  assert.deepEqual(setRawOptionalService(raw, 'RoutingService', false), {
    source: { log: { loglevel: 'warning' } },
    topLevel: {},
  })
})

test('setRawOptionalService: enabling adds the service to BOTH source and topLevel', () => {
  assert.deepEqual(setRawOptionalService({ source: { log: {} }, topLevel: {} }, 'RoutingService', true), {
    source: { log: {}, api: { services: ['RoutingService'] } },
    topLevel: { api: { services: ['RoutingService'] } },
  })
})

test('setRawOptionalService: preserves other raw keys and only touches api', () => {
  const raw = { extra: 1, source: { api: { services: ['RoutingService', 'ObservatoryService'] }, routing: { rules: [] } }, topLevel: { api: { services: ['RoutingService', 'ObservatoryService'] }, policy: {} } }
  assert.deepEqual(setRawOptionalService(raw, 'RoutingService', false), {
    extra: 1,
    source: { api: { services: ['ObservatoryService'] }, routing: { rules: [] } },
    topLevel: { api: { services: ['ObservatoryService'] }, policy: {} },
  })
})

test('setRawOptionalService: missing source updates only topLevel; non-object raw is safe', () => {
  assert.deepEqual(setRawOptionalService({ topLevel: {} }, 'RoutingService', true), { topLevel: { api: { services: ['RoutingService'] } } })
  assert.deepEqual(setRawOptionalService(undefined, 'RoutingService', true), { topLevel: { api: { services: ['RoutingService'] } } })
})
