import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Copy, MoreVertical, Pencil, Trash2 } from 'lucide-react'
import { CoreResponse } from '@/service/api'

interface CoreActionsMenuProps {
  core: CoreResponse
  onEdit: (core: CoreResponse) => void
  onDuplicate?: () => void
  onDelete?: () => void
  className?: string
}

export default function CoreActionsMenu({ core, onEdit, onDuplicate, onDelete, className }: CoreActionsMenuProps) {
  const { t } = useTranslation()

  const handleDeleteClick = (event: Event) => {
    event.stopPropagation()
    if (onDelete) {
      onDelete()
    }
  }

  return (
    <div className={className} onClick={e => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onSelect={e => {
              e.stopPropagation()
              onEdit(core)
            }}
          >
            <Pencil className="mr-2 h-4 w-4" />
            {t('edit')}
          </DropdownMenuItem>
          {onDuplicate && (
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
          <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive">
            <Trash2 className="mr-2 h-4 w-4" />
            {t('delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
