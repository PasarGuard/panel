export type BaseColor = 'default' | 'zinc' | 'slate' | 'stone' | 'gray' | 'mauve' | 'olive' | 'mist'
export type ColorTheme = 'default' | 'inverse' | 'red' | 'rose' | 'pink' | 'orange' | 'amber' | 'yellow' | 'green' | 'teal' | 'cyan' | 'blue' | 'indigo' | 'violet'
export type ThemeStyle = 'vega' | 'nova' | 'maia' | 'lyra'

export type ColorThemeConfig = {
  name: string
  light: Record<string, string>
  dark: Record<string, string>
}

const lightShared = {
  '--destructive': '0 72% 51%',
  '--destructive-foreground': '0 0% 98%',
  '--card-foreground': 'var(--foreground)',
  '--popover': 'var(--background)',
  '--popover-foreground': 'var(--foreground)',
}

const darkShared = {
  '--destructive': '0 72% 51%',
  '--destructive-foreground': '210 40% 98%',
  '--card-foreground': 'var(--foreground)',
  '--popover': 'var(--background)',
  '--popover-foreground': 'var(--foreground)',
}

function basePalette(name: string, hue: number, lightSat: number, darkSat: number, lightPrimary: string, lightPrimaryFg: string, darkPrimary: string, darkPrimaryFg: string): ColorThemeConfig {
  return {
    name,
    light: {
      ...lightShared,
      '--background': `${hue} ${lightSat}% 96%`,
      '--foreground': `${hue} ${Math.min(lightSat + 2, 10)}% 10%`,
      '--secondary': `${hue} ${lightSat}% 90%`,
      '--secondary-foreground': `${hue} ${Math.min(lightSat + 2, 10)}% 20%`,
      '--muted': `${hue} ${lightSat}% 90%`,
      '--muted-foreground': `${hue} ${lightSat}% 40%`,
      '--accent': `${hue} ${lightSat}% 90%`,
      '--accent-foreground': `${hue} ${Math.min(lightSat + 2, 10)}% 20%`,
      '--border': `${hue} ${lightSat}% 80%`,
      '--input': `${hue} ${lightSat + 1}% 91%`,
      '--card': `${hue} ${lightSat}% 98%`,
      '--primary': lightPrimary,
      '--primary-foreground': lightPrimaryFg,
      '--ring': lightPrimary,
      '--chart-1': lightPrimary,
      '--chart-2': `${hue} ${Math.max(lightSat, 8)}% 45%`,
      '--chart-3': `${hue} ${Math.max(lightSat, 8)}% 35%`,
      '--chart-4': `${hue} ${Math.max(lightSat, 6)}% 55%`,
      '--chart-5': `${hue} ${Math.max(lightSat, 4)}% 70%`,
      '--sidebar-background': `${hue} ${lightSat}% 92%`,
      '--sidebar-foreground': `${hue} ${Math.min(lightSat + 2, 10)}% 20%`,
      '--sidebar-primary': lightPrimary,
      '--sidebar-primary-foreground': lightPrimaryFg,
      '--sidebar-accent': `${hue} ${lightSat}% 86%`,
      '--sidebar-accent-foreground': `${hue} ${Math.min(lightSat + 2, 10)}% 10%`,
      '--sidebar-border': `${hue} ${lightSat}% 80%`,
      '--sidebar-ring': lightPrimary,
    },
    dark: {
      ...darkShared,
      '--background': `${hue} ${darkSat}% 11%`,
      '--foreground': `${hue} ${darkSat}% 98%`,
      '--secondary': `${hue} ${darkSat + 2}% 16%`,
      '--secondary-foreground': `${hue} ${darkSat}% 98%`,
      '--muted': `${hue} ${darkSat + 2}% 15%`,
      '--muted-foreground': `${hue} ${darkSat}% 64%`,
      '--accent': `${hue} ${darkSat + 2}% 16%`,
      '--accent-foreground': `${hue} ${darkSat}% 98%`,
      '--border': `${hue} ${darkSat}% 18%`,
      '--input': `${hue} ${darkSat}% 16.5%`,
      '--card': `${hue} ${darkSat}% 12.5%`,
      '--primary': darkPrimary,
      '--primary-foreground': darkPrimaryFg,
      '--ring': '215 16% 47%',
      '--chart-1': darkPrimary,
      '--chart-2': `${hue} ${Math.max(darkSat + 4, 8)}% 55%`,
      '--chart-3': `${hue} ${Math.max(darkSat + 4, 8)}% 45%`,
      '--chart-4': `${hue} ${Math.max(darkSat + 2, 6)}% 65%`,
      '--chart-5': `${hue} ${Math.max(darkSat, 4)}% 75%`,
      '--sidebar-background': `${hue} ${darkSat}% 11%`,
      '--sidebar-foreground': `${hue} ${darkSat}% 90%`,
      '--sidebar-primary': darkPrimary,
      '--sidebar-primary-foreground': darkPrimaryFg,
      '--sidebar-accent': `${hue} ${darkSat + 2}% 16%`,
      '--sidebar-accent-foreground': `${hue} ${darkSat}% 98%`,
      '--sidebar-border': `${hue} ${darkSat}% 20%`,
      '--sidebar-ring': '215 16% 47%',
    },
  }
}

