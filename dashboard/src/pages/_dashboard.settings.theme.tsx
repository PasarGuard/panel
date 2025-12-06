import { useTranslation } from 'react-i18next'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import { useTheme, colorThemes, type ColorTheme, type Radius } from '@/components/common/theme-provider'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { CheckCircle2, SunMoon, Palette, Ruler, Eye, RotateCcw, Sun, Moon, Monitor, CalendarClock, Languages } from 'lucide-react'
import { Button } from '@/components/ui/button'
import useDirDetection from '@/hooks/use-dir-detection'
import { Switch } from '@/components/ui/switch'
import { getDatePickerPreference, setDatePickerPreference, type DatePickerPreference } from '@/utils/userPreferenceStorage'

const colorThemeData = [
  { name: 'default', label: 'theme.default', dot: '#2563eb' },
  { name: 'red', label: 'theme.red', dot: '#ef4444' },
  { name: 'rose', label: 'theme.rose', dot: '#e11d48' },
  { name: 'orange', label: 'theme.orange', dot: '#f97316' },
  { name: 'green', label: 'theme.green', dot: '#22c55e' },
  { name: 'blue', label: 'theme.blue', dot: '#3b82f6' },
  { name: 'yellow', label: 'theme.yellow', dot: '#eab308' },
  { name: 'violet', label: 'theme.violet', dot: '#8b5cf6' },
] as const

const radiusOptions = [
  { value: '0', label: 'theme.radiusNone', description: '0px' },
  { value: '0.3rem', label: 'theme.radiusSmall', description: '0.3rem' },
  { value: '0.5rem', label: 'theme.radiusMedium', description: '0.5rem' },
  { value: '0.75rem', label: 'theme.radiusLarge', description: '0.75rem' },
] as const

const modeOptions = ['light', 'dark', 'system'] as const

const modeIcons: Record<(typeof modeOptions)[number], JSX.Element> = {
  light: <Sun className="h-4 w-4 text-primary" />,
  dark: <Moon className="h-4 w-4 text-primary" />,
  system: <Monitor className="h-4 w-4 text-primary" />,
}

