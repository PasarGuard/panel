import type { Issue, JsonObject, JsonValue, Profile } from '@pasarguard/xray-config-kit'

type GeodataPreset = {
  owner: string
  countryCode: string
  geoip: string
  geosite: string
}

export const geodataPresetGroups = {
  iran: [
    {
      owner: 'Chocolate4U',
      countryCode: 'ir',
      geoip: 'https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geoip.dat',
      geosite: 'https://github.com/Chocolate4U/Iran-v2ray-rules/releases/latest/download/geosite.dat',
    },
  ],
  russia: [
    {
      owner: 'runetfreedom',
      countryCode: 'ru',
      geoip: 'https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/geoip.dat',
      geosite: 'https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/geosite.dat',
    },
  ],
  china: [
    {
      owner: 'Loyalsoldier',
      countryCode: 'cn',
      geoip: 'https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat',
      geosite: 'https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat',
    },
  ],
} satisfies Record<string, GeodataPreset[]>

export function addGeodataPresetAssets(assets: readonly JsonValue[], preset: GeodataPreset): JsonValue[] {
  const existingFiles = new Set(assets.map(asset => geodataObject(asset)?.file))
  const regionalAssets = [
    { file: `geoip-${preset.countryCode}.dat`, url: preset.geoip },
    { file: `geosite-${preset.countryCode}.dat`, url: preset.geosite },
  ]
  return [...assets, ...regionalAssets.filter(asset => !existingFiles.has(asset.file))]
}

const cronFields = [
  { min: 0, max: 59 },
  { min: 0, max: 23 },
  { min: 1, max: 31 },
  { min: 1, max: 12, names: 'jan feb mar apr may jun jul aug sep oct nov dec'.split(' ') },
  { min: 0, max: 6, names: 'sun mon tue wed thu fri sat'.split(' ') },
]

function isCronSchedule(value: string): boolean {
  const schedule = value.replace(/^(?:CRON_TZ|TZ)=\S+ +/, '').trim()
  // Xray's standard parser also accepts named schedules and Go durations.
  if (/^@(?:yearly|annually|monthly|weekly|daily|midnight|hourly)$/.test(schedule)) return true
  if (/^@every (?:[+-]?0|[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:ns|us|µs|μs|ms|s|m|h))+)$/.test(schedule)) return true

  const fields = schedule.toLowerCase().split(/\s+/)
  return (
    fields.length === cronFields.length &&
    cronFields.every(({ min, max, names }, index) => {
      const parseValue = (part: string) => (/^\+?\d+$/.test(part) ? Number(part) : (names?.indexOf(part) ?? -1) + min)
      return fields[index].split(',').every(part => {
        const match = /^(?:[*?]|(\+?\w+)(?:-(\+?\w+))?)(?:\/(\+?\d+))?$/.exec(part)
        if (!match) return false
        const [, start, end, step] = match
        const first = start === undefined ? min : parseValue(start)
        const last = end === undefined ? first : parseValue(end)
        return first >= min && last <= max && first <= last && (step === undefined || Number(step) > 0)
      })
    })
  )
}

export function geodataObject(value: unknown): JsonObject | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as JsonObject) : undefined
}

export function setProfileGeodata(profile: Profile, geodata?: JsonObject): Profile {
  const topLevel = { ...profile.raw?.topLevel }
  // The compiler can merge the imported source back in, including removed keys.
  const source = geodataObject(profile.raw?.source)
  const nextSource = source ? { ...source } : undefined
  if (geodata === undefined) {
    delete topLevel.geodata
    if (nextSource) delete nextSource.geodata
  } else {
    topLevel.geodata = geodata
    if (nextSource) nextSource.geodata = geodata
  }
  return { ...profile, raw: { ...profile.raw, topLevel, ...(nextSource && { source: nextSource }) } }
}

function isHttpsUrl(value: JsonValue | undefined): boolean {
  if (typeof value !== 'string' || !/^https:\/\/[^/\\?#\s]/i.test(value)) return false
  return URL.canParse(value)
}

function isResourcePath(value: JsonValue | undefined): boolean {
  return typeof value === 'string' && value.trim() !== '' && !/^[a-z]:|[\\\0]/i.test(value) && value.split('/').every(part => part !== '' && part !== '.' && part !== '..')
}

export function validateXrayGeodata(value: unknown): Issue[] {
  if (value == null) return []
  const issues: Issue[] = []
  const add = (path: string, message: string) => {
    issues.push({ code: 'invalid-geodata', path: `/geodata${path}`, message, severity: 'error', category: 'schema' })
  }
  const config = geodataObject(value)
  if (!config) {
    add('', 'Geodata must be an object.')
    return issues
  }
  if (config.cron != null && (typeof config.cron !== 'string' || !isCronSchedule(config.cron))) {
    add('/cron', 'Enter a valid Xray cron schedule.')
  }
  if (config.outbound != null && typeof config.outbound !== 'string') {
    add('/outbound', 'The download outbound tag must be a string.')
  }
  if (config.assets != null) {
    if (Array.isArray(config.assets)) {
      config.assets.forEach((value, index) => {
        const asset = geodataObject(value)
        if (!isHttpsUrl(asset?.url)) add(`/assets/${index}/url`, 'Enter an HTTPS download URL.')
        if (!isResourcePath(asset?.file)) add(`/assets/${index}/file`, 'Enter a file path inside the Xray resource directory.')
      })
    } else {
      add('/assets', 'Geodata assets must be a list.')
    }
  }
  return issues
}
