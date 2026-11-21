export interface CountryOption {
  code: string
  name: string
}

const A_CODE = 65
const REGIONAL_INDICATOR_A = 0x1f1e6
const COUNTRY_CODE_PATTERN = /^[A-Za-z]{2}$/
// ISO 3166-1 user-assigned codes (AA, QM-QZ, XA-XZ, ZZ) are CLDR pseudo-regions; XK (Kosovo) is the common exception
const USER_ASSIGNED_PATTERN = /^(AA|Q[M-Z]|X[A-Z]|ZZ)$/

// Groupings and exceptionally reserved codes that CLDR names but are not countries
const NON_COUNTRY_CODES = new Set(['EU', 'EZ', 'UN', 'AC', 'CP', 'DG', 'EA', 'IC', 'TA'])

const isUserAssigned = (code: string) => code !== 'XK' && USER_ASSIGNED_PATTERN.test(code)

// Deprecated ISO/CLDR aliases that still have display names (DD=Germany, SU=Russia, UK=United Kingdom, ...).
// Listed explicitly because not every engine canonicalizes them (JavaScriptCore keeps und-UK as is).
const DEPRECATED_ALIASES = new Set(['AN', 'BU', 'CS', 'DD', 'DY', 'FQ', 'FX', 'HV', 'NH', 'NT', 'RH', 'SU', 'TP', 'UK', 'VD', 'YD', 'YU', 'ZR'])

const isCanonicalRegion = (code: string) => {
  if (DEPRECATED_ALIASES.has(code)) return false
  try {
    return Intl.getCanonicalLocales(`und-${code}`)[0] === `und-${code}`
  } catch {
    return false
  }
}

let cachedCodes: string[] | null = null
const displayNamesCache = new Map<string, Intl.DisplayNames | null>()

const getDisplayNames = (locale: string): Intl.DisplayNames | null => {
  if (displayNamesCache.has(locale)) return displayNamesCache.get(locale) ?? null
  let displayNames: Intl.DisplayNames | null = null
  try {
    displayNames = new Intl.DisplayNames([locale, 'en'], { type: 'region', fallback: 'none' })
  } catch {
    displayNames = null
  }
  displayNamesCache.set(locale, displayNames)
  return displayNames
}

export const normalizeCountryCode = (code: string | null | undefined): string | null => {
  const trimmed = code?.trim()
  if (!trimmed || !COUNTRY_CODE_PATTERN.test(trimmed)) return null
  return trimmed.toUpperCase()
}

/**
 * Two-letter region codes known to the runtime's Intl data (AA..ZZ probed at runtime),
 * so the list follows the platform instead of a hand-maintained table.
 */
export const getCountryCodes = (): string[] => {
  if (cachedCodes) return cachedCodes
  const displayNames = getDisplayNames('en')
  const codes: string[] = []
  if (displayNames) {
    for (let first = 0; first < 26; first++) {
      for (let second = 0; second < 26; second++) {
        const code = String.fromCharCode(A_CODE + first, A_CODE + second)
        if (isUserAssigned(code) || NON_COUNTRY_CODES.has(code) || !isCanonicalRegion(code)) continue
        try {
          if (displayNames.of(code)) codes.push(code)
        } catch {
          // Not a valid region subtag for this runtime
        }
      }
    }
  }
  cachedCodes = codes
  return codes
}

export const getCountryFlag = (code: string | null | undefined): string => {
  const normalized = normalizeCountryCode(code)
  if (!normalized) return ''
  return String.fromCodePoint(...Array.from(normalized, char => REGIONAL_INDICATOR_A + char.charCodeAt(0) - A_CODE))
}

let flagEmojiSupport: boolean | null = null

/**
 * Whether the platform draws flag emoji. Windows has no flag glyphs and shows regional
 * indicators as two plain letters, so callers show the country code instead.
 */
export const supportsFlagEmoji = (): boolean => {
  if (flagEmojiSupport !== null) return flagEmojiSupport
  flagEmojiSupport = false
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 16
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) return flagEmojiSupport
    context.textBaseline = 'top'
    context.font = '16px sans-serif'
    context.fillStyle = '#000'
    context.fillText(getCountryFlag('DE'), 0, 0)
    const pixels = context.getImageData(0, 0, 16, 16).data
    // Letters fall back to the black fill; a real flag has colored pixels
    for (let index = 0; index < pixels.length; index += 4) {
      if (pixels[index + 3] && (pixels[index] !== pixels[index + 1] || pixels[index + 1] !== pixels[index + 2])) {
        flagEmojiSupport = true
        break
      }
    }
  } catch {
    flagEmojiSupport = false
  }
  return flagEmojiSupport
}

export const getCountryName = (code: string | null | undefined, locale = 'en'): string => {
  const normalized = normalizeCountryCode(code)
  if (!normalized) return ''
  try {
    return getDisplayNames(locale)?.of(normalized) || getDisplayNames('en')?.of(normalized) || normalized
  } catch {
    return normalized
  }
}

export const getCountryOptions = (locale = 'en'): CountryOption[] => {
  const collator = new Intl.Collator([locale, 'en'])
  return getCountryCodes()
    .map(code => ({ code, name: getCountryName(code, locale) }))
    .sort((a, b) => collator.compare(a.name, b.name))
}
