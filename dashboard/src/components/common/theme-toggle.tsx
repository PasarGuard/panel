import { Theme, useTheme } from './theme-provider'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SidebarContext } from '@/components/ui/sidebar'
import { Monitor, Moon, Sun } from 'lucide-react'
import { useCallback, useContext } from 'react'
import { useTranslation } from 'react-i18next'

export function ThemeToggle() {
  const { setTheme } = useTheme()
  const { t } = useTranslation()

  // Safely get sidebar state, defaulting to 'expanded' if not available
  const sidebarContext = useContext(SidebarContext)
  const sidebarState: 'expanded' | 'collapsed' = sidebarContext?.state ?? 'expanded'
  const isMobile = sidebarContext?.isMobile ?? false

  const toggleTheme = useCallback(
    (theme: Theme) => {
      setTheme(theme)
    },
    [setTheme],
  )

  // Collapsed state (desktop only) - icon with popover
  // On mobile, always use expanded UI since there's no collapsed sidebar concept
  if (sidebarState === 'collapsed' && !isMobile) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="icon" className="h-8 w-8 transition-colors duration-200">
            <Sun className="transition-all duration-300 ease-in-out dark:hidden" />
            <Moon className="hidden transition-all duration-300 ease-in-out dark:block" />
            <span className="sr-only">{t('theme.toggle')}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-48 p-2" side="right" align="start">
          <div className="space-y-1">
            <div className="px-2 py-1.5 text-sm font-semibold">{t('theme.title', { defaultValue: 'Theme' })}</div>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => toggleTheme('light')}>
              <Sun className="mr-2 h-4 w-4" />
              {t('theme.light')}
            </Button>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => toggleTheme('dark')}>
              <Moon className="mr-2 h-4 w-4" />
              {t('theme.dark')}
            </Button>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => toggleTheme('system')}>
              <Monitor className="mr-2 h-4 w-4" />
              {t('theme.system')}
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    )
  }

  // Expanded state - dropdown
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" className="transition-colors duration-200">
          <Sun className="transition-all duration-300 ease-in-out dark:hidden" />
          <Moon className="hidden transition-all duration-300 ease-in-out dark:block" />
          <span className="sr-only">{t('theme.toggle')}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="transition-all duration-200 ease-in-out">
        <DropdownMenuItem onClick={() => toggleTheme('light')} className="transition-colors duration-150 hover:bg-accent">
          <Sun className="mr-2 h-4 w-4 transition-transform duration-200 hover:scale-110" />
          {t('theme.light')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => toggleTheme('dark')} className="transition-colors duration-150 hover:bg-accent">
          <Moon className="mr-2 h-4 w-4 transition-transform duration-200 hover:scale-110" />
          {t('theme.dark')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => toggleTheme('system')} className="transition-colors duration-150 hover:bg-accent">
          <Monitor className="mr-2 h-4 w-4 transition-transform duration-200 hover:scale-110" />
          {t('theme.system')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
