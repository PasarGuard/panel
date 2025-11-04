import { cn } from '@/lib/utils'
import { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'

export interface Tab {
  id: string
  label: string
  icon: LucideIcon
  url: string
}

interface NavigationTabsProps {
  tabs: Tab[]
  defaultTab?: string
  className?: string
  scrollable?: boolean
}

export function NavigationTabs({ tabs, defaultTab, className, scrollable = false }: NavigationTabsProps) {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()

  // Derive activeTab from current location
  const currentTab = tabs.find(tab => location.pathname === tab.url)
  const activeTab = currentTab?.id || defaultTab || tabs[0]?.id

  return (
    <div className={cn('relative w-full', className)}>
      <div className="flex border-b">
        <div className="w-full">
          <div
            className={cn(
              'flex px-4',
              scrollable && 'scrollbar-hide overflow-x-auto lg:flex-wrap',
            )}
          >
            {tabs.map(tab => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => navigate(tab.url)}
                  className={cn(
                    'relative flex-shrink-0 whitespace-nowrap px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'border-b-2 border-primary text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <tab.icon className="h-4 w-4" />
                    <span>{t(tab.label)}</span>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

