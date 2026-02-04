import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Copy, EllipsisVertical, Pen, Power, Trash2 } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { createUserTemplate, useRemoveUserTemplate, UserTemplateCreate, UserTemplateResponse } from '@/service/api'
import { queryClient } from '@/utils/query-client'

interface UserTemplateActionsMenuProps {
  template: UserTemplateResponse
  onEdit: (template: UserTemplateResponse) => void
  onToggleStatus: (template: UserTemplateResponse) => void
  className?: string
}

const DeleteAlertDialog = ({ userTemplate, isOpen, onClose, onConfirm }: { userTemplate: UserTemplateResponse; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader className={cn(dir === 'rtl' && 'sm:text-right')}>
          <AlertDialogTitle>{t('templates.deleteUserTemplateTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('templates.deleteUserTemplatePrompt', { name: userTemplate.name }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className={cn(dir === 'rtl' && 'sm:flex-row-reverse sm:gap-x-2')}>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('remove')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function UserTemplateActionsMenu({ template, onEdit, onToggleStatus, className }: UserTemplateActionsMenuProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const removeUserTemplateMutation = useRemoveUserTemplate()
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)

  const handleDeleteClick = (event: Event) => {
    event.preventDefault()
    event.stopPropagation()
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    try {
      await removeUserTemplateMutation.mutateAsync({
        templateId: template.id,
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('templates.deleteSuccess', {
          name: template.name,
          defaultValue: 'Template «{name}» has been deleted successfully',
        }),
      })
      setDeleteDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['/api/user_templates'] })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('templates.deleteFailed', {
          name: template.name,
          defaultValue: 'Failed to delete template «{name}»',
        }),
      })
    }
  }

  const handleDuplicate = async () => {
    try {
      const newTemplate: UserTemplateCreate = {
        ...template,
        name: `${template.name} (copy)`,
      }
      await createUserTemplate(newTemplate)
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('templates.duplicateSuccess', {
          name: template.name,
          defaultValue: 'Template «{name}» has been duplicated successfully',
        }),
      })
      queryClient.invalidateQueries({ queryKey: ['/api/user_templates'] })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('templates.duplicateFailed', {
          name: template.name,
          defaultValue: 'Failed to duplicate template «{name}»',
        }),
      })
    }
  }

  return (
    <div className={cn(className)} onClick={e => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="template-dropdown-menu">
            <EllipsisVertical />
            <span className="sr-only">Template Actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={dir === 'rtl' ? 'end' : 'start'} className="template-dropdown-menu">
          <DropdownMenuItem
            onSelect={e => {
              e.stopPropagation()
              onToggleStatus(template)
            }}
          >
            <Power className="mr-2 h-4 w-4" />
            {template.is_disabled ? t('enable') : t('disable')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={e => {
              e.stopPropagation()
              onEdit(template)
            }}
          >
            <Pen className="h-4 w-4" />
            <span>{t('edit')}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            dir={dir}
            className="template-dropdown-menu flex items-center"
            onSelect={e => {
              e.stopPropagation()
              handleDuplicate()
            }}
          >
            <Copy className="h-4 w-4" />
            <span>{t('duplicate')}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            dir={dir}
            className="template-dropdown-menu flex items-center !text-red-500"
            onSelect={e => {
              e.stopPropagation()
              handleDeleteClick(e)
            }}
          >
            <Trash2 className="h-4 w-4 text-red-500" />
            <span>{t('delete')}</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DeleteAlertDialog userTemplate={template} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />
    </div>
  )
}
