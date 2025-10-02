import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { TFunction } from 'i18next'
import { Search } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

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
}

export function SelectorPanel({
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

  return (
    <Card className="min-w-0 flex-1 bg-card">
      {/* Header */}
      <CardHeader className="pb-3 sm:pb-4">
        <div className="mb-2 flex items-center justify-between sm:mb-3">
          <CardTitle className="flex items-center gap-2 text-xs font-medium sm:text-sm">
            <Icon className="h-3 w-3 text-muted-foreground sm:h-4 sm:w-4" />
            {title}
          </CardTitle>
        </div>
        <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center sm:gap-0">
          <Badge variant="secondary" className="w-fit text-xs">
            {t('selectedCount', { count: selected.length, defaultValue: '{{count}} selected' })}
          </Badge>
          <div className="flex items-center gap-1 sm:gap-2">
            <Button size="sm" variant="outline" className="h-6 bg-transparent px-1 text-xs sm:px-2" onClick={handleSelectAll}>
              <span className="hidden sm:inline">{selectAllLabel}</span>
              <span className="sm:hidden">{t('selectAll', { defaultValue: 'All' })}</span>
            </Button>
            <Button size="sm" variant="outline" className="h-6 bg-transparent px-1 text-xs sm:px-2" onClick={handleDeselectAll}>
              <span className="hidden sm:inline">{deselectAllLabel}</span>
              <span className="sm:hidden">{t('deselectAll', { defaultValue: 'None' })}</span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3 sm:space-y-4">
        {/* Search */}
        <div className="relative" dir="ltr">
          <Search className="absolute left-3 top-1/2 h-3 w-3 -translate-y-1/2 transform text-muted-foreground sm:h-4 sm:w-4" />
          <Input placeholder={searchPlaceholder} value={search} onChange={e => setSearch(e.target.value)} className="h-8 bg-background pl-8 text-xs sm:h-9 sm:pl-9 sm:text-sm" />
        </div>

        {/* Items List */}
        <div className="max-h-[150px] space-y-1 overflow-y-auto sm:max-h-[200px]" dir="ltr">
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
                  'flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-accent sm:gap-3 sm:px-3 sm:py-2',
                  isSelected && 'border border-primary bg-accent',
                )}
              >
                <div className="relative">
                  <div className={cn('h-3 w-3 rounded-full border-2 transition-colors sm:h-4 sm:w-4', isSelected ? 'border-primary bg-primary' : 'border-muted-foreground/30 bg-background')}>
                    {isSelected && <div className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 transform rounded-full bg-primary-foreground sm:h-2 sm:w-2" />}
                  </div>
                </div>
                <span className="flex-1 truncate text-xs sm:text-sm">{label}</span>
              </div>
            )
          })}
          {filteredItems.length === 0 && <div className="py-4 text-center text-xs text-muted-foreground sm:py-8 sm:text-sm">{t('noResults', { defaultValue: 'No results found.' })}</div>}
        </div>
      </CardContent>
    </Card>
  )
}
