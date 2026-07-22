import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Copy, EllipsisVertical, Pen, Trash2 } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { createClientTemplate, useRemoveClientTemplate, ClientTemplateResponse } from '@/service/api'
import { queryClient } from '@/utils/query-client'

interface ClientTemplateActionsMenuProps {
  template: ClientTemplateResponse
  onEdit: (template: ClientTemplateResponse) => void
  canCreate?: boolean
  canUpdate?: boolean
  canDelete?: boolean
  className?: string
}

const DeleteAlertDialog = ({ template, isOpen, onClose, onConfirm }: { template: ClientTemplateResponse; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('clientTemplates.deleteTitle', { defaultValue: 'Delete Client Template' })}</AlertDialogTitle>
          <AlertDialogDescription>
            <span
              dir={dir}
              dangerouslySetInnerHTML={{
                __html: t('clientTemplates.deletePrompt', {
                  name: template.name,
                  defaultValue: `Are you sure you want to delete <b>{{name}}</b>? This action cannot be undone.`,
                }),
              }}
            />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('remove')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function ClientTemplateActionsMenu({ template, onEdit, canCreate = true, canUpdate = true, canDelete = true, className }: ClientTemplateActionsMenuProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const removeClientTemplateMutation = useRemoveClientTemplate()
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)

  const handleDeleteClick = (event: Event) => {
    event.preventDefault()
    event.stopPropagation()
    if (!canDelete) return
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (!canDelete) return

    try {
      await removeClientTemplateMutation.mutateAsync({ templateId: template.id })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('clientTemplates.deleteSuccess', {
          name: template.name,
          defaultValue: 'Template "{{name}}" has been deleted successfully',
        }),
      })
      setDeleteDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['/api/client_templates'] })
    } catch {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('clientTemplates.deleteFailed', {
          name: template.name,
          defaultValue: 'Failed to delete template "{{name}}"',
        }),
      })
    }
  }

  const handleDuplicate = async () => {
    if (!canCreate) return

    try {
      await createClientTemplate({
        name: `${template.name} (copy)`,
        template_type: template.template_type,
        content: template.content,
        is_default: false,
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('clientTemplates.duplicateSuccess', {
          name: template.name,
          defaultValue: 'Template "{{name}}" has been duplicated successfully',
        }),
      })
      queryClient.invalidateQueries({ queryKey: ['/api/client_templates'] })
    } catch {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t('clientTemplates.duplicateFailed', {
          name: template.name,
          defaultValue: 'Failed to duplicate template "{{name}}"',
        }),
      })
    }
  }

  const hasTemplateActions = canUpdate || (!template.is_system && (canCreate || canDelete))
  if (!hasTemplateActions) return null

  return (
    <div className={cn(className)} onClick={e => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon">
            <EllipsisVertical />
            <span className="sr-only">Template Actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={dir === 'rtl' ? 'end' : 'start'}>
          {canUpdate && (
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onEdit(template)
              }}
            >
              <Pen className="h-4 w-4" />
              <span>{t('edit')}</span>
            </DropdownMenuItem>
          )}
          {!template.is_system && (canCreate || canDelete) && (
            <>
              {canCreate && (
                <DropdownMenuItem
                  dir={dir}
                  onSelect={e => {
                    e.stopPropagation()
                    handleDuplicate()
                  }}
                >
                  <Copy className="h-4 w-4" />
                  <span>{t('duplicate')}</span>
                </DropdownMenuItem>
              )}
              {(canUpdate || canCreate) && canDelete && <DropdownMenuSeparator />}
              {canDelete && (
                <DropdownMenuItem
                  dir={dir}
                  className="!text-red-500"
                  onSelect={e => {
                    e.stopPropagation()
                    handleDeleteClick(e)
                  }}
                >
                  <Trash2 className="h-4 w-4 text-red-500" />
                  <span>{t('delete')}</span>
                </DropdownMenuItem>
              )}
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {canDelete && <DeleteAlertDialog template={template} isOpen={isDeleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />}
    </div>
  )
}
