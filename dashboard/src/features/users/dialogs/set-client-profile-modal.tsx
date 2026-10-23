import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Loader2, SlidersHorizontal } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { assignClientProfileUsers, unassignClientProfileUsers } from '@/service/api'
import { ClientProfileSelect } from '@/features/templates/components/client-profile-select'
import { getApiErrorDetail, invalidateClientProfileQueries, useClientProfileOptions } from '@/features/templates/components/use-client-profile-options'
import { profileIdsToDetach } from '@/features/templates/forms/client-profile-form'
import { queryClient } from '@/utils/query-client'

interface SetClientProfileModalProps {
  open: boolean
  onClose: () => void
  userIds: number[]
  /** Users currently loaded in the table; used to find which profiles to detach for "No profile". */
  loadedUsers: ReadonlyArray<{ id: number; client_profile_id?: number | null }>
  selectedCount: number
  onSuccess?: () => void
}

export default function SetClientProfileModal({ open, onClose, userIds, loadedUsers, selectedCount, onSuccess }: SetClientProfileModalProps) {
  const { t } = useTranslation()
  const [profileId, setProfileId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { profiles, isLoading } = useClientProfileOptions(open)

  useEffect(() => {
    if (!open) setProfileId(null)
  }, [open])

  const handleSubmit = async () => {
    if (!userIds.length) return
    setSubmitting(true)
    try {
      let count = 0
      if (profileId !== null) {
        const response = await assignClientProfileUsers(profileId, { user_ids: userIds })
        count = response.count
      } else {
        const ids = profileIdsToDetach(
          userIds,
          loadedUsers,
          profiles.map(profile => profile.id),
        )
        for (const id of ids) {
          const response = await unassignClientProfileUsers(id, { user_ids: userIds })
          count += response.count
        }
      }
      toast.success(
        profileId !== null
          ? t('clientProfiles.bulkAssignSuccess', { count, defaultValue: 'Profile set for {{count}} users' })
          : t('clientProfiles.bulkUnassignSuccess', { count, defaultValue: 'Profile removed from {{count}} users' }),
      )
      invalidateClientProfileQueries()
      onSuccess?.()
      onClose()
    } catch (error: any) {
      // Some requests may have succeeded before the failure; refresh what the table shows
      invalidateClientProfileQueries()
      queryClient.invalidateQueries({ queryKey: ['/api/users'] })
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: getApiErrorDetail(error) || t('clientProfiles.bulkAssignFailed', { defaultValue: 'Failed to change the client profile' }),
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={next => !next && !submitting && onClose()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5" />
            <span>{t('clientProfiles.bulkAssignTitle', { defaultValue: 'Set client profile' })}</span>
          </DialogTitle>
          <DialogDescription className="text-xs">
            {t('clientProfiles.bulkAssignDescription', {
              count: selectedCount,
              defaultValue: 'Choose the profile for {{count}} selected users. "No profile" returns them to the default settings.',
            })}
          </DialogDescription>
        </DialogHeader>
        <div className="mt-2 flex flex-col gap-4">
          <ClientProfileSelect value={profileId} onChange={setProfileId} enabled={open} disabled={submitting} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              {t('cancel')}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={submitting || isLoading || !userIds.length}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('clientProfiles.apply', { defaultValue: 'Apply' })}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
