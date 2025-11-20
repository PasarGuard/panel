import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useClipboard } from '@/hooks/use-clipboard'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { UseEditFormValues, UseFormValues } from '@/pages/_dashboard.users'
import { useActiveNextPlan, useGetCurrentAdmin, useRemoveUser, useResetUserDataUsage, useRevokeUserSubscription, UserResponse } from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Cpu, EllipsisVertical, ListStart, Network, Pencil, PieChart, QrCode, RefreshCcw, Trash2, User, Users } from 'lucide-react'
import { FC, useCallback, useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { CopyButton } from '@/components/common/copy-button'
import QRCodeModal from '@/components/dialogs/qrcode-modal'
import SetOwnerModal from '@/components/dialogs/set-owner-modal'
import UsageModal from '@/components/dialogs/usage-modal'
import UserModal from '@/components/dialogs/user-modal'
import { UserSubscriptionClientsModal } from '@/components/dialogs/user-subscription-clients-modal'
import UserAllIPsModal from '@/components/dialogs/user-all-ips-modal'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

type ActionButtonsProps = {
  user: UserResponse
}

export interface SubscribeLink {
  protocol: string
  link: string
  icon: string
}

const ActionButtons: FC<ActionButtonsProps> = ({ user }) => {
  const [subscribeUrl, setSubscribeUrl] = useState<string>('')
  const [subscribeLinks, setSubscribeLinks] = useState<SubscribeLink[]>([])
  const [showQRModal, setShowQRModal] = useState(false)
  const [isEditModalOpen, setEditModalOpen] = useState(false)
  const [isDeleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [isResetUsageDialogOpen, setResetUsageDialogOpen] = useState(false)
  const [isRevokeSubDialogOpen, setRevokeSubDialogOpen] = useState(false)
  const [isUsageModalOpen, setUsageModalOpen] = useState(false)
  const [isSetOwnerModalOpen, setSetOwnerModalOpen] = useState(false)
  const [isActiveNextPlanModalOpen, setIsActiveNextPlanModalOpen] = useState(false)
  const [isSubscriptionClientsModalOpen, setSubscriptionClientsModalOpen] = useState(false)
  const [isUserAllIPsModalOpen, setUserAllIPsModalOpen] = useState(false)
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const dir = useDirDetection()
  const removeUserMutation = useRemoveUser()
  const resetUserDataUsageMutation = useResetUserDataUsage()
  const revokeUserSubscriptionMutation = useRevokeUserSubscription()
  const activeNextMutation = useActiveNextPlan()
  const { data: currentAdmin } = useGetCurrentAdmin({
    query: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      refetchOnMount: false,
    },
  })

  // Create form for user editing
  const userForm = useForm<UseEditFormValues>({
    defaultValues: {
      username: user.username,
      status: user.status === 'expired' || user.status === 'limited' ? 'active' : user.status,
      data_limit: user.data_limit ? Math.round((Number(user.data_limit) / (1024 * 1024 * 1024)) * 100) / 100 : undefined, // Convert bytes to GB
      expire: user.expire,
      note: user.note || '',
      data_limit_reset_strategy: user.data_limit_reset_strategy || undefined,
      group_ids: user.group_ids || [], // Add group_ids
      on_hold_expire_duration: user.on_hold_expire_duration || undefined,
      next_plan: user.next_plan
        ? {
            user_template_id: user.next_plan.user_template_id ? Number(user.next_plan.user_template_id) : undefined,
            data_limit: user.next_plan.data_limit ? Number(user.next_plan.data_limit) : undefined,
            expire: user.next_plan.expire ? Number(user.next_plan.expire) : undefined,
            add_remaining_traffic: user.next_plan.add_remaining_traffic || false,
          }
        : undefined,
    },
  })

  // Update form when user data changes
  useEffect(() => {
    const values: UseFormValues = {
      username: user.username,
      status: user.status === 'active' || user.status === 'on_hold' || user.status === 'disabled' ? (user.status as any) : 'active',
      data_limit: user.data_limit ? Math.round((Number(user.data_limit) / (1024 * 1024 * 1024)) * 100) / 100 : 0,
      expire: user.expire, // Pass raw expire value (timestamp)
      note: user.note || '',
      data_limit_reset_strategy: user.data_limit_reset_strategy || undefined,
      group_ids: user.group_ids || [],
      on_hold_expire_duration: user.on_hold_expire_duration || undefined,
      proxy_settings: user.proxy_settings || undefined,
      next_plan: user.next_plan
        ? {
            user_template_id: user.next_plan.user_template_id ? Number(user.next_plan.user_template_id) : undefined,
            data_limit: user.next_plan.data_limit ? Number(user.next_plan.data_limit) : undefined,
            expire: user.next_plan.expire ? Number(user.next_plan.expire) : undefined,
            add_remaining_traffic: user.next_plan.add_remaining_traffic || false,
          }
        : undefined,
    }

    // Update form with current values
    userForm.reset(values)
  }, [user, userForm])

  const onOpenQRModal = useCallback(() => {
    setSubscribeUrl(user.subscription_url ? user.subscription_url : '')
    setShowQRModal(true)
  }, [user.subscription_url])

  const onCloseQRModal = useCallback(() => {
    setSubscribeUrl('')
    setShowQRModal(false)
  }, [])

  useEffect(() => {
    if (user.subscription_url) {
      const subURL = user.subscription_url.startsWith('/') ? window.location.origin + user.subscription_url : user.subscription_url

      const links = [
        { protocol: 'links', link: `${subURL}/links`, icon: '🔗' },
        { protocol: 'links (base64)', link: `${subURL}/links_base64`, icon: '📝' },
        { protocol: 'xray', link: `${subURL}/xray`, icon: '⚡' },
        { protocol: 'clash', link: `${subURL}/clash`, icon: '⚔️' },
        { protocol: 'clash-meta', link: `${subURL}/clash_meta`, icon: '🛡️' },
        { protocol: 'outline', link: `${subURL}/outline`, icon: '🔒' },
        { protocol: 'sing-box', link: `${subURL}/sing_box`, icon: '📦' },
      ]
      setSubscribeLinks(links)
    }
  }, [user.subscription_url])

  const { copy, copied } = useClipboard({ timeout: 1500 })

  // Refresh user data function
  const refreshUserData = () => {
    queryClient.invalidateQueries({ queryKey: ['/api/users'] })
  }

  // Handlers for menu items
  const handleEdit = () => {
    // Only need to open modal since form values are already updated via useEffect
    setEditModalOpen(true)
  }

  const handleSetOwner = () => {
    setSetOwnerModalOpen(true)
  }

  const handleRevokeSubscription = () => {
    setRevokeSubDialogOpen(true)
  }

  const confirmRevokeSubscription = async () => {
    try {
      await revokeUserSubscriptionMutation.mutateAsync({ username: user.username })
      toast.success(t('userDialog.revokeSubSuccess', { name: user.username }))
      setRevokeSubDialogOpen(false)
      refreshUserData()
    } catch (error: any) {
      toast.error(t('revokeUserSub.error', { name: user.username, error: error?.message || '' }))
    }
  }

  const handleActiveNextPlan = () => {
    setIsActiveNextPlanModalOpen(true)
  }

  const activeNextPlan = async () => {
    try {
      await activeNextMutation.mutateAsync({ username: user.username })
      toast.success(t('userDialog.activeNextPlanSuccess', { name: user.username }))
      refreshUserData()
    } catch (error: any) {
      toast.error(t('userDialog.activeNextPlanError', { name: user.username, error: error?.message || '' }))
    }
  }

  const handleResetUsage = () => {
    setResetUsageDialogOpen(true)
  }

  const confirmResetUsage = async () => {
    try {
      await resetUserDataUsageMutation.mutateAsync({ username: user.username })
      toast.success(t('usersTable.resetUsageSuccess', { name: user.username }))
      setResetUsageDialogOpen(false)
      refreshUserData()
    } catch (error: any) {
      toast.error(t('usersTable.resetUsageFailed', { name: user.username, error: error?.message || '' }))
    }
  }

  const handleUsageState = () => {
    setUsageModalOpen(true)
  }

  const handleDelete = () => {
    setDeleteDialogOpen(true)
  }

  const confirmDelete = async () => {
    try {
      await removeUserMutation.mutateAsync({ username: user.username })
      toast.success(t('usersTable.deleteSuccess', { name: user.username }))
      setDeleteDialogOpen(false)
      refreshUserData()
    } catch (error: any) {
      toast.error(t('usersTable.deleteFailed', { name: user.username, error: error?.message || '' }))
    }
  }

  // Utility functions
  const isIOS = () => {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  }

  const showManualCopyAlert = (content: string, type: 'content' | 'url') => {
    const message =
      type === 'content' ? t('copyFailed', { defaultValue: 'Failed to copy automatically. Please copy manually:' }) : t('downloadFailed', { defaultValue: 'Download blocked. Please copy manually:' })
    alert(`${message}\n\n${content}`)
  }

  const fetchContent = async (url: string): Promise<string> => {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return response.text()
  }

  const handleLinksCopy = async (subLink: SubscribeLink) => {
    try {
      if (isIOS()) {
        // iOS: redirect/open in new tab instead of copying
        const newWindow = window.open(subLink.link, '_blank')
        if (!newWindow) {
          const content = await fetchContent(subLink.link)
          showManualCopyAlert(content, 'url')
        } else {
          toast.success(t('downloadSuccess', { defaultValue: 'Configuration opened in new tab' }))
        }
      } else {
        // Non-iOS: copy content as before
        const content = await fetchContent(subLink.link)
        await copy(content)
        toast.success(t('usersTable.copied', { defaultValue: 'Copied to clipboard' }))
      }
    } catch (error) {
      console.error('Failed to fetch and copy content:', error)
      // Fallback: copy the URL instead
      await handleUrlCopy(subLink.link)
    }
  }

  const handleUrlCopy = async (url: string) => {
    try {
      await copy(url)
      toast.success(t('usersTable.copied', { defaultValue: 'URL copied to clipboard' }))
    } catch (error) {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy content' }))
    }
  }

  const handleCopyCoreUsername = () => handleUrlCopy(`${user.id}.${user.username}`)

  const handleConfigDownload = async (subLink: SubscribeLink) => {
    try {
      if (isIOS()) {
        // iOS: open in new tab or show content
        const newWindow = window.open(subLink.link, '_blank')
        if (!newWindow) {
          const content = await fetchContent(subLink.link)
          showManualCopyAlert(content, 'url')
        } else {
          toast.success(t('downloadSuccess', { defaultValue: 'Configuration opened in new tab' }))
        }
      } else {
        // Non-iOS: regular download
        const response = await fetch(subLink.link)
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }

        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${user.username}-${subLink.protocol}.txt`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        toast.success(t('downloadSuccess', { defaultValue: 'Configuration downloaded successfully' }))
      }
    } catch (error) {
      console.error('Failed to download configuration:', error)
      toast.error(t('downloadFailed', { defaultValue: 'Failed to download configuration' }))
    }
  }

  const handleCopyOrDownload = async (subLink: SubscribeLink) => {
    const isLinksProtocol = subLink.protocol === 'links' || subLink.protocol === 'links (base64)'

    if (isLinksProtocol) {
      await handleLinksCopy(subLink)
    } else {
      await handleConfigDownload(subLink)
    }
  }

  return (
    <div onClick={e => e.stopPropagation()}>
      <div className="flex items-center justify-end">
        <Button size="icon" variant="ghost" onClick={handleEdit} className="md:hidden">
          <Pencil className="h-4 w-4" />
        </Button>
        <TooltipProvider>
          <CopyButton
            value={user.subscription_url ? (user.subscription_url.startsWith('/') ? window.location.origin + user.subscription_url : user.subscription_url) : ''}
            copiedMessage="usersTable.copied"
            defaultMessage="usersTable.copyLink"
            icon="link"
          />
          <Tooltip open={copied ? true : undefined}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <TooltipTrigger asChild>
                  <Button size="icon" variant="ghost">
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </TooltipTrigger>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {subscribeLinks.map(subLink => (
                  <DropdownMenuItem className="justify-start p-0" key={subLink.link} onClick={() => handleCopyOrDownload(subLink)}>
                    <span className="flex w-full items-center gap-2 px-2 py-1.5">
                      <span className="text-sm">{subLink.icon}</span>
                      <span>{subLink.protocol}</span>
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <TooltipContent>{copied ? t('usersTable.copied') : t('usersTable.copyConfigs')}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon" variant="ghost">
              <EllipsisVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {/* Edit */}
            <DropdownMenuItem className="hidden md:flex" onClick={handleEdit}>
              <Pencil className="mr-2 h-4 w-4" />
              <span>{t('edit')}</span>
            </DropdownMenuItem>

            {/* QR Code */}
            <DropdownMenuItem onClick={onOpenQRModal}>
              <QrCode className="mr-2 h-4 w-4" />
              <span>Qr Code</span>
            </DropdownMenuItem>

            {/* Set Owner: only for sudo admins */}
            {currentAdmin?.is_sudo && (
              <DropdownMenuItem onClick={handleSetOwner}>
                <User className="mr-2 h-4 w-4" />
                <span>{t('setOwnerModal.title')}</span>
              </DropdownMenuItem>
            )}

            {/* Copy Core Username for sudo admins */}
            {currentAdmin?.is_sudo && (
              <DropdownMenuItem onClick={handleCopyCoreUsername}>
                <Cpu className="mr-2 h-4 w-4" />
                <span>{t('coreUsername')}</span>
              </DropdownMenuItem>
            )}

            <DropdownMenuSeparator />

            {/* Revoke Sub */}
            <DropdownMenuItem onClick={handleRevokeSubscription}>
              <RefreshCcw className="mr-2 h-4 w-4" />
              <span>{t('userDialog.revokeSubscription')}</span>
            </DropdownMenuItem>

            {/* Reset Usage */}
            <DropdownMenuItem onClick={handleResetUsage}>
              <RefreshCcw className="mr-2 h-4 w-4" />
              <span>{t('userDialog.resetUsage')}</span>
            </DropdownMenuItem>

            {/* Usage State */}
            <DropdownMenuItem onClick={handleUsageState}>
              <PieChart className="mr-2 h-4 w-4" />
              <span>{t('userDialog.usage')}</span>
            </DropdownMenuItem>

            {/* Active Next Plan */}
            {user.next_plan && (
              <DropdownMenuItem onClick={handleActiveNextPlan}>
                <ListStart className="mr-2 h-4 w-4" />
                <span>{t('usersTable.activeNextPlanSubmit')}</span>
              </DropdownMenuItem>
            )}

            {/* Subscription Info */}
            <DropdownMenuItem onClick={() => setSubscriptionClientsModalOpen(true)}>
              <Users className="mr-2 h-4 w-4" />
              <span>{t('subscriptionClients.clients', { defaultValue: 'Clients' })}</span>
            </DropdownMenuItem>

            {/* View All IPs: only for sudo admins */}
            {currentAdmin?.is_sudo && (
              <DropdownMenuItem onClick={() => setUserAllIPsModalOpen(true)}>
                <Network className="mr-2 h-4 w-4" />
                <span>{t('userAllIPs.ipAddresses', { defaultValue: 'IP addresses' })}</span>
              </DropdownMenuItem>
            )}

            <DropdownMenuSeparator />

            {/* Trash */}
            <DropdownMenuItem onClick={handleDelete} className="text-red-600">
              <Trash2 className="mr-2 h-4 w-4" />
              <span>{t('remove')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* QR Code Modal */}
      {showQRModal && subscribeUrl && <QRCodeModal subscribeUrl={subscribeUrl} onCloseModal={onCloseQRModal} />}

      {/* Active Next Plan Confirm Dialog */}
      <AlertDialog open={isActiveNextPlanModalOpen} onOpenChange={setIsActiveNextPlanModalOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('usersTable.activeNextPlanTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('usersTable.activeNextPlanPrompt', { name: user.username })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-0 sm:space-x-2')}>
            <AlertDialogCancel onClick={() => setDeleteDialogOpen(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={activeNextPlan} disabled={activeNextMutation.isPending}>
              {t('usersTable.activeNextPlanSubmit')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete User Confirm Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('usersTable.deleteUserTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('usersTable.deleteUserPrompt', { name: user.username })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-0 sm:space-x-2')}>
            <AlertDialogCancel onClick={() => setDeleteDialogOpen(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete} disabled={removeUserMutation.isPending}>
              {t('usersTable.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset Usage Confirm Dialog */}
      <AlertDialog open={isResetUsageDialogOpen} onOpenChange={setResetUsageDialogOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('usersTable.resetUsageTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('usersTable.resetUsagePrompt', { name: user.username })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-0 sm:space-x-2')}>
            <AlertDialogCancel onClick={() => setResetUsageDialogOpen(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmResetUsage} disabled={resetUserDataUsageMutation.isPending}>
              {t('usersTable.resetUsageSubmit')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Revoke Subscription Confirm Dialog */}
      <AlertDialog open={isRevokeSubDialogOpen} onOpenChange={setRevokeSubDialogOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('revokeUserSub.title')}</AlertDialogTitle>
            <AlertDialogDescription>{t('revokeUserSub.prompt', { username: user.username })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-0 sm:space-x-2')}>
            <AlertDialogCancel onClick={() => setRevokeSubDialogOpen(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmRevokeSubscription} disabled={revokeUserSubscriptionMutation.isPending}>
              {t('revokeUserSub.title')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit User Modal */}
      <UserModal
        isDialogOpen={isEditModalOpen}
        onOpenChange={setEditModalOpen}
        form={userForm}
        editingUser={true}
        editingUserId={user.id}
        editingUserData={user}
        onSuccessCallback={() => {
          // No need to invalidate - cache is already updated by the modal
          setEditModalOpen(false)
        }}
      />

      <UsageModal open={isUsageModalOpen} onClose={() => setUsageModalOpen(false)} username={user.username} />

      {/* SetOwnerModal: only for sudo admins */}
      {currentAdmin?.is_sudo && (
        <SetOwnerModal open={isSetOwnerModalOpen} onClose={() => setSetOwnerModalOpen(false)} username={user.username} currentOwner={user.admin?.username} onSuccess={refreshUserData} />
      )}

      {/* UserSubscriptionClientsModal */}
      <UserSubscriptionClientsModal isOpen={isSubscriptionClientsModalOpen} onOpenChange={setSubscriptionClientsModalOpen} username={user.username} />

      {/* UserAllIPsModal: only for sudo admins */}
      {currentAdmin?.is_sudo && <UserAllIPsModal isOpen={isUserAllIPsModalOpen} onOpenChange={setUserAllIPsModalOpen} username={user.username} />}
    </div>
  )
}

export default ActionButtons
