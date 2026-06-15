import { useTranslation } from 'react-i18next'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import { useTheme, colorThemes, type ColorTheme, type Radius } from '@/app/providers/theme-provider'
import { useEffect, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { CheckCircle2, SunMoon, Palette, Ruler, Eye, RotateCcw, Sun, Moon, Monitor, CalendarClock, Languages, BarChart3, TrendingUp, FileJson2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import useDirDetection from '@/hooks/use-dir-detection'
import { Switch } from '@/components/ui/switch'
import {
  getCoresListUseConfigModal,
  getDatePickerPreference,
  getChartViewTypePreference,
  setCoresListUseConfigModal,
  setDatePickerPreference,
  setChartViewTypePreference,
  type DatePickerPreference,
  type ChartViewType,
} from '@/utils/userPreferenceStorage'
import { isPersianLocaleLanguage } from '@/utils/datePickerUtils'

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

const modeIcons: Record<(typeof modeOptions)[number], ReactNode> = {
  light: <Sun className="text-primary h-4 w-4" />,
  dark: <Moon className="text-primary h-4 w-4" />,
  system: <Monitor className="text-primary h-4 w-4" />,
}

const chartViewOptions = ['bar', 'area'] as const

const chartViewIcons: Record<(typeof chartViewOptions)[number], ReactNode> = {
  bar: <BarChart3 className="text-primary h-4 w-4" />,
  area: <TrendingUp className="text-primary h-4 w-4" />,
}

export default function ThemeSettings() {
  const { t, i18n } = useTranslation()
  const { theme, colorTheme, radius, resolvedTheme, setTheme, setColorTheme, setRadius, resetToDefaults, isSystemTheme } = useTheme()
  const dir = useDirDetection()
  const [isResetting, setIsResetting] = useState(false)
  const [datePickerPreference, setDatePickerPreferenceState] = useState<DatePickerPreference>('locale')
  const [chartViewType, setChartViewTypeState] = useState<ChartViewType>('bar')
  const [coresListUseConfigModal, setCoresListUseConfigModalState] = useState(false)
  const isDatePickerFollowingLocale = datePickerPreference === 'locale'
  const defaultManualDatePreference: Exclude<DatePickerPreference, 'locale'> = isPersianLocaleLanguage(i18n.resolvedLanguage ?? i18n.language) ? 'persian' : 'gregorian'
  const datePickerModeCopy: Record<DatePickerPreference, string> = {
    locale: t('theme.datePickerModeLocale'),
    gregorian: t('theme.datePickerModeGregorian'),
    persian: t('theme.datePickerModePersian'),
  }
  const chartViewTypeCopy: Record<ChartViewType, string> = {
    bar: t('theme.chartViewBar'),
    area: t('theme.chartViewArea'),
  }

  useEffect(() => {
    setDatePickerPreferenceState(getDatePickerPreference())
    setChartViewTypeState(getChartViewTypePreference())
    setCoresListUseConfigModalState(getCoresListUseConfigModal())
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

  const handleChartViewTypeChange = (viewType: ChartViewType) => {
    setChartViewTypeState(viewType)
    setChartViewTypePreference(viewType)
    toast.success(t('success'), {
      description: `📊 ${t('theme.chartViewSaved')} • ${chartViewTypeCopy[viewType]}`,
      duration: 2000,
    })
  }

  const handleCoresListUseConfigModalChange = (checked: boolean) => {
    setCoresListUseConfigModalState(checked)
    setCoresListUseConfigModal(checked)
    toast.success(t('success'), {
      description: `🧩 ${t('theme.coresListEditorSaved')} • ${checked ? t('theme.coresListEditorModal') : t('theme.coresListEditorFullPage')}`,
      duration: 2000,
    })
  }

  const handleResetToDefaults = async () => {
    setIsResetting(true)
    try {
      resetToDefaults()
      setDatePickerPreferenceState('locale')
      setDatePickerPreference('locale')
      setChartViewTypeState('bar')
      setChartViewTypePreference('bar')
      setCoresListUseConfigModalState(false)
      setCoresListUseConfigModal(false)
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
    <div className="space-y-10 px-4 pt-6 pb-12 sm:pt-8">
      <section className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <SunMoon className="text-primary h-4 w-4" />
              <p className="text-base font-semibold sm:text-lg">{t('theme.mode')}</p>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.modeDescription')}</p>
          </div>
          {isSystemTheme && (
            <span className="text-muted-foreground text-xs sm:text-sm rtl:text-left">
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
                  'border-border/70 bg-background flex cursor-pointer items-start justify-between gap-3 rounded-lg border px-3 py-3 text-xs transition-colors sm:px-4 sm:text-sm',
                  'hover:border-primary/60 hover:bg-accent/40',
                  'peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5',
                )}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    {modeIcons[option]}
                    <span className="font-medium">{t(`theme.${option}`)}</span>
                  </div>
                  <span className="text-muted-foreground block text-xs leading-relaxed">{t(`theme.${option}Description`)}</span>
                </div>
                {theme === option && <CheckCircle2 className="text-primary h-4 w-4 flex-shrink-0 ltr:ml-auto rtl:mr-auto" />}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Palette className="text-primary h-4 w-4" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.color')}</p>
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.colorDescription')}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {colorThemeData.map(color => (
            <button
              key={color.name}
              onClick={() => handleColorChange(color.name)}
              dir={dir}
              className={cn(
                'group border-border/70 flex items-center gap-3 rounded-md border px-3 py-3 text-left transition-colors sm:px-4',
                'hover:border-primary/60 hover:bg-accent/40',
                colorTheme === color.name ? 'border-primary bg-primary/5' : 'bg-background',
              )}
              aria-label={color.label}
            >
              <span
                className={cn('h-8 w-8 rounded-full border shadow-sm transition-transform group-hover:scale-105', colorTheme === color.name ? 'border-primary' : 'border-border')}
                style={{ background: color.dot }}
              />
              <span className="text-xs font-medium sm:text-sm">{t(color.label)}</span>
              {colorTheme === color.name && <CheckCircle2 className="text-primary h-4 w-4 ltr:ml-auto rtl:mr-auto" />}
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Ruler className="text-primary h-4 w-4" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.radius')}</p>
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.radiusDescription')}</p>
        </div>
        <RadioGroup value={radius} onValueChange={handleRadiusChange} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {radiusOptions.map(option => (
            <div key={option.value} className="relative">
              <RadioGroupItem value={option.value} id={`radius-${option.value}`} className="peer sr-only" />
              <Label
                htmlFor={`radius-${option.value}`}
                dir={dir}
                className={cn(
                  'border-border/70 bg-background flex cursor-pointer flex-wrap items-start gap-3 rounded-lg border px-3 py-3 text-xs transition-colors sm:px-4 sm:text-sm',
                  'hover:border-primary/50 hover:bg-accent/40',
                  'peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5',
                  'sm:flex-nowrap sm:items-center',
                )}
              >
                <div className="bg-muted flex h-10 w-10 flex-shrink-0 items-center justify-center rounded border" style={{ borderRadius: option.value }}>
                  <div className="bg-primary/30 h-4 w-4" style={{ borderRadius: option.value }} />
                </div>
                <div className="min-w-0 flex-1 space-y-0.5">
                  <span className="block font-medium">{t(option.label)}</span>
                  <span className="text-muted-foreground block text-xs leading-relaxed break-words">{option.description}</span>
                </div>
                {radius === option.value && <CheckCircle2 className="text-primary h-4 w-4 flex-shrink-0 ltr:ml-auto rtl:mr-auto" />}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </section>

      <section className="space-y-3">
        <div className="border-border/70 bg-background/60 flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <CalendarClock className="text-primary h-4 w-4" />
              <p className="text-base font-semibold sm:text-lg">{t('theme.datePicker')}</p>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.datePickerDescription')}</p>
          </div>
          <div className="border-border/70 bg-muted/40 flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
            <div className="space-y-0.5">
              <p className="text-foreground text-xs font-medium">{t('theme.datePickerFollowLocale')}</p>
              <p className="text-muted-foreground text-[11px] leading-relaxed">{t('theme.datePickerManualHint')}</p>
            </div>
            <Switch checked={isDatePickerFollowingLocale} onCheckedChange={handleDatePickerAutoToggle} aria-label={t('theme.datePickerFollowLocale')} />
          </div>
        </div>

        <div className="border-border/70 bg-muted/30 grid grid-cols-1 gap-2 rounded-lg border border-dashed px-3 py-2 pb-6 sm:flex sm:flex-wrap sm:items-center sm:pb-2" dir={dir}>
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
              <span className="text-xs font-medium sm:text-sm">{datePickerModeCopy[option]}</span>
            </Button>
          ))}
          <div className="text-muted-foreground mt-3 flex items-center justify-start gap-2 text-xs sm:mt-0">
            <Languages className="text-primary h-3.5 w-3.5" />
            <span className="text-foreground font-medium">{datePickerModeCopy[datePickerPreference]}</span>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <BarChart3 className="text-primary h-4 w-4" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.chartViewType')}</p>
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.chartViewDescription')}</p>
        </div>
        <RadioGroup value={chartViewType} onValueChange={value => handleChartViewTypeChange(value as ChartViewType)} className="grid gap-2 sm:grid-cols-2">
          {chartViewOptions.map(option => (
            <div dir={dir} key={option} className="relative">
              <RadioGroupItem value={option} id={`chart-view-${option}`} className="peer sr-only" />
              <Label
                htmlFor={`chart-view-${option}`}
                className={cn(
                  'border-border/70 bg-background flex cursor-pointer items-start justify-between gap-3 rounded-lg border px-3 py-3 text-xs transition-colors sm:px-4 sm:text-sm',
                  'hover:border-primary/50 hover:bg-accent/40',
                  'peer-data-[state=checked]:border-primary peer-data-[state=checked]:bg-primary/5',
                )}
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    {chartViewIcons[option]}
                    <span className="font-medium">{option === 'bar' ? t('theme.chartViewBar') : t('theme.chartViewArea')}</span>
                  </div>
                  <span className="text-muted-foreground block text-xs leading-relaxed">{option === 'bar' ? t('theme.chartViewBarDescription') : t('theme.chartViewAreaDescription')}</span>
                </div>
                {chartViewType === option && <CheckCircle2 className="text-primary h-4 w-4 flex-shrink-0 ltr:ml-auto rtl:mr-auto" />}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </section>

      <section className="space-y-3">
        <div className="border-border/70 bg-background/60 flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <FileJson2 className="text-primary h-4 w-4" />
              <p className="text-base font-semibold sm:text-lg">{t('theme.coresListEditor')}</p>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.coresListEditorDescription')}</p>
          </div>
          <div className="border-border/70 bg-muted/40 flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
            <div className="space-y-0.5">
              <p className="text-foreground text-xs font-medium">{t('theme.coresListEditorModal')}</p>
              <p className="text-muted-foreground text-[11px] leading-relaxed">{t('theme.coresListEditorModalHint')}</p>
            </div>
            <Switch checked={coresListUseConfigModal} onCheckedChange={handleCoresListUseConfigModalChange} aria-label={t('theme.coresListEditorModal')} />
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Eye className="text-primary h-4 w-4" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.preview')}</p>
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.previewDescription')}</p>
        </div>
        <div className="border-border/70 bg-muted/30 space-y-3 rounded-lg border p-3 sm:space-y-4 sm:p-4" style={{ borderRadius: radius }}>
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-medium sm:text-sm">{t('theme.dashboardPreview')}</p>
              <p className="text-muted-foreground text-xs">
                {t('theme.currentTheme')}: {t(colorThemeData.find(c => c.name === colorTheme)?.label || '')} • {resolvedTheme === 'dark' ? t('theme.dark') : t('theme.light')}
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
      </section>

      <section className="flex flex-col gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <RotateCcw className="text-primary h-4 w-4" />
            <p className="text-base font-semibold sm:text-lg">{t('theme.resetToDefaults')}</p>
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed sm:text-sm">{t('theme.resetDescription')}</p>
        </div>
        <Button variant="outline" onClick={handleResetToDefaults} disabled={isResetting} className="w-full sm:w-auto">
          {isResetting ? t('theme.resetting') : t('theme.reset')}
        </Button>
      </section>
    </div>
  )
}
