import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

export type TimePeriod = string
export type TimeSelectorShortcut = {
  value: string
  label: string
  quick?: boolean
}

export const DEFAULT_TIME_SELECTOR_SHORTCUTS: TimeSelectorShortcut[] = [
  { value: '24h', label: '24h' },
  { value: '3d', label: '3d' },
  { value: '1w', label: '1w' },
  { value: '1m', label: '1m' },
]

export const TRAFFIC_TIME_SELECTOR_SHORTCUTS: TimeSelectorShortcut[] = [
  { value: '1h', label: '1h', quick: true },
  { value: '2h', label: '2h' },
  { value: '4h', label: '4h' },
  { value: '6h', label: '6h', quick: true },
  { value: '12h', label: '12h' },
  { value: '24h', label: '24h', quick: true },
  { value: '2d', label: '2d' },
  { value: '3d', label: '3d', quick: true },
  { value: '5d', label: '5d' },
  { value: '1w', label: '1w', quick: true },
  { value: '2w', label: '2w' },
  { value: '1m', label: '1m' },
  { value: 'all', label: 'all' },
]

interface TimeSelectorProps {
  selectedTime: string
  setSelectedTime: (value: string) => void
  shortcuts?: readonly TimeSelectorShortcut[]
  maxVisible?: number
  className?: string
}

export default function TimeSelector({ selectedTime, setSelectedTime, shortcuts = DEFAULT_TIME_SELECTOR_SHORTCUTS, maxVisible = shortcuts.length, className }: TimeSelectorProps) {
  const { t } = useTranslation()
  const [isMobileMoreOpen, setIsMobileMoreOpen] = useState(false)
  const [isDesktopMoreOpen, setIsDesktopMoreOpen] = useState(false)
  const moreLabelRaw = t('more', { defaultValue: 'More' })
  const moreLabel = moreLabelRaw ? moreLabelRaw.charAt(0).toLocaleUpperCase() + moreLabelRaw.slice(1) : 'More'

  const getShortcutLabel = (shortcut: TimeSelectorShortcut) => {
    if (shortcut.value === 'all') {
      return t('alltime', { defaultValue: 'All Time' })
    }
    return shortcut.label
  }

  const quickShortcuts = useMemo(() => {
    const explicitQuick = shortcuts.filter(shortcut => shortcut.quick)
    if (explicitQuick.length > 0) return explicitQuick
    return shortcuts.slice(0, maxVisible)
  }, [shortcuts, maxVisible])

  const desktopOverflowShortcuts = useMemo(() => {
    const quickValues = new Set(quickShortcuts.map(shortcut => shortcut.value))
    return shortcuts.filter(shortcut => !quickValues.has(shortcut.value))
  }, [shortcuts, quickShortcuts])

  const mobileQuickShortcuts = useMemo(() => quickShortcuts.slice(0, 4), [quickShortcuts])

  const mobileOverflowShortcuts = useMemo(() => {
    const quickValues = new Set(mobileQuickShortcuts.map(shortcut => shortcut.value))
    return shortcuts.filter(shortcut => !quickValues.has(shortcut.value))
  }, [shortcuts, mobileQuickShortcuts])

  const isMobileOverflowSelected = mobileOverflowShortcuts.some(shortcut => shortcut.value === selectedTime)
  const isDesktopOverflowSelected = desktopOverflowShortcuts.some(shortcut => shortcut.value === selectedTime)

  return (
    <div dir="ltr" className={cn('w-full min-w-0 max-w-full overflow-hidden rounded-md border border-border/60 bg-muted/20 p-1', className)}>
      <div className="flex w-full min-w-0 items-center gap-1 lg:hidden">
        <ToggleGroup
          type="single"
          value={selectedTime}
          onValueChange={value => value && setSelectedTime(value)}
          className="min-w-0 flex-nowrap gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          aria-label="Traffic range shortcuts"
        >
          {mobileQuickShortcuts.map(shortcut => (
            <ToggleGroupItem
              key={shortcut.value}
              value={shortcut.value}
              variant="default"
              className="h-7 min-w-[2.25rem] shrink-0 border-0 bg-transparent px-2.5 py-1 text-xs font-medium text-muted-foreground data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm"
            >
              {getShortcutLabel(shortcut)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {mobileOverflowShortcuts.length > 0 && (
          <DropdownMenu modal={false} open={isMobileMoreOpen} onOpenChange={setIsMobileMoreOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className={cn(
                  'h-7 min-w-[3.75rem] border-0 bg-transparent px-2 text-xs font-medium text-muted-foreground shadow-none hover:bg-background/70 hover:text-foreground',
                  isMobileOverflowSelected && 'bg-background text-foreground shadow-sm',
                )}
              >
                {moreLabel}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent dir="ltr" align="end" className="min-w-[7rem]" onInteractOutside={() => setIsMobileMoreOpen(false)}>
              <DropdownMenuRadioGroup
                value={selectedTime}
                onValueChange={value => {
                  setSelectedTime(value)
                  setIsMobileMoreOpen(false)
                }}
              >
                {mobileOverflowShortcuts.map(shortcut => (
                  <DropdownMenuRadioItem key={shortcut.value} value={shortcut.value} className="text-xs">
                    {getShortcutLabel(shortcut)}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      <div className="hidden w-full min-w-0 items-center gap-1 lg:flex">
        <ToggleGroup
          type="single"
          value={selectedTime}
          onValueChange={value => value && setSelectedTime(value)}
          className="min-w-0 flex-nowrap gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          aria-label="Traffic range shortcuts"
        >
          {quickShortcuts.map(shortcut => (
            <ToggleGroupItem
              key={shortcut.value}
              value={shortcut.value}
              variant="default"
              className="h-7 min-w-[2.25rem] shrink-0 border-0 bg-transparent px-2.5 py-1 text-xs font-medium text-muted-foreground data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm"
            >
              {getShortcutLabel(shortcut)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {desktopOverflowShortcuts.length > 0 && (
          <DropdownMenu modal={false} open={isDesktopMoreOpen} onOpenChange={setIsDesktopMoreOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className={cn(
                  'h-7 min-w-[3.75rem] border-0 bg-transparent px-2 text-xs font-medium text-muted-foreground shadow-none hover:bg-background/70 hover:text-foreground',
                  isDesktopOverflowSelected && 'bg-background text-foreground shadow-sm',
                )}
              >
                {moreLabel}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent dir="ltr" align="end" className="min-w-[7rem]" onInteractOutside={() => setIsDesktopMoreOpen(false)}>
              <DropdownMenuRadioGroup
                value={selectedTime}
                onValueChange={value => {
                  setSelectedTime(value)
                  setIsDesktopMoreOpen(false)
                }}
              >
                {desktopOverflowShortcuts.map(shortcut => (
                  <DropdownMenuRadioItem key={shortcut.value} value={shortcut.value} className="text-xs">
                    {getShortcutLabel(shortcut)}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </div>
  )
}