function accentOverlay(name: string, lightPrimary: string, lightFg: string, darkPrimary: string, darkFg: string, lightCharts: string[], darkCharts: string[]): ColorThemeConfig {
  return {
    name,
    light: {
      '--primary': lightPrimary,
      '--primary-foreground': lightFg,
      '--ring': lightPrimary,
      '--chart-1': lightCharts[0],
      '--chart-2': lightCharts[1],
      '--chart-3': lightCharts[2],
      '--chart-4': lightCharts[3],
      '--chart-5': lightCharts[4],
      '--sidebar-primary': lightPrimary,
      '--sidebar-primary-foreground': lightFg,
      '--sidebar-ring': lightPrimary,
    },
    dark: {
      '--primary': darkPrimary,
      '--primary-foreground': darkFg,
      '--ring': darkPrimary,
      '--chart-1': darkCharts[0],
      '--chart-2': darkCharts[1],
      '--chart-3': darkCharts[2],
      '--chart-4': darkCharts[3],
      '--chart-5': darkCharts[4],
      '--sidebar-primary': darkPrimary,
      '--sidebar-primary-foreground': darkFg,
      '--sidebar-ring': darkPrimary,
    },
  }
}

export const baseColors: Record<BaseColor, ColorThemeConfig> = {
  default: basePalette('Neutral', 240, 5, 2, '216 46% 40%', '240 5% 98%', '216 46% 53%', '0 0% 5%'),
  zinc: basePalette('Zinc', 240, 6, 3, '240 6% 10%', '0 0% 98%', '0 0% 98%', '240 6% 10%'),
  slate: basePalette('Slate', 215, 14, 8, '222 47% 11%', '210 40% 98%', '210 40% 98%', '222 47% 11%'),
  stone: basePalette('Stone', 30, 6, 4, '24 10% 10%', '60 9% 98%', '24 6% 83%', '24 10% 10%'),
  gray: basePalette('Gray', 0, 0, 0, '0 0% 9%', '0 0% 98%', '0 0% 98%', '0 0% 9%'),
  mauve: basePalette('Mauve', 280, 8, 5, '280 8% 12%', '280 20% 98%', '280 6% 90%', '280 8% 12%'),
  olive: basePalette('Olive', 85, 8, 5, '85 12% 12%', '85 20% 97%', '85 8% 88%', '85 12% 12%'),
  mist: basePalette('Mist', 200, 10, 6, '200 18% 14%', '200 40% 98%', '200 12% 90%', '200 18% 14%'),
}

