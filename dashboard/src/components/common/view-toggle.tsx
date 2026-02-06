import { LayoutGrid, List } from 'lucide-react'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

export type ViewMode = 'grid' | 'list'

interface ViewToggleProps {
  value: ViewMode
  onChange: (value: ViewMode) => void
  className?: string
}

export default function ViewToggle({ value, onChange, className }: ViewToggleProps) {
  const { t } = useTranslation()
  const viewModeLabel = t('viewMode')
  const gridViewLabel = t('gridView')
  const listViewLabel = t('listView')

  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={next => {
        if (next) onChange(next as ViewMode)
      }}
      variant="default"
      size="sm"
      className={cn('inline-flex h-9 items-center rounded-xl border bg-background p-0.5 shadow-sm', className)}
      aria-label={viewModeLabel}
    >
      <ToggleGroupItem
        value="grid"
        aria-label={gridViewLabel}
        title={gridViewLabel}
        className="h-8 min-w-8 rounded-lg border-0 px-2 text-muted-foreground shadow-none transition-colors data-[state=on]:bg-accent data-[state=on]:text-foreground data-[state=on]:shadow-sm"
      >
        <LayoutGrid className="h-4 w-4" />
      </ToggleGroupItem>
      <ToggleGroupItem
        value="list"
        aria-label={listViewLabel}
        title={listViewLabel}
        className="h-8 min-w-8 rounded-lg border-0 px-2 text-muted-foreground shadow-none transition-colors data-[state=on]:bg-accent data-[state=on]:text-foreground data-[state=on]:shadow-sm"
      >
        <List className="h-4 w-4" />
      </ToggleGroupItem>
    </ToggleGroup>
  )
}
