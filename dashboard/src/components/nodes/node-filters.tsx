import { Input } from '@/components/ui/input'
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/pagination'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { SearchIcon, X, RefreshCw, Filter } from 'lucide-react'
import {useEffect} from 'react'
import { useTranslation } from 'react-i18next'
import { RefetchOptions } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {NodeStatus} from "@/service/api";

interface NodeFiltersProps {
  filters: {
    search?: string
    limit: number
    offset: number
    status?: NodeStatus[]
    core_id?: number
  }
  onFilterChange: (filters: Partial<NodeFiltersProps['filters']>) => void
  refetch?: (options?: RefetchOptions) => Promise<unknown>
  isFetching?: boolean
  advanceSearchOnOpen: (status: boolean) => void
  onClearAdvanceSearch?: () => void
}

export const NodeFilters = ({ filters, onFilterChange, refetch, isFetching, advanceSearchOnOpen, onClearAdvanceSearch }: NodeFiltersProps) => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { search, debouncedSearch, setSearch } = useDebouncedSearch(filters.search || '', 300)

  // Update filters when debounced search changes
  useEffect(() => {
    onFilterChange({
      search: debouncedSearch || undefined,
      offset: 0,
    })
  }, [debouncedSearch, onFilterChange])

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value)
  }

  const clearSearch = () => {
    setSearch('')
    onFilterChange({
      search: undefined,
      offset: 0,
    })
  }

  const handleManualRefresh = () => {
    if (refetch) {
      refetch()
    }
  }

  const handleOpenAdvanceSearch = () => {
    advanceSearchOnOpen(true)
  }

  // Check if any advance search filters are active
  const hasActiveAdvanceFilters = () => {
    const status = filters.status
    const core_id = filters.core_id
    return (status && status.length > 0) || core_id !== undefined
  }

  // Get the count of active advance filters
  const getActiveFiltersCount = () => {
    const status = filters.status
    const core_id = filters.core_id
    let count = 0
    if (status && status.length > 0) count++
    if (core_id !== undefined) count++
    return count
  }

  return (
    <div dir={dir} className="flex items-center gap-2 py-4 md:gap-4">
      {/* Search Input */}
      <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
        <SearchIcon className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 text-input-placeholder')} />
        <Input placeholder={t('search')} value={search} onChange={handleSearchChange} className="pl-8 pr-10" />
        {search && (
          <button onClick={clearSearch} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600')}>
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Advanced Filter Button */}
      <div className="flex h-full flex-shrink-0 items-center gap-1">
        <Button size="icon-md" variant="ghost" className="relative flex h-9 w-9 items-center justify-center border md:h-10 md:w-10" onClick={handleOpenAdvanceSearch}>
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
              <Button size="sm" variant="outline" className={cn('h-9 w-9 p-0 md:h-8 md:w-8', dir === 'rtl' ? 'rounded-r-none border-r-0' : 'rounded-l-none border-l-0')} onClick={onClearAdvanceSearch}>
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
        size="icon-md"
        onClick={handleManualRefresh}
        variant="ghost"
        className={cn('relative flex h-9 w-9 items-center justify-center border transition-all duration-200 md:h-10 md:w-10', isFetching && 'opacity-70')}
        aria-label={t('autoRefresh.refreshNow')}
        title={t('autoRefresh.refreshNow')}
      >
        <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
      </Button>
    </div>
  )
}

interface NodePaginationControlsProps {
  currentPage: number
  totalPages: number
  isLoading: boolean
  onPageChange: (page: number) => void
}

export const NodePaginationControls = ({
                                         currentPage,
                                         totalPages,
                                         isLoading,
                                         onPageChange
                                       }: NodePaginationControlsProps) => {
  const dir = useDirDetection()

  const getPaginationRange = (currentPage: number, totalPages: number) => {
    const delta = 2
    const range = []

    if (totalPages <= 5) {
      for (let i = 0; i < totalPages; i++) {
        range.push(i)
      }
      return range
    }

    range.push(0)

    let start = Math.max(1, currentPage - delta)
    let end = Math.min(totalPages - 2, currentPage + delta)

    if (currentPage - delta <= 1) {
      end = Math.min(totalPages - 2, start + 2 * delta)
    }
    if (currentPage + delta >= totalPages - 2) {
      start = Math.max(1, totalPages - 3 - 2 * delta)
    }

    if (start > 1) {
      range.push(-1)
    }

    for (let i = start; i <= end; i++) {
      range.push(i)
    }

    if (end < totalPages - 2) {
      range.push(-1)
    }

    if (totalPages > 1) {
      range.push(totalPages - 1)
    }

    return range
  }

  const paginationRange = getPaginationRange(currentPage, totalPages)

  return (
      <div className="mt-4 flex flex-col-reverse items-center justify-between gap-4 md:flex-row">
        <Pagination dir="ltr" className={`${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
          <PaginationContent
              className={cn('w-full justify-center overflow-x-auto', dir === 'rtl' ? 'md:justify-start' : 'md:justify-end')}>
            <PaginationItem>
              <PaginationPrevious onClick={() => onPageChange(currentPage - 1)}
                                  disabled={currentPage === 0 || isLoading}/>
            </PaginationItem>
            {paginationRange.map((pageNumber, i) =>
                pageNumber === -1 ? (
                    <PaginationItem key={`ellipsis-${i}`}>
                      <PaginationEllipsis/>
                    </PaginationItem>
                ) : (
                    <PaginationItem key={pageNumber}>
                      <PaginationLink
                          isActive={currentPage === pageNumber}
                          onClick={() => onPageChange(pageNumber as number)}
                          disabled={isLoading}
                          className={isLoading && currentPage === pageNumber ? 'opacity-70' : ''}
                      >
                        {isLoading && currentPage === pageNumber ? (
                            <div className="flex items-center">
                              <LoaderCircle className="mr-1 h-3 w-3 animate-spin"/>
                              {(pageNumber as number) + 1}
                            </div>
                        ) : (
                            (pageNumber as number) + 1
                        )}
                      </PaginationLink>
                    </PaginationItem>
                ),
            )}
            <PaginationItem>
              <PaginationNext onClick={() => onPageChange(currentPage + 1)}
                              disabled={currentPage === totalPages - 1 || totalPages === 0 || isLoading}/>
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      </div>
  )
}
