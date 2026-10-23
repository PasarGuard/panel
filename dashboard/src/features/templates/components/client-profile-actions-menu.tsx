import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Copy, EllipsisVertical, Pen, Trash2, UserMinus } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { createClientProfile, useRemoveClientProfile, useUnassignClientProfileUsers, ClientProfileResponse } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { translateHtml } from '@/utils/html-translation'
import { getApiErrorDetail, invalidateClientProfileQueries } from './use-client-profile-options'

interface ClientProfileActionsMenuProps {
  profile: ClientProfileResponse
  onEdit: (profile: ClientProfileResponse) => void
  canCreate?: boolean
  canUpdate?: boolean
  canDelete?: boolean
  className?: string
}

type ConfirmKind = 'delete' | 'detach' | null

const ConfirmDialog = ({ profile, kind, onClose, onConfirm, isPending }: { profile: ClientProfileResponse; kind: ConfirmKind; onClose: () => void; onConfirm: () => void; isPending: boolean }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isDelete = kind === 'delete'

  return (
    <AlertDialog open={kind !== null} onOpenChange={open => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {isDelete ? t('clientProfiles.deleteTitle', { defaultValue: 'Delete client profile' }) : t('clientProfiles.detachAllTitle', { defaultValue: 'Remove from all users' })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            <span
              dir={dir}
              dangerouslySetInnerHTML={{
                __html: isDelete
                  ? translateHtml(t, 'clientProfiles.deletePrompt', {
                      name: profile.name,
                      defaultValue: 'Delete <b>{{name}}</b>? Users on this profile will get the default subscription settings. This cannot be undone.',
                    })
                  : translateHtml(t, 'clientProfiles.detachAllPrompt', {
                      name: profile.name,
                      count: profile.users_count ?? 0,
                      defaultValue: 'Remove <b>{{name}}</b> from all {{count}} users? They will get the default subscription settings.',
                    }),
              }}
            />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose} disabled={isPending}>
            {t('cancel')}
          </AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm} disabled={isPending}>
            {isDelete ? t('remove') : t('clientProfiles.detachAll', { defaultValue: 'Remove from all users' })}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function ClientProfileActionsMenu({ profile, onEdit, canCreate = true, canUpdate = true, canDelete = true, className }: ClientProfileActionsMenuProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const removeClientProfileMutation = useRemoveClientProfile()
  const unassignUsersMutation = useUnassignClientProfileUsers()
  const [confirm, setConfirm] = useState<ConfirmKind>(null)

  const handleConfirm = async () => {
    if (confirm === 'delete') {
      if (!canDelete) return
      try {
        await removeClientProfileMutation.mutateAsync({ profileId: profile.id })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('clientProfiles.deleteSuccess', { name: profile.name, defaultValue: 'Profile "{{name}}" deleted' }),
        })
        setConfirm(null)
        invalidateClientProfileQueries()
        queryClient.invalidateQueries({ queryKey: ['/api/users'] })
      } catch (error: any) {
        toast.error(t('error', { defaultValue: 'Error' }), {
          description: getApiErrorDetail(error) || t('clientProfiles.deleteFailed', { name: profile.name, defaultValue: 'Failed to delete profile "{{name}}"' }),
        })
      }
      return
    }

    if (confirm === 'detach') {
      if (!canUpdate) return
      try {
        const response = await unassignUsersMutation.mutateAsync({ profileId: profile.id, data: { all: true } })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('clientProfiles.detachAllSuccess', { count: response.count, defaultValue: 'Profile removed from {{count}} users' }),
        })
        setConfirm(null)
        invalidateClientProfileQueries()
        queryClient.invalidateQueries({ queryKey: ['/api/users'] })
      } catch (error: any) {
        toast.error(t('error', { defaultValue: 'Error' }), {
          description: getApiErrorDetail(error) || t('clientProfiles.detachAllFailed', { defaultValue: 'Failed to remove the profile from users' }),
        })
      }
    }
  }

  const handleDuplicate = async () => {
    if (!canCreate) return

    try {
      await createClientProfile({
        name: `${profile.name} (copy)`.slice(0, 64),
        note: profile.note ?? null,
        templates: profile.templates ?? {},
        settings: profile.settings ?? {},
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('clientProfiles.duplicateSuccess', { name: profile.name, defaultValue: 'Profile "{{name}}" duplicated' }),
      })
      invalidateClientProfileQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: getApiErrorDetail(error) || t('clientProfiles.duplicateFailed', { name: profile.name, defaultValue: 'Failed to duplicate profile "{{name}}"' }),
      })
    }
  }

  const canDetach = canUpdate && (profile.users_count ?? 0) > 0
  if (!canUpdate && !canCreate && !canDelete) return null

  return (
    <div className={cn(className)} onClick={e => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon">
            <EllipsisVertical />
            <span className="sr-only">Profile Actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={dir === 'rtl' ? 'end' : 'start'}>
          {canUpdate && (
            <DropdownMenuItem
              onSelect={e => {
                e.stopPropagation()
                onEdit(profile)
              }}
            >
              <Pen className="h-4 w-4" />
              <span>{t('edit')}</span>
            </DropdownMenuItem>
          )}
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
          {canDetach && (
            <DropdownMenuItem
              dir={dir}
              onSelect={e => {
                e.stopPropagation()
                setConfirm('detach')
              }}
            >
              <UserMinus className="h-4 w-4" />
              <span>{t('clientProfiles.detachAll', { defaultValue: 'Remove from all users' })}</span>
            </DropdownMenuItem>
          )}
          {canDelete && (
            <>
              {(canUpdate || canCreate) && <DropdownMenuSeparator />}
              <DropdownMenuItem
                dir={dir}
                className="!text-red-500"
                onSelect={e => {
                  e.stopPropagation()
                  setConfirm('delete')
                }}
              >
                <Trash2 className="h-4 w-4 text-red-500" />
                <span>{t('delete')}</span>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog profile={profile} kind={confirm} onClose={() => setConfirm(null)} onConfirm={handleConfirm} isPending={removeClientProfileMutation.isPending || unassignUsersMutation.isPending} />
    </div>
  )
}