export const accentThemes: Record<ColorTheme, ColorThemeConfig> = {
  inverse: accentOverlay('Inverse', '0 0% 9%', '0 0% 98%', '0 0% 100%', '0 0% 9%', ['0 0% 9%', '0 0% 25%', '0 0% 40%', '0 0% 60%', '0 0% 80%'], ['0 0% 100%', '0 0% 80%', '0 0% 60%', '0 0% 40%', '0 0% 20%']),
  default: { name: 'Default', light: {}, dark: {} },
  red: accentOverlay('Red', '0 72.2% 50.6%', '0 86% 97%', '0 72.2% 50.6%', '0 86% 97%', ['0 72% 51%', '15 100% 50%', '30 100% 50%', '45 90% 50%', '0 70% 40%'], ['0 72% 51%', '15 100% 60%', '30 100% 60%', '45 90% 60%', '0 70% 55%']),
  rose: accentOverlay('Rose', '346.8 77.2% 49.8%', '356 100% 97%', '346.8 77.2% 49.8%', '356 100% 97%', ['347 77% 50%', '330 100% 50%', '315 90% 50%', '300 80% 50%', '347 70% 40%'], ['347 77% 50%', '330 100% 60%', '315 90% 60%', '300 80% 60%', '347 70% 55%']),
  pink: accentOverlay('Pink', '322.1 79.2% 52.4%', '327 73% 97%', '322.1 79.2% 56%', '327 73% 97%', ['322 79% 52%', '340 82% 52%', '350 80% 58%', '10 80% 55%', '322 70% 42%'], ['322 79% 56%', '340 82% 62%', '350 80% 66%', '10 80% 62%', '322 70% 55%']),
  orange: accentOverlay('Orange', '24.6 95% 53.1%', '60 9% 98%', '20.5 90.2% 48.2%', '60 9% 98%', ['25 95% 53%', '15 100% 50%', '35 100% 50%', '45 100% 50%', '20 90% 42%'], ['21 90% 48%', '15 100% 60%', '35 100% 60%', '45 100% 60%', '20 90% 55%']),
  amber: accentOverlay('Amber', '37.7 92.1% 50.2%', '26 83% 14%', '37.7 92.1% 50.2%', '26 83% 14%', ['38 92% 50%', '24 95% 53%', '15 90% 50%', '48 96% 53%', '38 80% 40%'], ['38 92% 50%', '24 95% 60%', '15 90% 58%', '48 96% 60%', '38 80% 55%']),
  yellow: accentOverlay('Yellow', '47.9 95.8% 53.1%', '26 83% 14%', '47.9 95.8% 53.1%', '26 83% 14%', ['48 96% 53%', '35 100% 50%', '25 100% 50%', '15 100% 50%', '48 80% 42%'], ['48 96% 53%', '35 100% 60%', '25 100% 60%', '15 100% 60%', '48 80% 55%']),
  green: accentOverlay('Green', '142.1 76.2% 36.3%', '356 100% 97%', '142.1 70.6% 45.3%', '145 80% 10%', ['142 76% 36%', '160 100% 40%', '180 80% 40%', '200 80% 45%', '142 60% 28%'], ['142 71% 45%', '160 100% 50%', '180 80% 50%', '200 80% 55%', '142 60% 40%']),
  teal: accentOverlay('Teal', '173.4 80.4% 36%', '166 76% 97%', '173.4 80.4% 40%', '166 76% 97%', ['173 80% 36%', '190 90% 40%', '200 90% 45%', '160 70% 40%', '173 70% 28%'], ['173 80% 40%', '190 90% 50%', '200 90% 55%', '160 70% 50%', '173 70% 45%']),
  cyan: accentOverlay('Cyan', '189 94% 43%', '185 80% 96%', '189 94% 48%', '185 80% 96%', ['189 94% 43%', '200 90% 48%', '220 80% 52%', '170 80% 40%', '189 80% 34%'], ['189 94% 48%', '200 90% 58%', '220 80% 62%', '170 80% 50%', '189 80% 45%']),
  blue: accentOverlay('Blue', '221.2 83.2% 53.3%', '210 40% 98%', '217.2 91.2% 59.8%', '222 47% 11%', ['221 83% 53%', '200 100% 50%', '180 90% 45%', '240 80% 55%', '221 70% 42%'], ['217 91% 60%', '200 100% 60%', '180 90% 55%', '240 80% 62%', '217 70% 50%']),
  indigo: accentOverlay('Indigo', '239 84% 57%', '226 100% 97%', '234 89% 64%', '226 100% 97%', ['239 84% 57%', '250 80% 55%', '260 70% 50%', '220 80% 55%', '239 70% 45%'], ['234 89% 64%', '250 80% 62%', '260 70% 58%', '220 80% 62%', '234 70% 52%']),
  violet: accentOverlay('Violet', '262.1 83.3% 57.8%', '210 20% 98%', '263.4 70% 50.4%', '210 20% 98%', ['262 83% 58%', '280 100% 50%', '300 90% 50%', '320 80% 50%', '262 70% 45%'], ['263 70% 50%', '280 100% 60%', '300 90% 60%', '320 80% 60%', '263 70% 55%']),
}

