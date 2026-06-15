import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Copy, Eye, MoreVertical, Pencil, Trash2 } from 'lucide-react'

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { queryClient } from '@/utils/query-client'
import { AdminRoleResponse, getGetRolesQueryKey, getGetRolesSimpleQueryKey, useDeleteRole } from '@/service/api'

import { isProtectedRole, isReadOnlyRole } from '@/features/admin-roles/forms/admin-role-form'

interface AdminRoleActionsMenuProps {
  role: AdminRoleResponse
  onEdit: (role: AdminRoleResponse) => void
  onDuplicate: (role: AdminRoleResponse) => void
  className?: string
}

export default function AdminRoleActionsMenu({ role, onEdit, onDuplicate, className }: AdminRoleActionsMenuProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const deleteRole = useDeleteRole()
  const protectedRole = isProtectedRole(role)
  const readOnlyRole = isReadOnlyRole(role)
  const canDeleteRole = !protectedRole

  const handleDeleteClick = (event: Event) => {
    event.stopPropagation()
    if (!canDeleteRole) return
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    try {
      await deleteRole.mutateAsync({ roleId: role.id })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('adminRoles.deleteSuccess', { name: role.name, defaultValue: 'Role «{{name}}» has been deleted successfully' }),
      })
      setDeleteDialogOpen(false)
      await Promise.all([queryClient.invalidateQueries({ queryKey: getGetRolesQueryKey() }), queryClient.invalidateQueries({ queryKey: getGetRolesSimpleQueryKey() })])
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('adminRoles.deleteFailed', { name: role.name, defaultValue: 'Failed to delete role «{{name}}»' }),
      })
    }
  }

  return (
    <>
      <div className={className} onClick={e => e.stopPropagation()}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon" className="h-7 w-7 sm:h-8 sm:w-8">
              <MoreVertical className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'}>
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onEdit(role)
              }}
            >
              {readOnlyRole ? <Eye className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} /> : <Pencil className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} />}
              <span className="min-w-0 truncate">{readOnlyRole ? t('view', { defaultValue: 'View' }) : t('edit', { defaultValue: 'Edit' })}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onDuplicate(role)
              }}
            >
              <Copy className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} />
              <span className="min-w-0 truncate">{t('duplicate', { defaultValue: 'Duplicate' })}</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={protectedRole} onSelect={handleDeleteClick} className="text-destructive">
              <Trash2 className={cn('h-4 w-4 shrink-0', dir === 'rtl' ? 'ml-2' : 'mr-2')} />
              <span className="min-w-0 truncate">{t('delete')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent onClick={event => event.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('adminRoles.deleteConfirmation', { defaultValue: 'Delete role' })}</AlertDialogTitle>
            <AlertDialogDescription>
              <span dir={dir} dangerouslySetInnerHTML={{ __html: t('adminRoles.deleteConfirm', { name: role.name, defaultValue: 'Are you sure you want to delete role <b>{{name}}</b>?' }) }} />
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleConfirmDelete}>
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
