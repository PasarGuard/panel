import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { UserCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useBulkSetOwner, useSetOwnerById, UserResponse } from '@/service/api'
import { toast } from 'sonner'
import useDynamicErrorHandler from '@/hooks/use-dynamic-errors'
import { Skeleton } from '@/components/ui/skeleton'

interface SetOwnerModalProps {
  open: boolean
  onClose: () => void
  userId?: number
  username?: string
  userIds?: number[]
  selectedCount?: number
  currentOwner?: string | null
  onSuccess?: (user?: UserResponse) => void
}

export default function SetOwnerModal({ open, onClose, userId, username, userIds, selectedCount, currentOwner, onSuccess }: SetOwnerModalProps) {
  const { t } = useTranslation()
  const [selectedAdmin, setSelectedAdmin] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [fetchAdmins, setFetchAdmins] = useState(false)
  const [admins, setAdmins] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isError, setIsError] = useState(false)
  const isBulkMode = Boolean(userIds?.length)
  const bulkCount = selectedCount ?? userIds?.length ?? 0
  const setOwnerMutation = useSetOwnerById({
    mutation: {
      onSuccess: updatedUser => {
        if (onSuccess && updatedUser) {
          onSuccess(updatedUser)
        }
      },
    },
  })
  const bulkSetOwnerMutation = useBulkSetOwner()
  const handleDynamicError = useDynamicErrorHandler()

  useEffect(() => {
    if (open) {
      setFetchAdmins(true)
    } else {
      setFetchAdmins(false)
      setAdmins([])
      setIsLoading(false)
      setIsError(false)
      setSelectedAdmin(null)
    }
  }, [open])

  useEffect(() => {
    if (fetchAdmins) {
      setIsLoading(true)
      setIsError(false)
      import('@/service/api').then(api => {
        api
          .getAdmins()
          .then(adminsResponse => {
            setAdmins(adminsResponse?.admins || [])
            setIsLoading(false)
          })
          .catch(() => {
            setIsError(true)
            setIsLoading(false)
          })
      })
    }
  }, [fetchAdmins])

  const handleSubmit = async () => {
    if (!selectedAdmin) return
    setSubmitting(true)
    try {
      if (isBulkMode) {
        await bulkSetOwnerMutation.mutateAsync({
          data: {
            ids: userIds ?? [],
            admin_username: selectedAdmin,
          },
        })
        toast.success(t('setOwnerModal.bulkSuccess', { count: bulkCount, admin: selectedAdmin }))
        onSuccess?.()
      } else if (userId) {
        await setOwnerMutation.mutateAsync({ userId, params: { admin_username: selectedAdmin } })
        toast.success(t('setOwnerModal.success', { username, admin: selectedAdmin }))
      }
      onClose()
    } catch (error: any) {
      handleDynamicError({
        error,
        fields: ['admin_username'],
        form: { setError: () => {}, clearErrors: () => {} },
        contextKey: 'setOwnerModal',
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserCheck className="h-5 w-5" />
            <span>{t('setOwnerModal.title', { defaultValue: 'Set Owner' })}</span>
          </DialogTitle>
        </DialogHeader>
        <div className="mt-2 flex flex-col gap-4">
          <div>
            {isBulkMode ? (
              <div className="mb-3 text-sm text-muted-foreground">
                {t('setOwnerModal.bulkDescription', {
                  defaultValue: 'Select a new owner for {{count}} selected users.',
                  count: bulkCount,
                })}
              </div>
            ) : (
              <div className="mb-3 text-sm text-muted-foreground">
                {t('setOwnerModal.currentOwner', { defaultValue: 'Current owner:' })}
                <span className="ml-4 font-bold">{currentOwner || t('setOwnerModal.none', { defaultValue: 'None' })}</span>
              </div>
            )}
            {isLoading ? (
              <div className="space-y-2 p-2">
                <Skeleton className="h-10 w-full" />
                <div className="space-y-1 rounded-md border p-2">
                  <Skeleton className="h-4 w-32" />
                </div>
              </div>
            ) : isError ? (
              <div className="p-2 text-destructive">{t('setOwnerModal.loadError', { defaultValue: 'Failed to load admins.' })}</div>
            ) : admins.length > 0 ? (
              <Select value={selectedAdmin ?? ''} onValueChange={setSelectedAdmin}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('setOwnerModal.selectAdmin', { defaultValue: 'Select new owner' })} />
                </SelectTrigger>
                <SelectContent>
                  {admins.map((admin: any) => (
                    <SelectItem key={admin.username} value={admin.username}>
                      {admin.username}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="p-2 text-sm text-muted-foreground">{t('noAdminsFound')}</div>
            )}
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              {t('cancel', { defaultValue: 'Cancel' })}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={!selectedAdmin || submitting}>
              {submitting ? t('submitting', { defaultValue: 'Submitting...' }) : t('setOwnerModal.confirm', { defaultValue: 'Set Owner' })}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
