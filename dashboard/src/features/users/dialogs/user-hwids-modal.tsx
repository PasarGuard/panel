import { CopyButton } from '@/components/common/copy-button'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import useDirDetection from '@/hooks/use-dir-detection'
import { getGetUserHwidsQueryKey, useDeleteUserHwid, useGetUserHwids, useResetUserHwids, type UserHWIDResponse } from '@/service/api'
import { dateUtils } from '@/utils/dateFormatter'
import { useQueryClient } from '@tanstack/react-query'
import { Fingerprint, Laptop, RefreshCw, Smartphone, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface UserHwidsModalProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  userId: number
  username?: string
}

const formatHwidDate = (value?: string | number | null) => {
  if (!value) return null
  return dateUtils.toDayjs(value).format('YYYY-MM-DD HH:mm')
}

const getDeviceIcon = (deviceOs?: string | null) => {
  const os = deviceOs?.toLowerCase() || ''
  if (os.includes('android') || os.includes('ios') || os.includes('iphone') || os.includes('ipad')) {
    return Smartphone
  }
  return Laptop
}

export function UserHwidsModal({ isOpen, onOpenChange, userId, username }: UserHwidsModalProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const queryClient = useQueryClient()
  const [hwidToDelete, setHwidToDelete] = useState<string | null>(null)
  const [isResetDialogOpen, setResetDialogOpen] = useState(false)

  const queryKey = useMemo(() => getGetUserHwidsQueryKey(userId), [userId])
  const { data, isLoading, error } = useGetUserHwids(userId, {
    query: {
      enabled: isOpen && !!userId,
    },
  })

  const invalidateHwids = () => queryClient.invalidateQueries({ queryKey })

  const deleteMutation = useDeleteUserHwid({
    mutation: {
      onSuccess: () => {
        toast.success(t('hwids.deleteSuccess', { defaultValue: 'Hardware ID removed' }))
        setHwidToDelete(null)
        invalidateHwids()
      },
      onError: (deleteError: any) => {
        toast.error(t('hwids.deleteFailed', { defaultValue: 'Failed to remove hardware ID' }), {
          description: deleteError?.data?.detail || deleteError?.message || '',
        })
      },
    },
  })

  const resetMutation = useResetUserHwids({
    mutation: {
      onSuccess: () => {
        toast.success(t('hwids.resetSuccess', { defaultValue: 'All hardware IDs reset' }))
        setResetDialogOpen(false)
        invalidateHwids()
      },
      onError: (resetError: any) => {
        toast.error(t('hwids.resetFailed', { defaultValue: 'Failed to reset hardware IDs' }), {
          description: resetError?.data?.detail || resetError?.message || '',
        })
      },
    },
  })

  const hwids = data?.hwids || []

  const renderHwidCard = (item: UserHWIDResponse) => {
    const DeviceIcon = getDeviceIcon(item.device_os)
    const createdAt = formatHwidDate(item.created_at)
    const lastUsedAt = formatHwidDate(item.last_used_at)

    return (
      <div key={item.id} className="rounded-md border bg-card p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2">
            <DeviceIcon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 space-y-2">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <p className="max-w-full truncate font-mono text-xs" dir="ltr">
                      {item.hwid}
                    </p>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-sm">
                    <p className="break-all font-mono text-xs" dir="ltr">
                      {item.hwid}
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <div className="flex flex-wrap gap-1.5">
                {item.device_os && <Badge variant="secondary">{item.device_os}</Badge>}
                {item.os_version && <Badge variant="outline">v{item.os_version}</Badge>}
                {item.device_model && <Badge variant="outline">{item.device_model}</Badge>}
              </div>
              <div className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                {createdAt && (
                  <span>
                    {t('hwids.createdAt', { defaultValue: 'Created' })}: <span dir="ltr">{createdAt}</span>
                  </span>
                )}
                {lastUsedAt && (
                  <span>
                    {t('hwids.lastUsedAt', { defaultValue: 'Last used' })}: <span dir="ltr">{lastUsedAt}</span>
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <CopyButton
              value={item.hwid}
              className="h-8 w-8"
              copiedMessage="hwids.copied"
              defaultMessage="hwids.copy"
              showToast
              toastSuccessMessage="hwids.copied"
            />
            <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => setHwidToDelete(item.hwid)}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[90vh] max-w-full flex-col sm:h-[620px] sm:max-w-3xl" dir={dir}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Fingerprint className="h-5 w-5" />
            <span>{t('hwids.title', { defaultValue: 'Hardware IDs' })}</span>
            {username && (
              <Badge variant="outline" dir="ltr">
                {username}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription className="sr-only">{t('hwids.description', { defaultValue: 'Manage registered hardware IDs for this user.' })}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button className='flex items-center gap-2' type="button" variant="destructive" onClick={() => setResetDialogOpen(true)} disabled={hwids.length === 0 || resetMutation.isPending}>
            <RefreshCw className='h-4 w-4' />
            <span>
              {t('hwids.reset', { defaultValue: 'Reset all' })}
            </span>
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="space-y-3 p-1">
              {isLoading &&
                Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="rounded-md border p-3">
                    <Skeleton className="h-4 w-2/3" />
                    <div className="mt-3 flex gap-2">
                      <Skeleton className="h-5 w-16" />
                      <Skeleton className="h-5 w-20" />
                    </div>
                    <Skeleton className="mt-3 h-3 w-1/2" />
                  </div>
                ))}

              {error && <div className="py-8 text-center text-sm text-destructive">{t('hwids.loadFailed', { defaultValue: 'Failed to load hardware IDs' })}</div>}

              {!isLoading && !error && hwids.length === 0 && (
                <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
                  <Fingerprint className="h-8 w-8" />
                  <p className="text-sm">{t('hwids.empty', { defaultValue: 'No hardware IDs registered yet' })}</p>
                </div>
              )}

              {!isLoading && !error && hwids.map(renderHwidCard)}
            </div>
          </ScrollArea>
        </div>

        <div className="flex justify-end border-t pt-3">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('close', { defaultValue: 'Close' })}
          </Button>
        </div>
      </DialogContent>

      <AlertDialog open={!!hwidToDelete} onOpenChange={open => !open && setHwidToDelete(null)}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('hwids.deleteTitle', { defaultValue: 'Remove hardware ID' })}</AlertDialogTitle>
            <AlertDialogDescription>{t('hwids.deletePrompt', { defaultValue: 'This device will need to register again on the next subscription request.' })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>{t('cancel', { defaultValue: 'Cancel' })}</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleteMutation.isPending || !hwidToDelete}
              onClick={() => hwidToDelete && deleteMutation.mutate({ userId, hwid: hwidToDelete })}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('remove', { defaultValue: 'Remove' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={isResetDialogOpen} onOpenChange={setResetDialogOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('hwids.resetTitle', { defaultValue: 'Reset all hardware IDs' })}</AlertDialogTitle>
            <AlertDialogDescription>{t('hwids.resetPrompt', { defaultValue: 'All registered devices for this user will be removed.' })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resetMutation.isPending}>{t('cancel', { defaultValue: 'Cancel' })}</AlertDialogCancel>
            <AlertDialogAction disabled={resetMutation.isPending} onClick={() => resetMutation.mutate({ userId })}>
              {t('hwids.reset', { defaultValue: 'Reset all' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  )
}
