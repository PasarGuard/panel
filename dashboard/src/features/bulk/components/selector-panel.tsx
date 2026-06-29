import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { TFunction } from 'i18next'
import { Search, Check } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { memo, useCallback, useDeferredValue, useMemo } from 'react'

// Types for selector items
interface GroupResponse {
  id: number
  name: string
}
interface UserResponse {
  id: number
  username: string
}
interface AdminDetails {
  id: number
  username: string
}

type SelectorItem = GroupResponse | UserResponse | AdminDetails

type SelectorPanelProps = {
  icon: LucideIcon
  title: string
  items: SelectorItem[]
  selected: number[]
  setSelected: (ids: number[]) => void
  search: string
  setSearch: (s: string) => void
  searchPlaceholder: string
  selectAllLabel: string
  deselectAllLabel: string
  itemLabelKey: 'name' | 'username'
  itemValueKey: 'id'
  searchKey: 'name' | 'username'
  t: TFunction
  isLoading?: boolean
  description?: string
  isRequired?: boolean
  hasError?: boolean
}

export const SelectorPanel = memo(function SelectorPanel({
  icon: Icon,
  title,
  items,
  selected,
  setSelected,
  search,
  setSearch,
  searchPlaceholder,
  selectAllLabel,
  deselectAllLabel,
  itemLabelKey,
  itemValueKey,
  searchKey,
  t,
  isLoading = false,
  description,
  isRequired = false,
  hasError = false,
}: SelectorPanelProps) {
  const deferredSearch = useDeferredValue(search)
  const normalizedSearch = deferredSearch.trim().toLowerCase()

  const allItemIds = useMemo(() => items.map(item => (typeof item[itemValueKey] === 'number' ? (item[itemValueKey] as number) : -1)).filter(id => id !== -1), [items, itemValueKey])

  const selectedSet = useMemo(() => new Set(selected), [selected])

  const handleSelectAll = useCallback(() => setSelected(allItemIds), [allItemIds, setSelected])
  const handleDeselectAll = useCallback(() => setSelected([]), [setSelected])

  const filteredItems = useMemo(() => {
    if (!normalizedSearch) return items

    return items.filter(item => {
      const rawValue = searchKey === 'name' && 'name' in item ? item.name : searchKey === 'username' && 'username' in item ? item.username : ''

      if (typeof rawValue !== 'string') return false
      return rawValue.toLowerCase().includes(normalizedSearch)
    })
  }, [items, normalizedSearch, searchKey])

  const handleItemToggle = useCallback(
    (id: number) => {
      if (selected.includes(id)) {
        setSelected(selected.filter(selectedId => selectedId !== id))
      } else {
        setSelected([...selected, id])
      }
    },
    [selected, setSelected],
  )

  const allFilteredSelected =
    filteredItems.length > 0 &&
    filteredItems.every(item => {
      const id = typeof item[itemValueKey] === 'number' ? (item[itemValueKey] as number) : undefined
      return id !== undefined && selectedSet.has(id)
    })

  return (
    <Card className={cn('flex h-full min-w-[200px] flex-1 flex-col overflow-hidden sm:min-w-[240px]', hasError && 'border-destructive')}>
      <CardHeader className="flex-shrink-0 overflow-hidden px-3 pt-3 pb-3 sm:px-6 sm:pt-6 sm:pb-4">
        <div className="mb-2 flex min-w-0 items-center justify-between gap-2 sm:mb-2.5 sm:gap-3">
          <CardTitle className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden text-sm font-medium sm:gap-2 sm:text-base">
            <Icon className="text-muted-foreground h-4 w-4 flex-shrink-0 sm:h-4 sm:w-4" />
            <span className="block min-w-0 truncate" title={title}>
              {title}
            </span>
            {isRequired && <span className="text-destructive ml-0.5 flex-shrink-0">*</span>}
          </CardTitle>
          <Badge dir="ltr" variant={selected.length > 0 ? 'default' : 'secondary'} className="min-w-[2.5rem] flex-shrink-0 px-2 py-0.5 text-center text-xs tabular-nums sm:min-w-[2.75rem] sm:text-sm">
            {selected.length}
          </Badge>
        </div>
        <div className="mb-2 min-h-[1.25rem] overflow-hidden sm:mb-3 sm:min-h-[1.5rem]">
          {description && <p className="text-muted-foreground overflow-hidden text-xs leading-relaxed break-words sm:text-sm">{description}</p>}
          {hasError && !description && <p className="text-destructive overflow-hidden text-xs break-words sm:text-sm">{t('bulk.required', { defaultValue: 'This field is required' })}</p>}
        </div>
        <div className="flex items-center gap-2 overflow-hidden sm:gap-2.5">
          <Button
            size="sm"
            variant={allFilteredSelected ? 'default' : 'outline'}
            className="h-8 min-w-0 flex-1 overflow-hidden px-2 text-xs sm:h-9 sm:flex-initial sm:px-4 sm:text-sm"
            onClick={handleSelectAll}
          >
            <Check className={cn('h-3.5 w-3.5 flex-shrink-0 sm:h-4 sm:w-4', allFilteredSelected && 'mr-1 sm:mr-1.5')} />
            <span className="hidden truncate sm:inline">{selectAllLabel}</span>
            <span className="truncate sm:hidden">{t('selectAll', { defaultValue: 'All' })}</span>
          </Button>
          <Button size="sm" variant="outline" className="h-8 min-w-0 flex-1 overflow-hidden px-2 text-xs sm:h-9 sm:flex-initial sm:px-4 sm:text-sm" onClick={handleDeselectAll}>
            <span className="hidden truncate sm:inline">{deselectAllLabel}</span>
            <span className="truncate sm:hidden">{t('deselectAll', { defaultValue: 'None' })}</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col space-y-2.5 overflow-hidden px-3 pb-3 sm:space-y-3 sm:px-6 sm:pb-6">
        {isLoading ? (
          <>
            <div className="relative flex-shrink-0" dir="ltr">
              <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 sm:left-3 sm:h-4 sm:w-4" />
              <Skeleton className="h-9 w-full sm:h-10" />
            </div>

            <div className="scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent max-h-[220px] min-h-0 flex-1 space-y-1.5 overflow-y-auto sm:max-h-[280px] sm:space-y-2" dir="ltr">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="flex min-w-0 items-center gap-2 rounded-md px-3 py-2 sm:gap-2.5 sm:px-3.5 sm:py-2.5">
                  <Skeleton className="h-4 w-4 flex-shrink-0 rounded-full sm:h-4 sm:w-4" />
                  <Skeleton className="h-4 min-w-0 flex-1" />
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <div className="relative mt-1.5 flex-shrink-0" dir="ltr">
              <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 sm:left-3 sm:h-4 sm:w-4" />
              <Input placeholder={searchPlaceholder} value={search} onChange={e => setSearch(e.target.value)} className="h-9 w-full pl-10 text-sm sm:h-10 sm:pl-10 sm:text-sm" />
            </div>

            <div className="scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent max-h-[220px] min-h-0 flex-1 space-y-1.5 overflow-y-auto sm:max-h-[280px] sm:space-y-2" dir="ltr">
              {filteredItems.map(item => {
                const id = typeof item[itemValueKey] === 'number' ? (item[itemValueKey] as number) : undefined
                let label = ''
                if (itemLabelKey === 'name' && 'name' in item && typeof item.name === 'string') label = item.name
                if (itemLabelKey === 'username' && 'username' in item && typeof item.username === 'string') label = item.username
                if (id === undefined) return null

                const isSelected = selectedSet.has(id)

                return (
                  <div
                    key={id}
                    onClick={() => handleItemToggle(id)}
                    className={cn(
                      'group hover:bg-accent active:bg-accent/80 flex min-w-0 cursor-pointer items-center gap-2 overflow-hidden rounded-md border px-3 py-2 transition-colors sm:gap-2.5 sm:px-3.5 sm:py-2.5',
                      isSelected && 'border-primary bg-primary/5',
                    )}
                  >
                    <div
                      className={cn(
                        'flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border transition-colors sm:h-4 sm:w-4',
                        isSelected ? 'border-primary bg-primary' : 'border-muted-foreground/40 group-hover:border-primary/60',
                      )}
                    >
                      {isSelected && <Check className="text-primary-foreground h-3 w-3 sm:h-3 sm:w-3" />}
                    </div>
                    <span className="block min-w-0 flex-1 truncate text-sm sm:text-sm" title={label}>
                      {label}
                    </span>
                  </div>
                )
              })}
              {filteredItems.length === 0 && (
                <div className="flex flex-col items-center justify-center py-6 text-center sm:py-8">
                  <Search className="text-muted-foreground mb-2 h-4 w-4 sm:mb-2.5 sm:h-5 sm:w-5" />
                  <p className="text-muted-foreground text-sm sm:text-sm">{t('noResults', { defaultValue: 'No results found.' })}</p>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
})
