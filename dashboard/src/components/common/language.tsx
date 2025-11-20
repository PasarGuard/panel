import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SidebarContext } from '@/components/ui/sidebar'
import { LanguagesIcon } from 'lucide-react'
import { useContext } from 'react'
import { useTranslation } from 'react-i18next'

export const Language: React.FC = () => {
  const { i18n, t } = useTranslation()

  // Safely get sidebar state, defaulting to 'expanded' if not available
  const sidebarContext = useContext(SidebarContext)
  const sidebarState: 'expanded' | 'collapsed' = sidebarContext?.state ?? 'expanded'
  const isMobile = sidebarContext?.isMobile ?? false

  const changeLanguage = async (lang: string) => {
    await i18n.changeLanguage(lang)
    document.documentElement.lang = lang
    document.documentElement.setAttribute('dir', i18n.dir())
  }

  // Collapsed state (desktop only) - icon with popover
  // On mobile, always use expanded UI since there's no collapsed sidebar concept
  if (sidebarState === 'collapsed' && !isMobile) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="icon" className="h-8 w-8">
            <LanguagesIcon className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-48 p-2" side="right" align="start">
          <div className="space-y-1">
            <div className="px-2 py-1.5 text-sm font-semibold">{t('language.title', { defaultValue: 'Language' })}</div>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => changeLanguage('en')}>
              English
            </Button>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => changeLanguage('fa')}>
              فارسی
            </Button>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => changeLanguage('zh')}>
              简体中文
            </Button>
            <Button variant="ghost" size="sm" className="w-full justify-start" onClick={() => changeLanguage('ru')}>
              Русский
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
        <Button variant="outline" size="icon">
          <LanguagesIcon className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top">
        <DropdownMenuItem onClick={() => changeLanguage('en')}>English</DropdownMenuItem>
        <DropdownMenuItem onClick={() => changeLanguage('fa')}>فارسی</DropdownMenuItem>
        <DropdownMenuItem onClick={() => changeLanguage('zh')}>简体中文</DropdownMenuItem>
        <DropdownMenuItem onClick={() => changeLanguage('ru')}>Русский</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
