import { FormItem, FormMessage } from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { useGetCoresSimple } from '@/service/api'
import { Check, ChevronDown, Loader2 } from 'lucide-react'
import { useState, useEffect, useRef, useCallback } from 'react'
import { Control, FieldPath, FieldValues, useController } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 20

interface CoresSelectorProps<T extends FieldValues> {
    control: Control<T>
    name: FieldPath<T>
    onCoreChange?: (core: number | null) => void
    placeholder?: string
}

export default function CoresSelector<T extends FieldValues>({ control, name, onCoreChange, placeholder }: CoresSelectorProps<T>) {
    const { t } = useTranslation()
    const dir = useDirDetection()

    const { field } = useController({
        control,
        name,
    })

    // Pagination and search state
    const [offset, setOffset] = useState(0)
    const [cores, setCores] = useState<any[]>([])
    const [hasMore, setHasMore] = useState(true)
    const [isLoading, setIsLoading] = useState(false)
    const [dropdownOpen, setDropdownOpen] = useState(false)
    const listRef = useRef<HTMLDivElement>(null)
    const { debouncedSearch: coreSearch, setSearch: setCoreSearchInput } = useDebouncedSearch('', 300)

    // Handle debounced search side effects
    useEffect(() => {
        setOffset(0)
        setCores([])
        setHasMore(true)
    }, [coreSearch])

    const { data: coresData, isLoading: coresLoading } = useGetCoresSimple(
        { all: true },
        {
        query: {
            staleTime: 5 * 60 * 1000, // 5 minutes
            gcTime: 10 * 60 * 1000, // 10 minutes
            refetchOnWindowFocus: true,
            refetchOnMount: true,
            refetchOnReconnect: true,
        },
        },
    )

    // Update cores when data is fetched
    useEffect(() => {
        if (coresData?.cores) {
            const allCores = coresData.cores
            const filteredCores = coreSearch 
                ? allCores.filter((core: any) => 
                    core.name.toLowerCase().includes(coreSearch.toLowerCase())
                  )
                : allCores
            
            // Simulate pagination
            const paginatedCores = filteredCores.slice(0, offset + PAGE_SIZE)
            setCores(paginatedCores)
            setHasMore(paginatedCores.length < filteredCores.length)
            setIsLoading(false)
        }
    }, [coresData, coreSearch, offset])

    const handleScroll = useCallback(() => {
        if (!listRef.current || isLoading || !hasMore) return
        const { scrollTop, scrollHeight, clientHeight } = listRef.current
        if (scrollHeight - scrollTop - clientHeight < 100) {
            setIsLoading(true)
            setOffset(prev => prev + PAGE_SIZE)
        }
    }, [isLoading, hasMore])

    useEffect(() => {
        const el = listRef.current
        if (!el) return
        el.addEventListener('scroll', handleScroll)
        return () => el.removeEventListener('scroll', handleScroll)
    }, [handleScroll])

    const selectedCoreId = field.value as number | null | undefined

    const handleCoreSelect = (coreId: number | null) => {
        field.onChange(coreId)
        onCoreChange?.(coreId)
        setDropdownOpen(false)
    }

    const selectedCore = coresData?.cores?.find((core: any) => core.id === selectedCoreId)

    if (coresLoading) {
        return (
            <FormItem>
                <div className="relative mb-3 w-full max-w-xs sm:mb-4 sm:max-w-sm lg:max-w-md" dir={dir}>
                    <Skeleton className="h-8 w-full sm:h-9" />
                </div>
                <FormMessage />
            </FormItem>
        )
    }

    return (
        <FormItem>
            <div className="relative mb-3 w-full max-w-xs sm:mb-4 sm:max-w-sm lg:max-w-md" dir={dir}>
                <Popover open={dropdownOpen} onOpenChange={setDropdownOpen}>
                    <PopoverTrigger asChild>
                        <Button 
                            variant="outline" 
                            className={cn(
                                'h-8 w-full justify-between px-2 transition-colors hover:bg-muted/50 sm:h-9 sm:px-3',
                                'min-w-0 text-xs font-medium sm:text-sm'
                            )}
                        >
                            <div className={cn(
                                'flex min-w-0 flex-1 items-center gap-1 sm:gap-2',
                                dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'
                            )}>
                                <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                                    <AvatarFallback className="bg-muted text-xs font-medium">
                                        {selectedCore?.name?.charAt(0).toUpperCase() || 'C'}
                                    </AvatarFallback>
                                </Avatar>
                                <span className="truncate text-xs sm:text-sm">
                                    {selectedCore?.name || placeholder || t('advanceSearch.selectCore', { defaultValue: 'Select Core' })}
                                </span>
                            </div>
                            <ChevronDown className="ml-1 h-3 w-3 flex-shrink-0 text-muted-foreground" />
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent 
                        className="w-64 p-1 sm:w-72 lg:w-80"
                        sideOffset={4} 
                        align={dir === 'rtl' ? 'end' : 'start'}
                    >
                        <Command>
                            <CommandInput 
                                placeholder={placeholder || t('search', { defaultValue: 'Search' })} 
                                onValueChange={setCoreSearchInput}
                                className="mb-1 h-7 text-xs sm:h-8 sm:text-sm" 
                            />
                            <CommandList ref={listRef}>
                                <CommandEmpty>
                                    <div className="py-3 text-center text-xs text-muted-foreground sm:py-4 sm:text-sm">
                                        {t('advanceSearch.noCoresFound', { defaultValue: 'No cores found' })}
                                    </div>
                                </CommandEmpty>

                                {/* "None" option to deselect */}
                                <CommandItem
                                    onSelect={() => handleCoreSelect(null)}
                                    className={cn(
                                        'flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm',
                                        dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'
                                    )}
                                >
                                    <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                                        <AvatarFallback className="bg-primary/10 text-xs font-medium">N</AvatarFallback>
                                    </Avatar>
                                    <span className="flex-1 truncate">{t('none', { defaultValue: 'None' })}</span>
                                    <div className="flex flex-shrink-0 items-center gap-1">
                                        {!selectedCoreId && <Check className="h-3 w-3 text-primary" />}
                                    </div>
                                </CommandItem>

                                {cores.map((core: any) => (
                                    <CommandItem
                                        key={core.id}
                                        onSelect={() => handleCoreSelect(core.id)}
                                        className={cn(
                                            'flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm',
                                            dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'
                                        )}
                                    >
                                        <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                                            <AvatarFallback className="bg-muted text-xs font-medium">
                                                {core.name.charAt(0).toUpperCase()}
                                            </AvatarFallback>
                                        </Avatar>
                                        <span className="flex-1 truncate">{core.name}</span>
                                        <div className="flex flex-shrink-0 items-center gap-1">
                                            {selectedCoreId === core.id && <Check className="h-3 w-3 text-primary" />}
                                        </div>
                                    </CommandItem>
                                ))}

                                {isLoading && (
                                    <div className="flex justify-center py-2">
                                        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                                    </div>
                                )}
                            </CommandList>
                        </Command>
                    </PopoverContent>
                </Popover>
            </div>
            <FormMessage />
        </FormItem>
    )
}
