import ViewToggle, { type ViewMode } from '@/components/common/view-toggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { type ProxyHostSecurity, type UserStatus } from '@/service/api'
import { Filter, RefreshCw, SearchIcon, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface HostListFilters {
  search?: string
  status?: UserStatus[]
  inbound_tags?: string[]
  security?: ProxyHostSecurity
  is_disabled?: boolean
}

interface HostFiltersProps {
  filters: HostListFilters
  onFilterChange: (filters: Partial<HostListFilters>) => void
  onRefresh?: () => Promise<unknown> | void
  isRefreshing?: boolean
  advanceSearchOnOpen: (status: boolean) => void
  onClearAdvanceSearch?: () => void
  viewMode?: ViewMode
  onViewModeChange?: (mode: ViewMode) => void
}

export function HostFilters({ filters, onFilterChange, onRefresh, isRefreshing, advanceSearchOnOpen, onClearAdvanceSearch, viewMode, onViewModeChange }: HostFiltersProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const search = filters.search || ''

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    onFilterChange({
      search: value.trim() ? value : undefined,
    })
  }

  const clearSearch = () => {
    onFilterChange({
      search: undefined,
    })
  }

  const handleManualRefresh = () => {
    if (onRefresh) {
      onRefresh()
    }
  }

  const handleOpenAdvanceSearch = () => {
    advanceSearchOnOpen(true)
  }

  const hasActiveAdvanceFilters = () => {
    return Boolean((filters.status && filters.status.length > 0) || (filters.inbound_tags && filters.inbound_tags.length > 0) || filters.security || typeof filters.is_disabled === 'boolean')
  }

  const getActiveFiltersCount = () => {
    let count = 0
    if (filters.status && filters.status.length > 0) count++
    if (filters.inbound_tags && filters.inbound_tags.length > 0) count++
    if (filters.security) count++
    if (typeof filters.is_disabled === 'boolean') count++
    return count
  }

  return (
    <div dir={dir} className="flex items-center gap-2 md:gap-4">
      <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
        <SearchIcon className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 text-input-placeholder')} />
        <Input placeholder={t('search')} value={search} onChange={handleSearchChange} className="pl-8 pr-10" />
        {search && (
          <button onClick={clearSearch} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600')}>
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="flex flex-shrink-0 items-center gap-2">
        <div className="flex h-full flex-shrink-0 items-center gap-1">
          <Button size="icon-md" variant="ghost" className="relative flex h-9 w-9 items-center justify-center rounded-lg border" onClick={handleOpenAdvanceSearch}>
            <Filter className="h-4 w-4" />
            {hasActiveAdvanceFilters() && (
              <Badge variant="default" className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary p-0 text-[10.5px] text-primary-foreground">
                {getActiveFiltersCount()}
              </Badge>
            )}
          </Button>
          {hasActiveAdvanceFilters() && onClearAdvanceSearch && (
            <Popover>
              <PopoverTrigger asChild>
                <Button size="sm" variant="outline" className={cn('h-9 w-9 p-0', dir === 'rtl' ? 'rounded-r-none border-r-0' : 'rounded-l-none border-l-0')} onClick={onClearAdvanceSearch}>
                  <X className="h-3 w-3" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-2" side={dir === 'rtl' ? 'left' : 'right'} align="center">
                <p className="text-sm">{t('clearAllFilters', { defaultValue: 'Clear All Filters' })}</p>
              </PopoverContent>
            </Popover>
          )}
        </div>

        <Button
          size="icon-md"
          onClick={handleManualRefresh}
          variant="ghost"
          className={cn('relative flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-200', isRefreshing && 'opacity-70')}
          aria-label={t('autoRefresh.refreshNow')}
          title={t('autoRefresh.refreshNow')}
        >
          <RefreshCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} />
        </Button>
        {viewMode && onViewModeChange && <ViewToggle value={viewMode} onChange={onViewModeChange} />}
      </div>
    </div>
  )
}