export default function ThemeSettings() {
  const { t, i18n } = useTranslation()
  const { theme, colorTheme, radius, resolvedTheme, setTheme, setColorTheme, setRadius, resetToDefaults, isSystemTheme } = useTheme()
  const dir = useDirDetection()
  const [isResetting, setIsResetting] = useState(false)
  const [datePickerPreference, setDatePickerPreferenceState] = useState<DatePickerPreference>('locale')
  const isDatePickerFollowingLocale = datePickerPreference === 'locale'
  const defaultManualDatePreference: Exclude<DatePickerPreference, 'locale'> = i18n.language === 'fa' ? 'persian' : 'gregorian'
  const datePickerModeCopy: Record<DatePickerPreference, string> = {
    locale: t('theme.datePickerModeLocale'),
    gregorian: t('theme.datePickerModeGregorian'),
    persian: t('theme.datePickerModePersian'),
  }

  useEffect(() => {
    setDatePickerPreferenceState(getDatePickerPreference())
  }, [])

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme)

    // Get the appropriate icon for the toast
    const getThemeIcon = (theme: string) => {
      switch (theme) {
        case 'light':
          return '☀️'
        case 'dark':
          return '🌙'
        case 'system':
          return '💻'
        default:
          return '🎨'
      }
    }

    toast.success(t('success'), {
      description: `${getThemeIcon(newTheme)} ${t('theme.themeChanged')}`,
      duration: 2000,
    })
  }

  const handleColorChange = (colorName: string) => {
    if (Object.keys(colorThemes).includes(colorName)) {
      setColorTheme(colorName as ColorTheme)

      // Get the color dot for the toast
      const colorData = colorThemeData.find(c => c.name === colorName)
      const colorEmoji = '🎨'

      toast.success(t('success'), {
        description: `${colorEmoji} ${t('theme.themeSaved')} - ${t(colorData?.label || '')}`,
        duration: 2000,
      })
    }
  }

  const handleRadiusChange = (radiusValue: string) => {
    if (['0', '0.3rem', '0.5rem', '0.75rem'].includes(radiusValue)) {
      setRadius(radiusValue as Radius)

      const radiusData = radiusOptions.find(r => r.value === radiusValue)

      toast.success(t('success'), {
        description: `📐 ${t('theme.radiusSaved')} - ${t(radiusData?.label || '')}`,
        duration: 2000,
      })
    }
  }

  const persistDatePickerPreference = (preference: DatePickerPreference) => {
    setDatePickerPreferenceState(preference)
    setDatePickerPreference(preference)
    toast.success(t('success'), {
      description: `📅 ${t('theme.datePickerPreferenceSaved')} • ${datePickerModeCopy[preference]}`,
      duration: 2000,
    })
  }

  const handleDatePickerAutoToggle = (checked: boolean) => {
    if (checked) {
      persistDatePickerPreference('locale')
      return
    }
    const nextPreference = datePickerPreference === 'locale' ? defaultManualDatePreference : datePickerPreference
    persistDatePickerPreference(nextPreference)
  }

  const handleManualDatePreferenceChange = (preference: Exclude<DatePickerPreference, 'locale'>) => {
    persistDatePickerPreference(preference)
  }

  const handleResetToDefaults = async () => {
    setIsResetting(true)
    try {
      resetToDefaults()
      toast.success(t('success'), {
        description: '🔄 ' + t('theme.resetSuccess'),
        duration: 3000,
      })
    } catch (error) {
      toast.error(t('error'), {
        description: '❌ ' + t('theme.resetFailed'),
        duration: 3000,
      })
    } finally {
      setIsResetting(false)
    }
  }

  return (
    <div className="space-y-10 px-4 pb-12 pt-6 sm:pt-8">
      <section className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <SunMoon className="h-4 w-4 text-primary" />
              <p className="text-base font-semibold sm:text-lg">{t('theme.mode')}</p>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('theme.modeDescription')}</p>
          </div>
          {isSystemTheme && (
            <span className="text-xs text-muted-foreground sm:text-sm rtl:text-left">
              {t('theme.system')}: {resolvedTheme === 'dark' ? t('theme.dark') : t('theme.light')}
            </span>
          )}
        </div>

        <RadioGroup value={theme} onValueChange={handleThemeChange} className="grid gap-3 sm:grid-cols-3">
          {modeOptions.map(option => (
            <div dir={dir} key={option} className="relative">
              <RadioGroupItem value={option} id={option} className="peer sr-only" />
              <Label
                htmlFor={option}
                dir={dir}
                className={cn(
                  'flex cursor-pointer items-start justify-between gap-3 rounded-lg border border-border/70 bg-background px-4 py-3 text-sm transition-colors',
                  'hover:border-primary/60 hover:bg-accent/40',
                  'peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5',
                )}
              >
                <div className="space-y-1 min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {modeIcons[option]}
                    <span className="font-medium">{t(`theme.${option}`)}</span>
                  </div>
                  <span className="block text-xs leading-relaxed text-muted-foreground">{t(`theme.${option}Description`)}</span>
                </div>
                {theme === option && <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-primary ltr:ml-auto rtl:mr-auto" />}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Palette className="h-4 w-4 text-primary" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.color')}</p>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('theme.colorDescription')}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {colorThemeData.map(color => (
            <button
              key={color.name}
              onClick={() => handleColorChange(color.name)}
              dir={dir}
              className={cn(
                'group flex items-center gap-3 rounded-md border border-border/70 px-4 py-3 text-left transition-colors',
                'hover:border-primary/60 hover:bg-accent/40',
                colorTheme === color.name ? 'border-primary bg-primary/5' : 'bg-background',
              )}
              aria-label={color.label}
            >
              <span
                className={cn(
                  'h-8 w-8 rounded-full border shadow-sm transition-transform group-hover:scale-105',
                  colorTheme === color.name ? 'border-primary' : 'border-border',
                )}
                style={{ background: color.dot }}
              />
              <span className="text-sm font-medium">{t(color.label)}</span>
              {colorTheme === color.name && <CheckCircle2 className="h-4 w-4 text-primary ltr:ml-auto rtl:mr-auto" />}
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Ruler className="h-4 w-4 text-primary" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.radius')}</p>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('theme.radiusDescription')}</p>
        </div>
        <RadioGroup value={radius} onValueChange={handleRadiusChange} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {radiusOptions.map(option => (
            <div key={option.value} className="relative">
              <RadioGroupItem value={option.value} id={`radius-${option.value}`} className="peer sr-only" />
              <Label
                htmlFor={`radius-${option.value}`}
                dir={dir}
                className={cn(
                  'flex cursor-pointer flex-wrap items-start gap-3 rounded-lg border border-border/70 bg-background px-4 py-3 text-sm transition-colors',
                  'hover:border-primary/50 hover:bg-accent/40',
                  'peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5',
                  'sm:flex-nowrap sm:items-center',
                )}
              >
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded border bg-muted" style={{ borderRadius: option.value }}>
                  <div className="h-4 w-4 bg-primary/30" style={{ borderRadius: option.value }} />
                </div>
                <div className="min-w-0 flex-1 space-y-0.5">
                  <span className="block font-medium">{t(option.label)}</span>
                  <span className="block text-xs leading-relaxed text-muted-foreground break-words">{option.description}</span>
                </div>
                {radius === option.value && <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-primary ltr:ml-auto rtl:mr-auto" />}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </section>

      <section className="space-y-3">
        <div className="flex flex-col gap-3 rounded-lg border border-border/70 bg-background/60 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-primary" />
              <p className="text-base font-semibold sm:text-lg">{t('theme.datePicker')}</p>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('theme.datePickerDescription')}</p>
          </div>
          <div className="flex items-center gap-3 justify-between rounded-lg border border-border/70 bg-muted/40 px-3 py-2">
            <div className="space-y-0.5">
              <p className="text-xs font-medium text-foreground">{t('theme.datePickerFollowLocale')}</p>
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t('theme.datePickerManualHint')}</p>
            </div>
            <Switch checked={isDatePickerFollowingLocale} onCheckedChange={handleDatePickerAutoToggle} aria-label={t('theme.datePickerFollowLocale')} />
          </div>
        </div>

        <div
          className="grid grid-cols-1 gap-2 pb-6 sm:pb-2 rounded-lg border border-dashed border-border/70 bg-muted/30 px-3 py-2 sm:flex sm:flex-wrap sm:items-center"
          dir={dir}
        >
          {(['gregorian', 'persian'] as const).map(option => (
            <Button
              key={option}
              type="button"
              variant={datePickerPreference === option ? 'default' : 'outline'}
              size="sm"
              className="flex w-full items-center justify-center gap-2 sm:w-auto sm:justify-start"
              disabled={isDatePickerFollowingLocale}
              onClick={() => handleManualDatePreferenceChange(option)}
            >
              <CalendarClock className="h-3.5 w-3.5" />
              <span className="text-sm font-medium">{datePickerModeCopy[option]}</span>
            </Button>
          ))}
          <div className="flex items-center justify-start gap-2 mt-3 sm:mt-0 text-xs text-muted-foreground">
            <Languages className="h-3.5 w-3.5 text-primary" />
            <span className="font-medium text-foreground">{datePickerModeCopy[datePickerPreference]}</span>
            {isDatePickerFollowingLocale && (
              <span className="hidden text-muted-foreground sm:inline">{t('theme.datePickerModeLocale')}</span>
            )}
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Eye className="h-4 w-4 text-primary" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.preview')}</p>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('theme.previewDescription')}</p>
        </div>
        <div className="space-y-4 rounded-lg border border-border/70 bg-muted/30 p-4" style={{ borderRadius: radius }}>
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium">{t('theme.dashboardPreview')}</p>
              <p className="text-xs text-muted-foreground">
                {t('theme.currentTheme')}: {t(colorThemeData.find(c => c.name === colorTheme)?.label || '')} • {resolvedTheme === 'dark' ? t('theme.dark') : t('theme.light')}
              </p>
            </div>
            <div className="flex gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-primary" />
              <span className="h-2.5 w-2.5 rounded-full bg-border" />
              <span className="h-2.5 w-2.5 rounded-full bg-accent" />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <div className="h-3 rounded bg-primary/80" style={{ borderRadius: radius }} />
              <div className="h-3 rounded bg-muted" style={{ borderRadius: radius }} />
              <div className="h-3 rounded bg-accent" style={{ borderRadius: radius }} />
            </div>
            <div className="space-y-2">
              <div className="flex h-9 items-center rounded border bg-background px-3 text-xs text-muted-foreground" style={{ borderRadius: radius }}>
                {t('theme.sampleInput')}
              </div>
              <div className="flex h-9 items-center justify-center rounded bg-primary text-xs font-medium text-primary-foreground" style={{ borderRadius: radius }}>
                {t('theme.primaryButton')}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <RotateCcw className="h-4 w-4 text-primary" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.resetToDefaults')}</p>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('theme.resetDescription')}</p>
        </div>
        <Button variant="outline" onClick={handleResetToDefaults} disabled={isResetting} className="w-full sm:w-auto">
          {isResetting ? t('theme.resetting') : t('theme.reset')}
        </Button>
      </section>
    </div>
  )
}
