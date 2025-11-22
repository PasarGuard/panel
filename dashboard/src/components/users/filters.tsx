import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/pagination'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel } from '@/components/ui/dropdown-menu'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { RefreshCw, SearchIcon, Filter, X, ArrowUpDown, User, Calendar, ChartPie, ChevronDown, Check, Clock } from 'lucide-react'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useGetUsers, UserStatus } from '@/service/api'
import { RefetchOptions } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { getUsersAutoRefreshIntervalSeconds, setUsersAutoRefreshIntervalSeconds } from '@/utils/userPreferenceStorage'

// Sort configuration to eliminate duplication
const sortSections = [
  {
    key: 'username',
    icon: User,
    label: 'username',
    items: [
      { value: '-username', label: 'sort.username.desc' },
      { value: 'username', label: 'sort.username.asc' },
    ],
  },
  {
    key: 'expire',
    icon: Calendar,
    label: 'expireDate',
    items: [
      { value: '-expire', label: 'sort.expire.newest' },
      { value: 'expire', label: 'sort.expire.oldest' },
    ],
  },
  {
    key: 'usage',
    icon: ChartPie,
    label: 'dataUsage',
    items: [
      { value: '-used_traffic', label: 'sort.usage.high' },
      { value: 'used_traffic', label: 'sort.usage.low' },
    ],
  },
  {
    key: 'onlineAt',
    icon: Clock,
    label: 'lastOnline',
    items: [
      { value: '-online_at', label: 'sort.online.newest' },
      { value: 'online_at', label: 'sort.online.oldest' },
    ],
  },
] as const

const autoRefreshOptions = [
  { value: 0, labelKey: 'autoRefresh.off' },
  { value: 5, labelKey: 'autoRefresh.5Seconds' },
  { value: 15, labelKey: 'autoRefresh.15Seconds' },
  { value: 30, labelKey: 'autoRefresh.30Seconds' },
  { value: 60, labelKey: 'autoRefresh.1Minute' },
] as const

interface FiltersProps {
  filters: {
    search?: string
    limit?: number
    offset?: number
    sort: string
    status?: UserStatus | null
    load_sub: boolean
    admin?: string[]
    group?: number[]
  }
  onFilterChange: (filters: Partial<FiltersProps['filters']>) => void
  refetch?: (options?: RefetchOptions) => Promise<unknown>
  autoRefetch?: (options?: RefetchOptions) => Promise<unknown>
  advanceSearchOnOpen: (status: boolean) => void
  onClearAdvanceSearch?: () => void
  handleSort?: (column: string, fromDropdown?: boolean) => void
}

