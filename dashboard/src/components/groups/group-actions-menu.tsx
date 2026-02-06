import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { MoreVertical, Pencil, Power, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import { GroupResponse, useRemoveGroup } from '@/service/api'
import useDirDetection from '@/hooks/use-dir-detection'

interface GroupActionsMenuProps {
  group: GroupResponse
  onEdit: (group: GroupResponse) => void
  onToggleStatus: (group: GroupResponse) => Promise<void>
  className?: string
}

const DeleteAlertDialog = ({ group, isOpen, onClose, onConfirm }: { group: GroupResponse; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('group.deleteConfirmation')}</AlertDialogTitle>
          <AlertDialogDescription>
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('group.deleteConfirm', { name: group.name }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function GroupActionsMenu({ group, onEdit, onToggleStatus, className }: GroupActionsMenuProps) {
  const { t } = useTranslation()
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const removeGroupMutation = useRemoveGroup()

  const handleDeleteClick = (event: Event) => {
    event.stopPropagation()
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    try {
      await removeGroupMutation.mutateAsync({
        groupId: group.id,
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('group.deleteSuccess', {
          name: group.name,
          defaultValue: 'Group "{name}" has been deleted successfully',
        }),
      })
      setDeleteDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['/api/groups'] })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('group.deleteFailed', {
          name: group.name,
          defaultValue: 'Failed to delete group "{name}"',
        }),
      })
    }
  }

  return (
    <>
      <div className={className} onClick={e => e.stopPropagation()}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8">
              <MoreVertical className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onEdit(group)
              }}
            >
              <Pencil className="mr-2 h-4 w-4 shrink-0" />
              <span className="min-w-0 truncate">{t('edit')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onToggleStatus(group)
              }}
            >
              <Power className="mr-2 h-4 w-4 shrink-0" />
              <span className="min-w-0 truncate">{group.is_disabled ? t('enable') : t('disable')}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={handleDeleteClick} className="text-destructive">
              <Trash2 className="mr-2 h-4 w-4 shrink-0" />
              <span className="min-w-0 truncate">{t('delete')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <DeleteAlertDialog group={group} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />
    </>
  )
}
