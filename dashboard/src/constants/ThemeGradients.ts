import type { ColorTheme } from '@/components/common/theme-provider'

export type GradientVariant = 'ad' | 'banner'

interface GradientConfig {
  light: string
  dark: string
}

const adGradients: Record<ColorTheme, GradientConfig> = {
  default: {
    light: 'bg-gradient-to-r from-blue-100/90 via-indigo-100/90 to-blue-100/90',
    dark: 'bg-gradient-to-r from-blue-950/50 via-indigo-950/50 to-blue-950/50',
  },
  red: {
    light: 'bg-gradient-to-r from-red-100/90 via-rose-100/90 to-red-100/90',
    dark: 'bg-gradient-to-r from-red-950/50 via-rose-950/50 to-red-950/50',
  },
  rose: {
    light: 'bg-gradient-to-r from-rose-100/90 via-pink-100/90 to-rose-100/90',
    dark: 'bg-gradient-to-r from-rose-950/50 via-pink-950/50 to-rose-950/50',
  },
  orange: {
    light: 'bg-gradient-to-r from-orange-100/90 via-amber-100/90 to-orange-100/90',
    dark: 'bg-gradient-to-r from-orange-950/50 via-amber-950/50 to-orange-950/50',
  },
  green: {
    light: 'bg-gradient-to-r from-green-100/90 via-emerald-100/90 to-green-100/90',
    dark: 'bg-gradient-to-r from-green-950/50 via-emerald-950/50 to-green-950/50',
  },
  blue: {
    light: 'bg-gradient-to-r from-blue-100/90 via-cyan-100/90 to-blue-100/90',
    dark: 'bg-gradient-to-r from-blue-950/50 via-cyan-950/50 to-blue-950/50',
  },
  yellow: {
    light: 'bg-gradient-to-r from-yellow-100/90 via-amber-100/90 to-yellow-100/90',
    dark: 'bg-gradient-to-r from-yellow-950/50 via-amber-950/50 to-yellow-950/50',
  },
  violet: {
    light: 'bg-gradient-to-r from-violet-100/90 via-purple-100/90 to-violet-100/90',
    dark: 'bg-gradient-to-r from-violet-950/50 via-purple-950/50 to-violet-950/50',
  },
}

const bannerGradients: Record<ColorTheme, GradientConfig> = {
  default: {
    light: 'bg-gradient-to-r from-blue-50/95 via-indigo-50/95 to-blue-50/95 border-blue-500/30',
    dark: 'bg-gradient-to-r from-blue-950/60 via-indigo-950/60 to-blue-950/60 border-blue-400/30',
  },
  red: {
    light: 'bg-gradient-to-r from-red-50/95 via-rose-50/95 to-red-50/95 border-red-500/30',
    dark: 'bg-gradient-to-r from-red-950/60 via-rose-950/60 to-red-950/60 border-red-400/30',
  },
  rose: {
    light: 'bg-gradient-to-r from-rose-50/95 via-pink-50/95 to-rose-50/95 border-rose-500/30',
    dark: 'bg-gradient-to-r from-rose-950/60 via-pink-950/60 to-rose-950/60 border-rose-400/30',
  },
  orange: {
    light: 'bg-gradient-to-r from-orange-50/95 via-amber-50/95 to-orange-50/95 border-orange-500/30',
    dark: 'bg-gradient-to-r from-orange-950/60 via-amber-950/60 to-orange-950/60 border-orange-400/30',
  },
  green: {
    light: 'bg-gradient-to-r from-green-50/95 via-emerald-50/95 to-green-50/95 border-green-500/30',
    dark: 'bg-gradient-to-r from-green-950/60 via-emerald-950/60 to-green-950/60 border-green-400/30',
  },
  blue: {
    light: 'bg-gradient-to-r from-blue-50/95 via-cyan-50/95 to-blue-50/95 border-blue-500/30',
    dark: 'bg-gradient-to-r from-blue-950/60 via-cyan-950/60 to-blue-950/60 border-blue-400/30',
  },
  yellow: {
    light: 'bg-gradient-to-r from-yellow-50/95 via-amber-50/95 to-yellow-50/95 border-yellow-500/30',
    dark: 'bg-gradient-to-r from-yellow-950/60 via-amber-950/60 to-yellow-950/60 border-yellow-400/30',
  },
  violet: {
    light: 'bg-gradient-to-r from-violet-50/95 via-purple-50/95 to-violet-50/95 border-violet-500/30',
    dark: 'bg-gradient-to-r from-violet-950/60 via-purple-950/60 to-violet-950/60 border-violet-400/30',
  },
}

const indicatorColors: Record<ColorTheme, GradientConfig> = {
  default: { light: 'bg-blue-500', dark: 'bg-blue-400' },
  red: { light: 'bg-red-500', dark: 'bg-red-400' },
  rose: { light: 'bg-rose-500', dark: 'bg-rose-400' },
  orange: { light: 'bg-orange-500', dark: 'bg-orange-400' },
  green: { light: 'bg-green-500', dark: 'bg-green-400' },
  blue: { light: 'bg-blue-500', dark: 'bg-blue-400' },
  yellow: { light: 'bg-yellow-500', dark: 'bg-yellow-400' },
  violet: { light: 'bg-violet-500', dark: 'bg-violet-400' },
}

/**
 * Get gradient classes based on color theme and variant
 * @param colorTheme - The color theme to use
 * @param isDark - Whether dark mode is active
 * @param variant - The gradient variant ('ad' for topbar ads, 'banner' for version banners)
 * @returns Tailwind CSS classes for the gradient
 */
export function getGradientByColorTheme(
  colorTheme: ColorTheme,
  isDark: boolean,
  variant: GradientVariant = 'ad'
): string {
  const gradients = variant === 'ad' ? adGradients : bannerGradients
  return isDark ? gradients[colorTheme].dark : gradients[colorTheme].light
}

/**
 * Get indicator color class based on color theme
 * @param colorTheme - The color theme to use
 * @param isDark - Whether dark mode is active
 * @returns Tailwind CSS class for the indicator color
 */
export function getIndicatorColorByTheme(colorTheme: ColorTheme, isDark: boolean): string {
  return isDark ? indicatorColors[colorTheme].dark : indicatorColors[colorTheme].light
}