export const Filters = ({ filters, onFilterChange, refetch, autoRefetch, advanceSearchOnOpen, onClearAdvanceSearch, handleSort }: FiltersProps) => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number>(() => getUsersAutoRefreshIntervalSeconds())
  const { refetch: queryRefetch, isFetching } = useGetUsers(filters)
  const { search, debouncedSearch, setSearch } = useDebouncedSearch(filters.search || '', 300)
  const prevDebouncedSearchRef = useRef<string | undefined>(filters.search || undefined)
  
  const refetchUsers = useCallback(
    async (showLoading = false, isAutoRefresh = false) => {
      if (showLoading) {
        setIsRefreshing(true)
      }
      try {
        // Use autoRefetch for auto refresh, otherwise use manual refetch
        const refetchFn = isAutoRefresh ? (autoRefetch ?? queryRefetch) : (refetch ?? queryRefetch)
        await refetchFn()
      } finally {
        if (showLoading) {
          setIsRefreshing(false)
        }
      }
    },
    [refetch, autoRefetch, queryRefetch],
  )
  useEffect(() => {
    const persistedValue = getUsersAutoRefreshIntervalSeconds()
    setAutoRefreshInterval(prev => (prev === persistedValue ? prev : persistedValue))
  }, [])
  useEffect(() => {
    if (!autoRefreshInterval) return
    const intervalId = setInterval(() => {
      refetchUsers(true, true) // Show loading spinner on auto refresh, mark as auto refresh
    }, autoRefreshInterval * 1000)
    return () => clearInterval(intervalId)
  }, [autoRefreshInterval, refetchUsers])
  useEffect(() => {
    if (typeof document === 'undefined') return
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && autoRefreshInterval > 0) {
        refetchUsers(true, true) // Show loading spinner on visibility change refresh, mark as auto refresh
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [autoRefreshInterval, refetchUsers])
  const currentAutoRefreshOption = autoRefreshOptions.find(option => option.value === autoRefreshInterval) ?? autoRefreshOptions[0]
  const autoRefreshShortLabel =
    autoRefreshInterval === 0
      ? t('autoRefresh.offShort')
      : autoRefreshInterval < 60
        ? t('autoRefresh.shortSeconds', { count: autoRefreshInterval })
        : t('autoRefresh.shortMinutes', { count: Math.round(autoRefreshInterval / 60) })
  const currentAutoRefreshDescription = t(currentAutoRefreshOption.labelKey)

  // Update filters when debounced search changes
  useEffect(() => {
    // Only update if search actually changed to avoid resetting page on initial load
    if (debouncedSearch !== prevDebouncedSearchRef.current) {
      prevDebouncedSearchRef.current = debouncedSearch
      onFilterChange({
        search: debouncedSearch || '',
        offset: 0,
      })
    }
  }, [debouncedSearch, onFilterChange])

  // Handle input change
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value)
  }

  // Clear search field
  const clearSearch = () => {
    setSearch('')
    onFilterChange({
      search: '',
      offset: 0,
    })
  }

  // Handle refresh with loading state
  const handleRefreshClick = async () => {
    await refetchUsers(true, false) // Show loading spinner on manual refresh, mark as manual refresh
  }

  const handleAutoRefreshChange = (seconds: number) => {
    setUsersAutoRefreshIntervalSeconds(seconds)
    setAutoRefreshInterval(seconds)
  }

  const handleOpenAdvanceSearch = () => {
    advanceSearchOnOpen(true)
  }

  // Check if any advance search filters are active
  // Check the actual filters prop instead of form values, as form gets reset when modal closes
  const hasActiveAdvanceFilters = () => {
    const admin = filters.admin
    const group = filters.group
    const status = filters.status
    return (admin && admin.length > 0) || (group && group.length > 0) || (status !== undefined && status !== null)
  }

  // Get the count of active advance filters
  // Check the actual filters prop instead of form values, as form gets reset when modal closes
  const getActiveFiltersCount = () => {
    const admin = filters.admin
    const group = filters.group
    const status = filters.status
    let count = 0
    if (admin && admin.length > 0) count++
    if (group && group.length > 0) count++
    if (status !== undefined && status !== null) count++
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
      {/* Sort Button */}
      {handleSort && (
        <div className="flex h-full flex-shrink-0 items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                size="icon-md"
                variant="ghost"
                className="relative flex h-9 w-9 items-center justify-center border md:h-10 md:w-10"
                aria-label={t('sortOptions', { defaultValue: 'Sort Options' })}
              >
                <ArrowUpDown className="h-4 w-4" />
                {filters.sort && filters.sort !== '-created_at' && <div className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-primary" />}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              {sortSections.map((section, sectionIndex) => (
                <div key={section.key}>
                  {/* Section Label */}
                  <DropdownMenuLabel className="flex items-center gap-1 px-1.5 py-1 text-[10px] text-muted-foreground">
                    <section.icon className="h-2.5 w-2.5" />
                    <span className="text-[10px]">{t(section.label)}</span>
                  </DropdownMenuLabel>

                  {/* Section Items */}
                  {section.items.map(item => (
                    <DropdownMenuItem
                      key={item.value}
                      onClick={() => handleSort && handleSort(item.value, true)}
                      className={`whitespace-nowrap px-1.5 py-1 text-[11px] ${filters.sort === item.value ? 'bg-accent' : ''}`}
                    >
                      <span className="truncate">{t(item.label)}</span>
                      {filters.sort === item.value && <ChevronDown className={`ml-auto h-2.5 w-2.5 flex-shrink-0 ${item.value.startsWith('-') ? '' : 'rotate-180'}`} />}
                    </DropdownMenuItem>
                  ))}

                  {/* Add separator except for last section */}
                  {sectionIndex < sortSections.length - 1 && <DropdownMenuSeparator />}
                </div>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
      {/* Refresh Button */}
      <div className="flex h-full flex-shrink-0 items-center gap-0">
        <Button
          size="icon-md"
          onClick={handleRefreshClick}
          variant="ghost"
          className={cn(
            'relative flex h-9 w-9 items-center justify-center border transition-all duration-200 md:h-10 md:w-10',
            dir === 'rtl' ? 'rounded-l-none border-l-0' : 'rounded-r-none',
            (isRefreshing || isFetching) && 'opacity-70',
          )}
          aria-label={t('autoRefresh.refreshNow')}
          title={t('autoRefresh.refreshNow')}
          disabled={isRefreshing || isFetching}
        >
          <RefreshCw className="h-4 w-4" />
          <div className="absolute -right-1 -top-1 flex items-center justify-center">
            {isRefreshing || isFetching ? (
              <div className="flex h-3 w-3 items-center justify-center rounded-full bg-primary transition-all duration-200 ease-in-out">
                <LoaderCircle className="h-2 w-2 animate-spin text-primary-foreground" />
              </div>
            ) : (
              autoRefreshInterval > 0 && <div className="h-2 w-2 rounded-full bg-primary transition-all duration-200 ease-in-out" />
            )}
          </div>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="icon-md"
              variant="ghost"
              className={cn('relative flex h-9 w-9 items-center justify-center border md:h-10 md:w-10', dir === 'rtl' ? 'rounded-r-none' : 'rounded-l-none border-l-0')}
              aria-label={t('autoRefresh.label')}
              title={`${t('autoRefresh.label')} (${autoRefreshShortLabel})`}
            >
              <ChevronDown className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel className="flex flex-col gap-0.5 px-1.5 py-1 text-[10px] text-muted-foreground">
              <span>{t('autoRefresh.label')}</span>
              <span className="text-[9px]">{t('autoRefresh.currentSelection', { value: currentAutoRefreshDescription })}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => void handleRefreshClick()}
              disabled={isRefreshing || isFetching}
              className={cn('flex items-center gap-1.5 px-1.5 py-1 text-[11px] transition-opacity duration-200', (isRefreshing || isFetching) && 'opacity-70')}
            >
              <RefreshCw className="h-2.5 w-2.5 flex-shrink-0" />
              <span className="truncate">{t('autoRefresh.refreshNow')}</span>
              {(isRefreshing || isFetching) && <LoaderCircle className="ml-auto h-2.5 w-2.5 animate-spin text-primary" />}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {autoRefreshOptions.map(option => {
              const isActive = option.value === autoRefreshInterval
              return (
                <DropdownMenuItem
                  key={option.value}
                  onSelect={() => handleAutoRefreshChange(option.value)}
                  className={cn('flex items-center gap-1.5 whitespace-nowrap px-1.5 py-1 text-[11px]', isActive && 'bg-accent')}
                >
                  <span>{t(option.labelKey)}</span>
                  {isActive && <Check className="ml-auto h-2.5 w-2.5 flex-shrink-0" />}
                </DropdownMenuItem>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

interface PaginationControlsProps {
  currentPage: number
  totalPages: number
  itemsPerPage: number
  totalUsers: number
  isLoading: boolean
  onPageChange: (page: number) => void
  onItemsPerPageChange: (value: number) => void
}

export const PaginationControls = ({ currentPage, totalPages, itemsPerPage, isLoading, onPageChange, onItemsPerPageChange }: PaginationControlsProps) => {
  const { t } = useTranslation()

  const getPaginationRange = (currentPage: number, totalPages: number) => {
    const delta = 2 // Number of pages to show on each side of current page
    const range = []

    // Handle small number of pages
    if (totalPages <= 5) {
      for (let i = 0; i < totalPages; i++) {
        range.push(i)
      }
      return range
    }

    // Always include first and last page
    range.push(0)

    // Calculate start and end of range
    let start = Math.max(1, currentPage - delta)
    let end = Math.min(totalPages - 2, currentPage + delta)

    // Adjust range if current page is near start or end
    if (currentPage - delta <= 1) {
      end = Math.min(totalPages - 2, start + 2 * delta)
    }
    if (currentPage + delta >= totalPages - 2) {
      start = Math.max(1, totalPages - 3 - 2 * delta)
    }

    // Add ellipsis if needed
    if (start > 1) {
      range.push(-1) // -1 represents ellipsis
    }

    // Add pages in range
    for (let i = start; i <= end; i++) {
      range.push(i)
    }

    // Add ellipsis if needed
    if (end < totalPages - 2) {
      range.push(-1) // -1 represents ellipsis
    }

    // Add last page
    if (totalPages > 1) {
      range.push(totalPages - 1)
    }

    return range
  }

  const paginationRange = getPaginationRange(currentPage, totalPages)
  const dir = useDirDetection()
  return (
    <div className="mt-4 flex flex-col-reverse items-center justify-between gap-4 md:flex-row">
      <div className="flex items-center gap-2">
        <Select value={itemsPerPage.toString()} onValueChange={value => onItemsPerPageChange(parseInt(value, 10))} disabled={isLoading}>
          <SelectTrigger className="w-[70px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="10">10</SelectItem>
              <SelectItem value="20">20</SelectItem>
              <SelectItem value="30">30</SelectItem>
              <SelectItem value="40">40</SelectItem>
              <SelectItem value="50">50</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <span className="whitespace-nowrap text-sm text-muted-foreground">{t('itemsPerPage')}</span>
      </div>

      <Pagination dir="ltr" className={`ic md:justify-end ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
        <PaginationContent className={cn('w-full justify-center overflow-x-auto', dir === 'rtl' ? 'md:justify-start' : 'md:justify-end')}>
          <PaginationItem>
            <PaginationPrevious onClick={() => onPageChange(currentPage - 1)} disabled={currentPage === 0 || isLoading} />
          </PaginationItem>
          {paginationRange.map((pageNumber, i) =>
            pageNumber === -1 ? (
              <PaginationItem key={`ellipsis-${i}`}>
                <PaginationEllipsis />
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
                      <LoaderCircle className="mr-1 h-3 w-3 animate-spin" />
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
            <PaginationNext onClick={() => onPageChange(currentPage + 1)} disabled={currentPage === totalPages - 1 || totalPages === 0 || isLoading} />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  )
}
