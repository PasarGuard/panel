import type { ColorTheme } from '@/constants/color-themes'

export type GradientVariant = 'ad' | 'banner'

/**
 * Gradients follow the active primary token so custom colors stay in sync.
 */
export function getGradientByColorTheme(_colorTheme: ColorTheme, isDark: boolean, variant: GradientVariant = 'ad'): string {
  if (variant === 'banner') {
    return isDark ? 'bg-gradient-to-r from-primary/20 via-primary/10 to-primary/20 border-primary/30' : 'bg-gradient-to-r from-primary/10 via-primary/5 to-primary/10 border-primary/30'
  }

  return isDark ? 'bg-gradient-to-r from-primary/20 via-primary/10 to-primary/20' : 'bg-gradient-to-r from-primary/15 via-primary/10 to-primary/15'
}

export function getIndicatorColorByTheme(_colorTheme: ColorTheme, _isDark: boolean): string {
  return 'bg-primary'
}
