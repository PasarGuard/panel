import { DEFAULT_XRAY_CORE_CONFIG } from '@/lib/default-xray-core-config'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { importRawToProfile, profileToPersistedConfig, validateProfileForPersist } from './xray-adapter'
import { setProfileGeodata, validateXrayGeodata } from './xray-geodata'

const geoip = { url: 'https://example.com/geoip-lite.dat.gz', file: 'geoip.dat' }
const geosite = { url: 'https://example.com/geosite.dat', file: 'geosite.dat' }
const original = { cron: '0 4 * * *', outbound: 'DIRECT', assets: [geoip, geosite] }

test('geodata can be added and saved with the Xray core config', () => {
  const { profile } = importRawToProfile(DEFAULT_XRAY_CORE_CONFIG)
  assert.equal('geodata' in profileToPersistedConfig(profile), false)

  const result = validateProfileForPersist(setProfileGeodata(profile, original))
  assert.equal(result.ok, true)
  if (!result.ok) return
  assert.deepEqual(result.config.geodata, original)
  assert.deepEqual(importRawToProfile(result.config).profile.raw?.topLevel?.geodata, original)
})

test('editing imported geodata can remove the outbound and assets from the saved config', () => {
  const { profile } = importRawToProfile({ ...DEFAULT_XRAY_CORE_CONFIG, geodata: original })
  assert.deepEqual(profileToPersistedConfig(profile).geodata, original)

  const reloadOnly = { cron: '30 3 * * MON' }
  const result = validateProfileForPersist(setProfileGeodata(profile, reloadOnly))
  assert.equal(result.ok, true)
  if (result.ok) assert.deepEqual(result.config.geodata, reloadOnly)
})

test('disabling geodata removes it without dropping other imported sections', () => {
  const { profile } = importRawToProfile({ ...DEFAULT_XRAY_CORE_CONFIG, geodata: original })
  const { geodata, ...rest } = profileToPersistedConfig(profile)
  assert.deepEqual(geodata, original)
  assert.deepEqual(profileToPersistedConfig(setProfileGeodata(profile)), rest)
})

test('blocking validation covers geodata from the raw config', () => {
  const geodata = { cron: '0 4 *', assets: [{ url: 'http://example.com/geoip.dat', file: '../geoip.dat' }] }
  const { profile } = importRawToProfile({ ...DEFAULT_XRAY_CORE_CONFIG, geodata })
  const result = validateProfileForPersist(profile)
  assert.equal(result.ok, false)
  if (result.ok) return
  assert.deepEqual(
    result.strictBlockers.filter(issue => issue.code === 'invalid-geodata').map(issue => issue.path),
    ['/geodata/cron', '/geodata/assets/0/url', '/geodata/assets/0/file'],
  )
})

test('assets must use HTTPS and target a relative resource file', () => {
  assert.deepEqual(validateXrayGeodata({}), [])
  assert.deepEqual(validateXrayGeodata({ assets: [{ ...geoip, file: 'custom/geoip.dat' }] }), [])
  for (const file of ['', '.', '/geoip.dat', 'C:\\geoip.dat', 'custom/../../geoip.dat']) {
    assert.equal(validateXrayGeodata({ assets: [{ ...geoip, file }] })[0]?.path, '/geodata/assets/0/file')
  }
})

test('cron validates field ranges and preserves Xray schedule shortcuts', () => {
  for (const cron of ['0 4 * * *', '*/15 8-17 * JAN,MAR MON-FRI', 'CRON_TZ=UTC 0 4 * * *', '@daily', '@every 1h30m']) {
    assert.deepEqual(validateXrayGeodata({ cron }), [])
  }
  for (const cron of ['', '60 4 * * *', '0 4 * 13 *', '0 4 * * FRY', '*/0 4 * * *', '0 22-10 * * *']) {
    assert.equal(validateXrayGeodata({ cron })[0]?.path, '/geodata/cron')
  }
})
