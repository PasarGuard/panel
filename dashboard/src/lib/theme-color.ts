export type Hsl = { h: number; s: number; l: number }

export type ThemeDensity = 'compact' | 'comfortable' | 'spacious'
export type ThemeSurface = 'flat' | 'subtle' | 'elevated'
export type ThemeNeutral = 'default' | 'cool' | 'warm' | 'true'
export type ThemeBaseColor = 'default' | 'zinc' | 'slate' | 'stone' | 'gray' | 'mauve' | 'olive' | 'mist'
export type ThemeStyleName = 'vega' | 'nova' | 'maia' | 'lyra'

export type ThemeCustomization = {
  density: ThemeDensity
  surface: ThemeSurface
  neutral: ThemeNeutral
  baseColor: ThemeBaseColor
  style: ThemeStyleName
}

export const DEFAULT_THEME_CUSTOMIZATION: ThemeCustomization = {
  density: 'comfortable',
  surface: 'subtle',
  neutral: 'default',
  baseColor: 'default',
  style: 'vega',
}

const BACKGROUND_TOKENS = new Set([
  '--background',
  '--card',
  '--muted',
  '--secondary',
  '--accent',
  '--popover',
  '--input',
  '--sidebar-background',
  '--scrollbar-track',
  '--background-custom',
])

const NEUTRAL_HUES: Record<Exclude<ThemeNeutral, 'default'>, number> = {
  cool: 220,
  warm: 32,
  true: 0,
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export function round(value: number, digits = 1) {
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

export function parseHsl(value: string): Hsl | null {
  const match = value.trim().match(/^(-?[\d.]+)\s+([\d.]+)%\s+([\d.]+)%/)
  if (!match) return null
  return { h: Number(match[1]), s: Number(match[2]), l: Number(match[3]) }
}

export function formatHsl({ h, s, l }: Hsl): string {
  return `${round(h, 1)} ${round(s, 1)}% ${round(l, 1)}%`
}

function normalizeHex(input: string): string | null {
  let value = input.trim()
  if (!value.startsWith('#')) value = `#${value}`
  if (/^#[0-9a-fA-F]{3}$/.test(value)) {
    value = `#${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`
  }
  if (!/^#[0-9a-fA-F]{6}$/.test(value)) return null
  return value.toLowerCase()
}

export function hslToHex({ h, s, l }: Hsl): string {
  const sat = s / 100
  const light = l / 100
  const a = sat * Math.min(light, 1 - light)
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const color = light - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
    return Math.round(255 * color)
      .toString(16)
      .padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

export function hslCssToHex(value: string): string | null {
  if (value.startsWith('#')) return normalizeHex(value)
  const hsl = parseHsl(value)
  return hsl ? hslToHex(hsl) : null
}

function resolveVars(vars: Record<string, string>) {
  const resolved = { ...vars }
  for (let i = 0; i < 3; i++) {
    for (const [key, value] of Object.entries(resolved)) {
      const match = value.trim().match(/^var\((--[\w-]+)\)$/)
      if (match && resolved[match[1]]) {
        resolved[key] = resolved[match[1]]
      }
    }
  }
  return resolved
}

function applyNeutralTint(vars: Record<string, string>, neutral: ThemeNeutral) {
  if (neutral === 'default') return vars
  const hue = NEUTRAL_HUES[neutral]
  const next = { ...vars }
  for (const [key, value] of Object.entries(next)) {
    const hsl = parseHsl(value)
    if (!hsl) continue
    if (!BACKGROUND_TOKENS.has(key) && key !== '--border' && key !== '--sidebar-border' && key !== '--scrollbar-thumb') continue
    next[key] = formatHsl({
      h: hue,
      s: neutral === 'true' ? Math.min(hsl.s, 4) : clamp(Math.max(hsl.s, 4), 4, 12),
      l: hsl.l,
    })
  }
  return next
}

export function applyThemeCustomization(baseVars: Record<string, string>, customization: ThemeCustomization): Record<string, string> {
  return applyNeutralTint(resolveVars({ ...baseVars }), customization.neutral)
}

export function resolveTokenHex(vars: Record<string, string>, cssVar: string): string {
  const resolved = resolveVars(vars)
  return hslCssToHex(resolved[cssVar] ?? '') ?? '#888888'
}

export function parseThemeCustomization(raw: string | null): ThemeCustomization {
  if (!raw) return { ...DEFAULT_THEME_CUSTOMIZATION }
  try {
    const parsed = JSON.parse(raw) as Partial<ThemeCustomization>
    const baseColors: ThemeBaseColor[] = ['default', 'zinc', 'slate', 'stone', 'gray', 'mauve', 'olive', 'mist']
    const styles: ThemeStyleName[] = ['vega', 'nova', 'maia', 'lyra']
    return {
      density: parsed.density === 'compact' || parsed.density === 'spacious' ? parsed.density : 'comfortable',
      surface: parsed.surface === 'flat' || parsed.surface === 'elevated' ? parsed.surface : 'subtle',
      neutral: parsed.neutral === 'cool' || parsed.neutral === 'warm' || parsed.neutral === 'true' ? parsed.neutral : 'default',
      baseColor: baseColors.includes(parsed.baseColor as ThemeBaseColor) ? (parsed.baseColor as ThemeBaseColor) : 'default',
      style: styles.includes(parsed.style as ThemeStyleName) ? (parsed.style as ThemeStyleName) : 'vega',
    }
  } catch {
    return { ...DEFAULT_THEME_CUSTOMIZATION }
  }
}
