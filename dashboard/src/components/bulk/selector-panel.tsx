import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { TFunction } from 'i18next'
import { Search, Check } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { memo } from 'react'

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
  const handleSelectAll = () => setSelected(items.map(item => (typeof item[itemValueKey] === 'number' ? (item[itemValueKey] as number) : -1)).filter(id => id !== -1))
  const handleDeselectAll = () => setSelected([])
  const filteredItems = items.filter(item => {
    const value =
      searchKey === 'name' && 'name' in item && typeof item.name === 'string' ? item.name : searchKey === 'username' && 'username' in item && typeof item.username === 'string' ? item.username : ''
    return value.toLowerCase().includes(search.toLowerCase())
  })

  const handleItemToggle = (id: number) => {
    if (selected.includes(id)) {
      setSelected(selected.filter(selectedId => selectedId !== id))
    } else {
      setSelected([...selected, id])
    }
  }

  const allFilteredSelected = filteredItems.length > 0 && filteredItems.every(item => {
    const id = typeof item[itemValueKey] === 'number' ? (item[itemValueKey] as number) : undefined
    return id !== undefined && selected.includes(id)
  })

  return (
    <Card className={cn("flex-1 flex flex-col h-full min-w-[200px] sm:min-w-[240px] overflow-hidden", hasError && "border-destructive")}>
      <CardHeader className="pb-3 sm:pb-4 flex-shrink-0 px-3 sm:px-6 pt-3 sm:pt-6 overflow-hidden">
        <div className="flex items-center justify-between mb-2 sm:mb-2.5 gap-2 sm:gap-3 min-w-0">
          <CardTitle className="flex items-center gap-1.5 sm:gap-2 text-sm sm:text-base font-medium min-w-0 flex-1 overflow-hidden">
            <Icon className="h-4 w-4 sm:h-4 sm:w-4 text-muted-foreground flex-shrink-0" />
            <span className="truncate block min-w-0" title={title}>{title}</span>
            {isRequired && <span className="text-destructive flex-shrink-0 ml-0.5">*</span>}
          </CardTitle>
          <Badge variant={selected.length > 0 ? "default" : "secondary"} className="text-xs sm:text-sm flex-shrink-0 min-w-[2.5rem] sm:min-w-[2.75rem] text-center tabular-nums px-2 py-0.5">
            {selected.length}
          </Badge>
        </div>
        <div className="min-h-[1.25rem] sm:min-h-[1.5rem] mb-2 sm:mb-3 overflow-hidden">
          {description && (
            <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed break-words overflow-hidden">{description}</p>
          )}
          {hasError && !description && (
            <p className="text-xs sm:text-sm text-destructive break-words overflow-hidden">{t('bulk.required', { defaultValue: 'This field is required' })}</p>
          )}
        </div>
        <div className="flex items-center gap-2 sm:gap-2.5 overflow-hidden">
          <Button
            size="sm"
            variant={allFilteredSelected ? 'default' : 'outline'}
            className="h-8 sm:h-9 text-xs sm:text-sm flex-1 sm:flex-initial px-2 sm:px-4 min-w-0 overflow-hidden"
            onClick={handleSelectAll}
          >
            <Check className={cn('h-3.5 w-3.5 sm:h-4 sm:w-4 flex-shrink-0', allFilteredSelected && 'mr-1 sm:mr-1.5')} />
            <span className="hidden sm:inline truncate">{selectAllLabel}</span>
            <span className="sm:hidden truncate">{t('selectAll', { defaultValue: 'All' })}</span>
          </Button>
          <Button size="sm" variant="outline" className="h-8 sm:h-9 text-xs sm:text-sm flex-1 sm:flex-initial px-2 sm:px-4 min-w-0 overflow-hidden" onClick={handleDeselectAll}>
            <span className="hidden sm:inline truncate">{deselectAllLabel}</span>
            <span className="sm:hidden truncate">{t('deselectAll', { defaultValue: 'None' })}</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-2.5 sm:space-y-3 flex-1 flex flex-col min-h-0 px-3 sm:px-6 pb-3 sm:pb-6 overflow-hidden">
        {isLoading ? (
          <>
            <div className="relative flex-shrink-0" dir="ltr">
              <Search className="absolute left-3 sm:left-3 top-1/2 h-4 w-4 sm:h-4 sm:w-4 -translate-y-1/2 text-muted-foreground" />
              <Skeleton className="h-9 sm:h-10 w-full" />
            </div>

            <div className="flex-1 min-h-0 space-y-1.5 sm:space-y-2 overflow-y-auto max-h-[220px] sm:max-h-[280px] scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent" dir="ltr">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="flex items-center gap-2 sm:gap-2.5 rounded-md px-3 py-2 sm:px-3.5 sm:py-2.5 min-w-0">
                  <Skeleton className="h-4 w-4 rounded-full sm:h-4 sm:w-4 flex-shrink-0" />
                  <Skeleton className="h-4 flex-1 min-w-0" />
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <div className="relative flex-shrink-0" dir="ltr">
              <Search className="absolute left-3 sm:left-3 top-1/2 h-4 w-4 sm:h-4 sm:w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder={searchPlaceholder} value={search} onChange={e => setSearch(e.target.value)} className="h-9 sm:h-10 pl-10 sm:pl-10 text-sm sm:text-sm w-full" />
            </div>

            <div className="flex-1 min-h-0 space-y-1.5 sm:space-y-2 overflow-y-auto max-h-[220px] sm:max-h-[280px] scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent" dir="ltr">
              {filteredItems.map(item => {
                const id = typeof item[itemValueKey] === 'number' ? (item[itemValueKey] as number) : undefined
                let label = ''
                if (itemLabelKey === 'name' && 'name' in item && typeof item.name === 'string') label = item.name
                if (itemLabelKey === 'username' && 'username' in item && typeof item.username === 'string') label = item.username
                if (id === undefined) return null

                const isSelected = selected.includes(id)

                return (
                  <div
                    key={id}
                    onClick={() => handleItemToggle(id)}
                    className={cn(
                      'group flex cursor-pointer items-center gap-2 sm:gap-2.5 rounded-md border px-3 sm:px-3.5 py-2 sm:py-2.5 transition-colors hover:bg-accent active:bg-accent/80 min-w-0 overflow-hidden',
                      isSelected && 'border-primary bg-primary/5',
                    )}
                  >
                    <div className={cn(
                      'flex h-4 w-4 sm:h-4 sm:w-4 items-center justify-center rounded border transition-colors flex-shrink-0',
                      isSelected ? 'border-primary bg-primary' : 'border-muted-foreground/40 group-hover:border-primary/60',
                    )}>
                      {isSelected && <Check className="h-3 w-3 sm:h-3 sm:w-3 text-primary-foreground" />}
                    </div>
                    <span className="flex-1 truncate text-sm sm:text-sm min-w-0 block" title={label}>{label}</span>
                  </div>
                )
              })}
              {filteredItems.length === 0 && (
                <div className="flex flex-col items-center justify-center py-6 sm:py-8 text-center">
                  <Search className="h-4 w-4 sm:h-5 sm:w-5 text-muted-foreground mb-2 sm:mb-2.5" />
                  <p className="text-sm sm:text-sm text-muted-foreground">{t('noResults', { defaultValue: 'No results found.' })}</p>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
})
