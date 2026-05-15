import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTranslation } from 'react-i18next'
import { MoreVertical, Pencil, Trash2 } from 'lucide-react'

export interface CoreEditorRowActionsMenuProps {
  /** Edit opens the detailed editor (same as row click). */
  onEdit: () => void
  onRemove: () => void
  /** When true, delete is shown but not actionable (e.g. minimum list size). */
  removeDisabled?: boolean
  className?: string
}

export function CoreEditorRowActionsMenu({ onEdit, onRemove, removeDisabled, className }: CoreEditorRowActionsMenuProps) {
  const { t } = useTranslation()

  const handleEditSelect = (event: Event) => {
    event.stopPropagation()
    onEdit()
  }

  const handleRemoveSelect = (event: Event) => {
    event.stopPropagation()
    if (removeDisabled) return
    onRemove()
  }

  return (
    <div className={className} onClick={e => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem className="gap-2" onSelect={handleEditSelect}>
            <Pencil className="size-4 shrink-0" />
            {t('edit')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={removeDisabled}
            onSelect={handleRemoveSelect}
            className="gap-2 text-destructive focus:text-destructive data-[disabled]:opacity-50"
          >
            <Trash2 className="size-4 shrink-0" />
            {t('delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
