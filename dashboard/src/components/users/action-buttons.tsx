import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useClipboard } from '@/hooks/use-clipboard'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { type UseEditFormValues } from '@/components/forms/user-form'
import { useActiveNextPlan, useGetCurrentAdmin, useRemoveUser, useResetUserDataUsage, useRevokeUserSubscription, UserResponse, UsersResponse } from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { Cpu, EllipsisVertical, ListStart, Network, Pencil, PieChart, QrCode, RefreshCcw, Trash2, User, Users, Copy, Check } from 'lucide-react'
import { FC, useCallback, useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import SubscriptionModal from '@/components/dialogs/subscription-modal'
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
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false)
  const [isEditModalOpen, setEditModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null)
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

  const updateUserInCache = (updatedUser: UserResponse) => {
    queryClient.setQueriesData<UsersResponse>(
      {
        queryKey: ['/api/users'],
        exact: false,
      },
      oldData => {
        if (!oldData) return oldData

        // Find and update the user in the users array
        const updatedUsers = oldData.users.map(u => (u.username === updatedUser.username ? updatedUser : u))

        return {
          ...oldData,
          users: updatedUsers,
        }
      },
    )

    // Still invalidate usage/stats queries as they may have changed
    queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
    queryClient.invalidateQueries({ queryKey: ['getUserStats'] })
    queryClient.invalidateQueries({ queryKey: ['getInboundStats'] })
    queryClient.invalidateQueries({ queryKey: ['getUserOnlineStats'] })
  }

  const removeUserMutation = useRemoveUser()
  const resetUserDataUsageMutation = useResetUserDataUsage({
    mutation: {
      onSuccess: (updatedUser) => {
        if (updatedUser) {
          updateUserInCache(updatedUser)
        }
      },
    },
  })
  const revokeUserSubscriptionMutation = useRevokeUserSubscription({
    mutation: {
      onSuccess: (updatedUser) => {
        if (updatedUser) {
          updateUserInCache(updatedUser)
        }
      },
    },
  })
  const activeNextMutation = useActiveNextPlan({
    mutation: {
      onSuccess: (updatedUser) => {
        if (updatedUser) {
          updateUserInCache(updatedUser)
        }
      },
    },
  })
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
      on_hold_timeout: user.on_hold_timeout || undefined,
      proxy_settings: user.proxy_settings || undefined,
      next_plan: user.next_plan
        ? {
          user_template_id: user.next_plan.user_template_id ? Number(user.next_plan.user_template_id) : undefined,
          data_limit: user.next_plan.data_limit ? Number(user.next_plan.data_limit) : 0,
          expire: user.next_plan.expire ? Number(user.next_plan.expire) : 0,
          add_remaining_traffic: user.next_plan.add_remaining_traffic || false,
        }
        : undefined,
    },
  })

  // Update form when user data changes
  useEffect(() => {
    const values: UseEditFormValues = {
      username: user.username,
      status: user.status === 'active' || user.status === 'on_hold' || user.status === 'disabled' ? (user.status as any) : 'active',
      data_limit: user.data_limit ? Math.round((Number(user.data_limit) / (1024 * 1024 * 1024)) * 100) / 100 : 0,
      expire: user.expire, // Pass raw expire value (timestamp)
      note: user.note || '',
      data_limit_reset_strategy: user.data_limit_reset_strategy || undefined,
      group_ids: user.group_ids || [],
      on_hold_expire_duration: user.on_hold_expire_duration || undefined,
      on_hold_timeout: user.on_hold_timeout || undefined,
      proxy_settings: user.proxy_settings || undefined,
      next_plan: user.next_plan
        ? {
          user_template_id: user.next_plan.user_template_id ? Number(user.next_plan.user_template_id) : undefined,
          data_limit: user.next_plan.data_limit ? Number(user.next_plan.data_limit) : 0,
          expire: user.next_plan.expire ? Number(user.next_plan.expire) : 0,
          add_remaining_traffic: user.next_plan.add_remaining_traffic || false,
        }
        : undefined,
    }

    // Update form with current values
    userForm.reset(values)
  }, [user, userForm])

  const onOpenSubscriptionModal = useCallback(() => {
    setSubscribeUrl(user.subscription_url ? user.subscription_url : '')
    setShowSubscriptionModal(true)
  }, [user.subscription_url])

  const onCloseSubscriptionModal = useCallback(() => {
    setSubscribeUrl('')
    setShowSubscriptionModal(false)
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

  // Refresh user data function (only for delete operations)
  const refreshUserData = () => {
    queryClient.invalidateQueries({ queryKey: ['/api/users'] })
  }

  // Handlers for menu items
  const handleEdit = () => {
    const cachedData = queryClient.getQueriesData<UsersResponse>({
      queryKey: ['/api/users'],
      exact: false,
    })

    let latestUser = user
    for (const [, data] of cachedData) {
      if (data?.users) {
        const foundUser = data.users.find(u => u.username === user.username)
        if (foundUser) {
          latestUser = foundUser
          break
        }
      }
    }

    // Update form with latest user data
    const values: UseEditFormValues = {
      username: latestUser.username,
      status: latestUser.status === 'active' || latestUser.status === 'on_hold' || latestUser.status === 'disabled' ? (latestUser.status as any) : 'active',
      data_limit: latestUser.data_limit ? Math.round((Number(latestUser.data_limit) / (1024 * 1024 * 1024)) * 100) / 100 : 0,
      expire: latestUser.expire,
      note: latestUser.note || '',
      data_limit_reset_strategy: latestUser.data_limit_reset_strategy || undefined,
      group_ids: latestUser.group_ids || [],
      on_hold_expire_duration: latestUser.on_hold_expire_duration || undefined,
      on_hold_timeout: latestUser.on_hold_timeout || undefined,
      proxy_settings: latestUser.proxy_settings || undefined,
      next_plan: latestUser.next_plan
        ? {
          user_template_id: latestUser.next_plan.user_template_id ? Number(latestUser.next_plan.user_template_id) : undefined,
          data_limit: latestUser.next_plan.data_limit ? Number(latestUser.next_plan.data_limit) : 0,
          expire: latestUser.next_plan.expire ? Number(latestUser.next_plan.expire) : 0,
          add_remaining_traffic: latestUser.next_plan.add_remaining_traffic || false,
        }
        : undefined,
    }

    userForm.reset(values)
    setSelectedUser(latestUser)
    setEditModalOpen(true)
  }

  const handleSetOwner = () => {
    setSetOwnerModalOpen(true)
  }

  const handleCopyCoreUsername = async () => {
    try {
      await navigator.clipboard.writeText(`${user.id}.${user.username}`)
      toast.success(t('usersTable.copied', { defaultValue: 'Copied to clipboard' }))
    } catch (error) {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy content' }))
    }
  }

  const handleRevokeSubscription = () => {
    setRevokeSubDialogOpen(true)
  }

  const confirmRevokeSubscription = async () => {
    try {
      await revokeUserSubscriptionMutation.mutateAsync({ username: user.username })
      toast.success(t('userDialog.revokeSubSuccess', { name: user.username }))
      setRevokeSubDialogOpen(false)
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
      setIsActiveNextPlanModalOpen(false)
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

  const buildDashboardFallbackUrl = (url: string): string | null => {
    try {
      const parsedUrl = new URL(url, window.location.origin)
      if (parsedUrl.origin === window.location.origin) return null

      return `${window.location.origin}${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`
    } catch (error) {
      console.error('Failed to build fallback url:', error)
      return null
    }
  }

  async function fetchWithDashboardFallback<T>(url: string, parser: (response: Response) => Promise<T>): Promise<T> {
    const attemptFetch = async (targetUrl: string) => {
      const response = await fetch(targetUrl)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return parser(response)
    }

    try {
      return await attemptFetch(url)
    } catch (primaryError) {
      const fallbackUrl = buildDashboardFallbackUrl(url)
      if (fallbackUrl) {
        try {
          return await attemptFetch(fallbackUrl)
        } catch (fallbackError) {
          console.error('Fallback fetch failed:', fallbackError)
        }
      }
      throw primaryError
    }
  }

  const fetchContent = (url: string): Promise<string> => fetchWithDashboardFallback(url, response => response.text())

  const fetchBlob = (url: string): Promise<Blob> => fetchWithDashboardFallback(url, response => response.blob())

  const handleLinksCopy = async (link: string, type: string, icon: string) => {
    try {
      const content = await fetchContent(link)
      copy(content)
      toast.success(`${icon} ${type} ${t('usersTable.copied', { defaultValue: 'Copied to clipboard' })}`)
    } catch (error) {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy content' }))
    }
  }

  const handleConfigDownload = async (link: string, type: string) => {
    try {
      if (isIOS()) {
        // iOS: open in new tab or show content
        const newWindow = window.open(link, '_blank')
        if (!newWindow) {
          const content = await fetchContent(link)
          showManualCopyAlert(content, 'url')
        } else {
          toast.success(t('downloadSuccess', { defaultValue: 'Configuration opened in new tab' }))
        }
      } else {
        // Non-iOS: regular download
        const blob = await fetchBlob(link)
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${user.username}-${type}.yaml`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        toast.success(t('usersTable.downloadStarted', { defaultValue: 'Download started' }))
      }
    } catch (error) {
      toast.error(t('downloadFailed', { defaultValue: 'Failed to download config' }))
    }
  }

  const handleCopyOrDownload = (link: string, type: string, icon: string) => {
    if (['clash', 'clash-meta', 'sing-box'].includes(type)) {
      handleConfigDownload(link, type)
    } else {
      handleLinksCopy(link, type, icon)
    }
  }

  return (
    <div onClick={e => e.stopPropagation()}>
      <div className="flex items-center justify-end">
        <Button size="icon" variant="ghost" onClick={handleEdit} className="md:hidden">
          <Pencil className="h-4 w-4" />
        </Button>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="ghost" onClick={onOpenSubscriptionModal}>
                <QrCode className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('subscriptionModal.title', { username: user.username, defaultValue: "{{username}}'s Subscription" })}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon" variant="ghost">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align={dir === 'rtl' ? 'start' : 'end'}>
            {subscribeLinks.map((item, index) => (
              <DropdownMenuItem key={index} onClick={() => handleCopyOrDownload(item.link, item.protocol, item.icon)}>
                <span className="mr-2">{item.icon}</span>
                {item.protocol}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
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

      {/* Subscription Modal */}
      {showSubscriptionModal && subscribeUrl && (
        <SubscriptionModal 
          subscribeUrl={subscribeUrl} 
          username={user.username} 
          onCloseModal={onCloseSubscriptionModal} 
        />
      )}

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
      {selectedUser && (
        <UserModal
          isDialogOpen={isEditModalOpen}
          onOpenChange={(open) => {
            setEditModalOpen(open)
            if (!open) {
              setSelectedUser(null)
            }
          }}
          form={userForm}
          editingUser={true}
          editingUserId={selectedUser.id}
          editingUserData={selectedUser}
          onSuccessCallback={() => {
            // No need to invalidate - cache is already updated by the modal
            setEditModalOpen(false)
            setSelectedUser(null)
          }}
        />
      )}

      <UsageModal open={isUsageModalOpen} onClose={() => setUsageModalOpen(false)} username={user.username} />

      {/* SetOwnerModal: only for sudo admins */}
      {currentAdmin?.is_sudo && (
        <SetOwnerModal
          open={isSetOwnerModalOpen}
          onClose={() => setSetOwnerModalOpen(false)}
          username={user.username}
          currentOwner={user.admin?.username}
          onSuccess={(updatedUser?: UserResponse) => {
            if (updatedUser) {
              updateUserInCache(updatedUser)
            }
          }}
        />
      )}

      {/* UserSubscriptionClientsModal */}
      <UserSubscriptionClientsModal isOpen={isSubscriptionClientsModalOpen} onOpenChange={setSubscriptionClientsModalOpen} username={user.username} />

      {/* UserAllIPsModal: only for sudo admins */}
      {currentAdmin?.is_sudo && <UserAllIPsModal isOpen={isUserAllIPsModalOpen} onOpenChange={setUserAllIPsModalOpen} username={user.username} />}
    </div>
  )
}

export default ActionButtons

