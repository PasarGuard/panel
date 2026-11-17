import { DEFAULT_XRAY_CORE_CONFIG } from '@/lib/default-xray-core-config'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { importRawToProfile, profileToPersistedConfig, validateProfileForPersist } from './xray-adapter'
import { addGeodataPresetAssets, geodataPresetGroups, setProfileGeodata, validateXrayGeodata } from './xray-geodata'

const geoip = { url: 'https://example.com/geoip-lite.dat.gz', file: 'geoip.dat' }
const geosite = { url: 'https://example.com/geosite.dat', file: 'geosite.dat' }
const original = { cron: '0 4 * * *', outbound: 'DIRECT', assets: [geoip, geosite] }

test('regional presets use the installer sources and distinct target filenames', () => {
  const sources = {
    iran: { repository: 'Chocolate4U/Iran-v2ray-rules', code: 'ir' },
    russia: { repository: 'runetfreedom/russia-v2ray-rules-dat', code: 'ru' },
    china: { repository: 'Loyalsoldier/v2ray-rules-dat', code: 'cn' },
  } as const
  const regions = ['iran', 'russia', 'china'] as const
  assert.deepEqual(Object.keys(geodataPresetGroups), [...regions])
  for (const region of regions) {
    const [preset] = geodataPresetGroups[region]
    assert.equal(geodataPresetGroups[region].length, 1)
    const { repository, code } = sources[region]
    const assets = addGeodataPresetAssets([], preset)
    const baseUrl = `https://github.com/${repository}/releases/latest/download`
    assert.deepEqual(assets, [
      { file: `geoip-${code}.dat`, url: `${baseUrl}/geoip.dat` },
      { file: `geosite-${code}.dat`, url: `${baseUrl}/geosite.dat` },
    ])
    assert.deepEqual(validateXrayGeodata({ assets }), [])
  }
})

test('all preset labels match the GitHub owner for both asset URLs', () => {
  for (const presets of Object.values(geodataPresetGroups)) {
    for (const preset of presets) {
      assert.equal(new URL(preset.geoip).pathname.split('/')[1], preset.owner)
      assert.equal(new URL(preset.geosite).pathname.split('/')[1], preset.owner)
      assert.deepEqual(validateXrayGeodata({ assets: addGeodataPresetAssets([], preset) }), [])
    }
  }
})

test('multiple regions save together and preserve existing standard and custom assets', () => {
  const custom = { file: 'custom.dat', url: 'https://example.com/custom.dat' }
  const previous = addGeodataPresetAssets([geoip, geosite, custom], geodataPresetGroups.iran[0])
  const assets = addGeodataPresetAssets(previous, geodataPresetGroups.china[0])
  const config = { cron: original.cron, assets }
  const { profile } = importRawToProfile(DEFAULT_XRAY_CORE_CONFIG)
  const result = validateProfileForPersist(setProfileGeodata(profile, config))

  assert.deepEqual(assets, [...previous, ...addGeodataPresetAssets([], geodataPresetGroups.china[0])])
  assert.equal(result.ok, true)
  if (result.ok) assert.deepEqual(result.config.geodata, config)
})

test('adding the same preset again fills missing targets without overwriting files', () => {
  const preset = geodataPresetGroups.russia[0]
  const custom = { file: 'geoip-ru.dat', url: 'https://example.com/custom.dat' }
  const assets = addGeodataPresetAssets([custom], preset)
  assert.deepEqual(assets, [custom, { file: 'geosite-ru.dat', url: preset.geosite }])
  assert.deepEqual(addGeodataPresetAssets(assets, preset), assets)
})

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

test('cron checks the time-zone prefix before validating the schedule', () => {
  for (const prefix of ['CRON_TZ=UTC', 'TZ=Asia/Tehran', 'CRON_TZ=Local', 'CRON_TZ=US/Eastern', 'TZ=Etc/GMT+3']) {
    assert.deepEqual(validateXrayGeodata({ cron: `${prefix} 0 4 * * *` }), [], prefix)
  }
  for (const prefix of ['CRON_TZ=Not/AZone', 'TZ=Not/AZone', 'CRON_TZ=+03:30', 'TZ=asia/tehran']) {
    const [issue] = validateXrayGeodata({ cron: `${prefix} 0 4 * * *` })
    assert.equal(issue?.path, '/geodata/cron', prefix)
    assert.match(issue.message, /time zone/, prefix)
  }
  assert.match(validateXrayGeodata({ cron: 'CRON_TZ=UTC 60 4 * * *' })[0]?.message ?? '', /schedule/)
})

test('persist validation rejects an imported cron with an unknown time zone', () => {
  const { profile } = importRawToProfile({ ...DEFAULT_XRAY_CORE_CONFIG, geodata: { cron: 'CRON_TZ=Not/AZone 0 4 * * *' } })
  const result = validateProfileForPersist(profile)
  assert.equal(result.ok, false)
  if (!result.ok) assert.ok(result.strictBlockers.some(issue => issue.path === '/geodata/cron' && issue.message.includes('time zone')))
})