export const baseColorOrder: BaseColor[] = ['default', 'zinc', 'slate', 'stone', 'gray', 'mauve', 'olive', 'mist']
export const colorThemeOrder: ColorTheme[] = ['default', 'inverse', 'red', 'rose', 'pink', 'orange', 'amber', 'yellow', 'green', 'teal', 'cyan', 'blue', 'indigo', 'violet']

export const baseSwatches: Record<BaseColor, string> = {
  default: '#4f6d8c',
  zinc: '#71717a',
  slate: '#64748b',
  stone: '#78716c',
  gray: '#6b7280',
  mauve: '#8b7d9a',
  olive: '#7d8a6f',
  mist: '#6b8a9a',
}

export const themeStylePresets: Record<ThemeStyle, { density: 'compact' | 'comfortable' | 'spacious'; surface: 'flat' | 'subtle' | 'elevated'; radius: string }> = {
  vega: { density: 'comfortable', surface: 'subtle', radius: '0.5rem' },
  nova: { density: 'compact', surface: 'flat', radius: '0.3rem' },
  maia: { density: 'spacious', surface: 'elevated', radius: '0.75rem' },
  lyra: { density: 'compact', surface: 'flat', radius: '0' },
}

export const radiusPresets = [
  { value: '0', label: 'theme.radiusNone' },
  { value: '0.3rem', label: 'theme.radiusSmall' },
  { value: '0.5rem', label: 'theme.radiusMedium' },
  { value: '0.75rem', label: 'theme.radiusLarge' },
  { value: '1rem', label: 'theme.radiusXl' },
] as const

export function composeTheme(baseColor: BaseColor, colorTheme: ColorTheme, mode: 'light' | 'dark'): Record<string, string> {
  const base = baseColors[baseColor] ?? baseColors.default
  const accent = accentThemes[colorTheme] ?? accentThemes.default
  return {
    ...base[mode],
    ...accent[mode],
  }
}

export const colorThemes: Record<ColorTheme, ColorThemeConfig> = Object.fromEntries(
  colorThemeOrder.map(name => [
    name,
    {
      name: accentThemes[name].name,
      light: composeTheme('default', name, 'light'),
      dark: composeTheme('default', name, 'dark'),
    },
  ]),
) as Record<ColorTheme, ColorThemeConfig>

export const LEGACY_THEME_TO_BASE: Partial<Record<string, BaseColor>> = {
  zinc: 'zinc',
  slate: 'slate',
}

export const LEGACY_COLOR_THEME: Record<string, ColorTheme> = {
  white: 'inverse',
}
