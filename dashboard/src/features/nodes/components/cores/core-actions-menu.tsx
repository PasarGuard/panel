import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Copy, MoreVertical, Pencil, Trash2 } from 'lucide-react'
import { CoreResponse } from '@/service/api'

interface CoreActionsMenuProps {
  core: CoreResponse
  onEdit: (core: CoreResponse) => void
  onDuplicate?: () => void
  onDelete?: () => void
  canUpdate?: boolean
  canCreate?: boolean
  canDelete?: boolean
  className?: string
}

export default function CoreActionsMenu({ core, onEdit, onDuplicate, onDelete, canUpdate = true, canCreate = true, canDelete = true, className }: CoreActionsMenuProps) {
  const { t } = useTranslation()

  const handleDeleteClick = (event: Event) => {
    event.preventDefault()
    event.stopPropagation()
    if (!canDelete) return
    if (onDelete) {
      onDelete()
    }
  }

  const hasActions = canUpdate || (canCreate && !!onDuplicate) || (canDelete && !!onDelete)
  if (!hasActions) return null

  return (
    <div className={className} onClick={e => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {canUpdate && (
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onEdit(core)
              }}
            >
              <Pencil className="mr-2 h-4 w-4" />
              {t('edit')}
            </DropdownMenuItem>
          )}
          {canCreate && onDuplicate && (
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onDuplicate()
              }}
            >
              <Copy className="mr-2 h-4 w-4" />
              {t('duplicate')}
            </DropdownMenuItem>
          )}
          {(canUpdate || (canCreate && onDuplicate)) && canDelete && onDelete && <DropdownMenuSeparator />}
          {canDelete && onDelete && (
            <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive">
              <Trash2 className="mr-2 h-4 w-4" />
              {t('delete')}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
