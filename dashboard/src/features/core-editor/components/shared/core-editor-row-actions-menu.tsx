import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useTranslation } from 'react-i18next'
import { MoreVertical, Pencil, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'

export interface CoreEditorRowAction {
  key: string
  label: ReactNode
  icon?: ReactNode
  onSelect: () => void
  disabled?: boolean
}

export interface CoreEditorRowActionsMenuProps {
  /** Edit opens the detailed editor (same as row click). */
  onEdit: () => void
  onRemove: () => void
  extraActions?: CoreEditorRowAction[]
  /** When true, delete is shown but not actionable (e.g. minimum list size). */
  removeDisabled?: boolean
  className?: string
}

export function CoreEditorRowActionsMenu({ onEdit, onRemove, extraActions = [], removeDisabled, className }: CoreEditorRowActionsMenuProps) {
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
          {extraActions.map(action => (
            <DropdownMenuItem
              key={action.key}
              className="gap-2"
              disabled={action.disabled}
              onSelect={event => {
                event.stopPropagation()
                if (!action.disabled) action.onSelect()
              }}
            >
              {action.icon}
              {action.label}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={removeDisabled} onSelect={handleRemoveSelect} className="text-destructive focus:text-destructive gap-2 data-[disabled]:opacity-50">
            <Trash2 className="size-4 shrink-0" />
            {t('delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
