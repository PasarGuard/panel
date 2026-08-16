import { accentThemes, baseColors } from '@/constants/color-themes'
import { useTheme } from '@/app/providers/theme-provider'
import { useTranslation } from 'react-i18next'

export function ThemePreview() {
  const { t } = useTranslation()
  const { colorTheme, customization, resolvedTheme, radius } = useTheme()
  const baseName = baseColors[customization.baseColor]?.name ?? customization.baseColor
  const accentName = accentThemes[colorTheme]?.name ?? colorTheme

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <p className="text-base font-semibold sm:text-lg">{t('theme.preview')}</p>
        <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.previewDescription')}</p>
      </div>
      <div className="border-border/70 bg-muted/30 space-y-3 rounded-lg border p-3 sm:space-y-4 sm:p-4" style={{ borderRadius: radius }}>
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-medium sm:text-sm">{t('theme.dashboardPreview')}</p>
            <p className="text-muted-foreground text-xs">
              {t('theme.currentTheme')}: {t(`theme.${customization.baseColor}`, { defaultValue: baseName })} / {t(`theme.${colorTheme}`, { defaultValue: accentName })} • {resolvedTheme === 'dark' ? t('theme.dark') : t('theme.light')}
            </p>
          </div>
          <div className="flex gap-2">
            <span className="bg-primary h-2.5 w-2.5 rounded-full" />
            <span className="bg-border h-2.5 w-2.5 rounded-full" />
            <span className="bg-accent h-2.5 w-2.5 rounded-full" />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-2">
            <div className="bg-primary/80 h-3 rounded" style={{ borderRadius: radius }} />
            <div className="bg-muted h-3 rounded" style={{ borderRadius: radius }} />
            <div className="bg-accent h-3 rounded" style={{ borderRadius: radius }} />
          </div>
          <div className="space-y-2">
            <div className="bg-background text-muted-foreground flex h-9 items-center rounded border px-3 text-xs" style={{ borderRadius: radius }}>
              {t('theme.sampleInput')}
            </div>
            <div className="bg-primary text-primary-foreground flex h-9 items-center justify-center rounded text-xs font-medium" style={{ borderRadius: radius }}>
              {t('theme.primaryButton')}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
