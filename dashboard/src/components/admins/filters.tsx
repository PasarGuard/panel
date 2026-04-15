import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/pagination'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { debounce } from 'es-toolkit'
import { ArrowUpDown, Calendar, ChartPie, ChevronDown, RefreshCw, SearchIcon, User, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoaderCircle } from 'lucide-react'

const sortSections = [
  {
    key: 'username',
    icon: User,
    label: 'username',
    asc: 'username',
    desc: '-username',
    ascHintKey: 'sort.hints.az',
    descHintKey: 'sort.hints.za',
  },
  {
    key: 'createdAt',
    icon: Calendar,
    label: 'createdAt',
    asc: 'created_at',
    desc: '-created_at',
    ascHintKey: 'sort.hints.oldest',
    descHintKey: 'sort.hints.newest',
  },
  {
    key: 'usage',
    icon: ChartPie,
    label: 'dataUsage',
    asc: 'used_traffic',
    desc: '-used_traffic',
    ascHintKey: 'sort.hints.lowToHigh',
    descHintKey: 'sort.hints.highToLow',
  },
] as const

interface BaseFilters {
  sort?: string
  username?: string | null
  limit?: number
  offset?: number
}

interface FiltersProps<T extends BaseFilters> {
  filters: T
  onFilterChange: (filters: Partial<T>) => void
  handleSort?: (column: string, fromDropdown?: boolean) => void
  refetch?: () => Promise<unknown>
  totalItems?: number
}

export function Filters<T extends BaseFilters>({ filters, onFilterChange, handleSort, refetch }: FiltersProps<T>) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [search, setSearch] = useState(filters.username || '')
  const onFilterChangeRef = useRef(onFilterChange)

  // Keep the ref in sync with the prop
  onFilterChangeRef.current = onFilterChange

  // Debounced search function
  const setSearchField = useCallback(
    debounce((value: string) => {
      onFilterChangeRef.current({
        username: value || undefined,
        offset: 0, // Reset to first page when search is updated
      } as Partial<T>)
    }, 300),
    [],
  )

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      setSearchField.cancel()
    }
  }, [setSearchField])

  // Handle input change
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value)
    setSearchField(e.target.value)
  }

  // Clear search field
  const clearSearch = () => {
    setSearch('')
    setSearchField.cancel()
    onFilterChangeRef.current({
      username: undefined,
      offset: 0,
    } as Partial<T>)
  }

  const getSortState = (section: (typeof sortSections)[number]) => {
    if (filters.sort === section.desc) return 'desc' as const
    if (filters.sort === section.asc) return 'asc' as const
    return 'none' as const
  }

  const handleCompactSort = (section: (typeof sortSections)[number]) => {
    if (!handleSort) return

    const state = getSortState(section)
    const nextSort = state === 'none' ? section.desc : section.asc
    handleSort(nextSort, true)
  }

  const handleRefreshClick = async () => {
    if (refetch) {
      await refetch()
    }
  }

  return (
    <div dir={dir} className="flex items-center gap-2 py-4 md:gap-4">
      {/* Search Input */}
      <div className="relative min-w-0 flex-1 md:w-[calc(100%/3-10px)] md:flex-none">
        <SearchIcon className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 text-input-placeholder')} />
        <Input placeholder={t('search')} value={search} onChange={handleSearchChange} className="pl-8 pr-10" />
        {search && (
          <button type="button" onClick={clearSearch} className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600')}>
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {handleSort && (
        <div className="flex h-full flex-shrink-0 items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                size="icon-md"
                variant="ghost"
                className="relative flex h-9 w-9 items-center justify-center border md:h-10 md:w-10"
                aria-label={t('sortOptions', { defaultValue: 'Sort Options' })}
              >
                <ArrowUpDown className="h-4 w-4" />
                {filters.sort && filters.sort !== '-created_at' && <div className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-primary" />}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52 max-h-72 overflow-y-auto">
              <DropdownMenuLabel className="px-2 py-1 text-[10px] text-muted-foreground">
                {t('sortOptions', { defaultValue: 'Sort Options' })}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {sortSections.map(section => {
                const state = getSortState(section)
                return (
                  <DropdownMenuItem
                    key={section.key}
                    onClick={() => handleCompactSort(section)}
                    className={cn('flex items-center gap-1.5 px-2 py-1.5 text-[11px]', state !== 'none' && 'bg-accent')}
                  >
                    <section.icon className="h-3 w-3 text-muted-foreground" />
                    <span className="truncate">{t(section.label)}</span>
                    {state !== 'none' && (
                      <>
                        <span className="ml-auto text-[10px] text-muted-foreground">
                          {t(state === 'desc' ? section.descHintKey : section.ascHintKey)}
                        </span>
                        <ChevronDown className={cn('h-2.5 w-2.5 flex-shrink-0', state === 'asc' && 'rotate-180')} />
                      </>
                    )}
                  </DropdownMenuItem>
                )
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {/* Refresh Button */}
      <div className="flex h-full flex-shrink-0 items-center gap-0">
        <Button type="button" size="icon-md" onClick={handleRefreshClick} variant="ghost" className="flex items-center gap-2 border">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

// Add props interface for PaginationControls
interface PaginationControlsProps {
  currentPage: number
  totalPages: number
  itemsPerPage: number
  totalItems: number
  isLoading: boolean
  onPageChange: (page: number) => void
  onItemsPerPageChange: (value: number) => void
}

// Update PaginationControls to use props
export const PaginationControls = ({ currentPage, totalPages, itemsPerPage, isLoading, onPageChange, onItemsPerPageChange }: PaginationControlsProps) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

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

      <Pagination dir="ltr" className={`md:justify-end ${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
        <PaginationContent className="max-w-[300px] overflow-x-auto sm:max-w-full">
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
