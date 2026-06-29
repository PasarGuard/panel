import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
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
    key_id?: number
  }
  onFilterChange: (filters: { status?: string; key_id?: number }) => void
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

  const hasActiveFilters = !!(filters.status || filters.key_id)
  const activeFiltersCount = (filters.status ? 1 : 0) + (filters.key_id ? 1 : 0)

  return (
    <div dir={dir} className="flex items-center gap-2 md:gap-4">
      <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
        <SearchIcon className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'text-muted-foreground top-1/2 h-4 w-4 -translate-y-1/2')} />
        <Input
          placeholder={t('search', { defaultValue: 'Search' })}
          value={search}
          onChange={e => onSearchChange(e.target.value)}
          className={cn('pr-10 pl-8', dir === 'rtl' && 'pr-8 pl-10')}
        />
        {search && (
          <button
            type="button"
            onClick={clearSearch}
            className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'text-muted-foreground hover:text-foreground top-1/2 -translate-y-1/2')}
            aria-label={t('clear', { defaultValue: 'Clear' })}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="flex flex-shrink-0 items-center gap-1">
        <Button
          type="button"
          size="icon-md"
          variant="ghost"
          className={cn(
            'relative h-9 w-9 rounded-lg border',
            hasActiveFilters && (dir === 'rtl' ? 'rounded-l-none border-l-0' : 'rounded-r-none'),
          )}
          onClick={onAdvanceSearchOpen}
          aria-label={t('advanceSearch.title', { defaultValue: 'Advanced search' })}
          title={t('advanceSearch.title', { defaultValue: 'Advanced search' })}
        >
          <Filter className="h-4 w-4" />
          {hasActiveFilters && (
            <Badge variant="default" className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full p-0 text-[10px]">
              {activeFiltersCount}
            </Badge>
          )}
        </Button>

        {hasActiveFilters && (
          <Button
            type="button"
            size="icon-md"
            variant="outline"
            className={cn('h-9 w-9 rounded-lg', dir === 'rtl' ? 'rounded-r-none' : 'rounded-l-none border-l-0')}
            onClick={() => onFilterChange({})}
            aria-label={t('clearAllFilters', { defaultValue: 'Clear all filters' })}
            title={t('clearAllFilters', { defaultValue: 'Clear all filters' })}
          >
            <X className="h-4 w-4" />
          </Button>
        )}

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
