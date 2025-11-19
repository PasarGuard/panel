import { Input } from '@/components/ui/input'
import { Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/pagination'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { debounce } from 'es-toolkit'
import { SearchIcon, X, RefreshCw } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { RefetchOptions } from '@tanstack/react-query'
import { LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface NodeFiltersProps {
    filters: {
        search?: string
        limit: number
        offset: number
    }
    onFilterChange: (filters: Partial<NodeFiltersProps['filters']>) => void
    refetch?: (options?: RefetchOptions) => Promise<unknown>
    isFetching?: boolean
}

export const NodeFilters = ({ filters, onFilterChange, refetch, isFetching }: NodeFiltersProps) => {
    const { t } = useTranslation()
    const dir = useDirDetection()
    const [search, setSearch] = useState(filters.search || '')

    const onFilterChangeRef = useRef(onFilterChange)
    onFilterChangeRef.current = onFilterChange

    const debouncedFilterChangeRef = useRef(
        debounce((value: string) => {
            onFilterChangeRef.current({
                search: value || undefined,
                offset: 0,
            })
        }, 300),
    )

    useEffect(() => {
        return () => {
            debouncedFilterChangeRef.current.cancel()
        }
    }, [])

    const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value
        setSearch(value)
        debouncedFilterChangeRef.current(value)
    }

    const clearSearch = () => {
        setSearch('')
        debouncedFilterChangeRef.current.cancel()
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

    return (
        <div dir={dir} className="flex items-center gap-2 py-4 md:gap-4">
            <div className="relative w-full md:w-[calc(100%/3-10px)] flex" dir={dir}>
                <SearchIcon
                    className={cn('absolute', dir === 'rtl' ? 'right-2' : 'left-2', 'top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground')}/>
                <Input
                    placeholder={t('search')}
                    value={search}
                    onChange={handleSearchChange}
                    className={cn('pl-8 pr-10', dir === 'rtl' && 'pr-8 pl-10')}
                />
                {search && (
                    <button
                        onClick={clearSearch}
                        className={cn('absolute', dir === 'rtl' ? 'left-2' : 'right-2', 'top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground')}
                    >
                        <X className="h-4 w-4"/>
                    </button>
                )}
            </div>
            <Button size="icon-md"
                    onClick={handleManualRefresh}
                    variant="ghost"
                    className={cn(
                        'relative flex h-9 w-9 items-center justify-center border transition-all duration-200 md:h-10 md:w-10',
                        isFetching && 'opacity-70',
                    )}
                    aria-label={t('autoRefresh.refreshNow')}
                    title={t('autoRefresh.refreshNow')}
            >
                <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')}/>
            </Button>
        </div>
    )
}

interface NodePaginationControlsProps {
    currentPage: number
    totalPages: number
    totalNodes: number
    isLoading: boolean
    onPageChange: (page: number) => void
}

export const NodePaginationControls = ({ currentPage, totalPages, totalNodes, isLoading, onPageChange }: NodePaginationControlsProps) => {
    const { t } = useTranslation()
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
    const startItem = totalNodes === 0 ? 0 : currentPage * 15 + 1
    const endItem = Math.min((currentPage + 1) * 15, totalNodes)

    return (
        <div className="mt-4 flex flex-col-reverse items-center justify-between gap-4 md:flex-row">
            <div className="text-sm text-muted-foreground">
                {t('showing')} {startItem}-{endItem} {t('of')} {totalNodes}
            </div>

            <Pagination dir="ltr" className={`${dir === 'rtl' ? 'flex-row-reverse' : ''}`}>
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
