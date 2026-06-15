import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { SearchIcon, X, RefreshCw, Filter } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import ViewToggle, { ViewMode } from '@/components/common/view-toggle'

interface ApiKeyFiltersProps {
  search: string
  onSearchChange: (value: string) => void
  isFetching?: boolean
  onRefresh: () => void
  viewMode?: ViewMode
  onViewModeChange?: (mode: ViewMode) => void
  filters: {
    status?: string
    role_id?: number
    key_id?: number
  }
  onFilterChange: (filters: { status?: string; role_id?: number; key_id?: number }) => void
  onAdvanceSearchOpen: () => void
}

export const ApiKeyFilters = ({
  search,
  onSearchChange,
  isFetching,
  onRefresh,
  viewMode,
  onViewModeChange,
  filters,
  onFilterChange,
  onAdvanceSearchOpen,
}: ApiKeyFiltersProps) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  const clearSearch = () => {
    onSearchChange('')
  }

  const hasActiveFilters = !!(filters.status || filters.role_id || filters.key_id)
  const activeFiltersCount = (filters.status ? 1 : 0) + (filters.role_id ? 1 : 0) + (filters.key_id ? 1 : 0)

  return (
    <div dir={dir} className="flex items-center gap-2 md:gap-4">
      {/* Search Input */}
      <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
        <SearchIcon className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 text-input-placeholder')} />
        <Input 
          placeholder={t('search')} 
          value={search} 
          onChange={(e) => onSearchChange(e.target.value)} 
          className="pl-8 pr-10" 
        />
        {search && (
          <button type="button" onClick={clearSearch} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600')}>
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="flex flex-shrink-0 items-center gap-2">
        {/* Advanced Filter Button */}
        <div className="flex h-full flex-shrink-0 items-center gap-1">
          <Button 
            type="button" 
            size="icon-md" 
            variant="ghost" 
            className="relative flex h-9 w-9 items-center justify-center rounded-lg border" 
            onClick={onAdvanceSearchOpen}
          >
            <Filter className="h-4 w-4" />
            {hasActiveFilters && (
              <Badge variant="default" className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary p-0 text-[10.5px] text-primary-foreground">
                {activeFiltersCount}
              </Badge>
            )}
          </Button>
          {hasActiveFilters && (
            <Popover>
              <PopoverTrigger asChild>
                <Button 
                  type="button" 
                  size="sm" 
                  variant="outline" 
                  className={cn('h-9 w-9 p-0', dir === 'rtl' ? 'rounded-r-none border-r-0' : 'rounded-l-none border-l-0')} 
                  onClick={() => onFilterChange({})}
                >
                  <X className="h-3 w-3" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-2" side={dir === 'rtl' ? 'left' : 'right'} align="center">
                <p className="text-sm">{t('clearAllFilters', { defaultValue: 'Clear All Filters' })}</p>
              </PopoverContent>
            </Popover>
          )}
        </div>

        {/* Refresh Button */}
        <Button
          type="button"
          size="icon-md"
          onClick={onRefresh}
          variant="ghost"
          className={cn('relative flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-200', isFetching && 'opacity-70')}
          aria-label={t('autoRefresh.refreshNow')}
          title={t('autoRefresh.refreshNow')}
        >
          <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
        </Button>
        {viewMode && onViewModeChange && <ViewToggle value={viewMode} onChange={onViewModeChange} />}
      </div>
    </div>
  )
}
