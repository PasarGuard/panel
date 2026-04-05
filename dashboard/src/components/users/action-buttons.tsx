import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useClipboard } from '@/hooks/use-clipboard'
import useDirDetection from '@/hooks/use-dir-detection'
import { type UseEditFormValues } from '@/components/forms/user-form'
import { useActiveNextPlan, useGetCurrentAdmin, useRemoveUser, useResetUserDataUsage, useRevokeUserSubscription, UserResponse, UsersResponse } from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Cpu, EllipsisVertical, Link2Off, ListStart, Network, Pencil, PieChart, QrCode, RefreshCcw, Trash2, User, Users } from 'lucide-react'
import { FC, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { CopyButton } from '@/components/common/copy-button'
import { normalizeExpireForEditForm } from '@/utils/userEditDateUtils'
import SubscriptionModal from '@/components/dialogs/subscription-modal'
import SetOwnerModal from '@/components/dialogs/set-owner-modal'
import UsageModal from '@/components/dialogs/usage-modal'
import UserModal from '@/components/dialogs/user-modal'
import { UserSubscriptionClientsModal } from '@/components/dialogs/user-subscription-clients-modal'
import UserAllIPsModal from '@/components/dialogs/user-all-ips-modal'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { invalidateUserMetricsQueries, upsertUserInUsersCache } from '@/utils/usersCache'

type ActionButtonsProps = {
  user: UserResponse
  isModalHost?: boolean
  renderActions?: boolean
}

export interface SubscribeLink {
  protocol: string
  link: string
  icon: string
}

const DOWNLOAD_ONLY_PROTOCOLS = ['clash', 'clash-meta', 'sing-box']

type ActionButtonsModalState = {
  subscribeUrl: string
  showSubscriptionModal: boolean
  isDeleteDialogOpen: boolean
  isResetUsageDialogOpen: boolean
  isRevokeSubDialogOpen: boolean
  isUsageModalOpen: boolean
  isSetOwnerModalOpen: boolean
  isActiveNextPlanModalOpen: boolean
  isSubscriptionClientsModalOpen: boolean
  isUserAllIPsModalOpen: boolean
}

const actionButtonsModalStateStore = new Map<number, ActionButtonsModalState>()
const actionButtonsUserStore = new Map<number, UserResponse>()
const actionButtonsModalStateListeners = new Map<number, Set<() => void>>()
const actionButtonsGlobalListeners = new Set<() => void>()
let actionButtonsGlobalStateVersion = 0

const createDefaultModalState = (user: UserResponse): ActionButtonsModalState => ({
  subscribeUrl: user.subscription_url || '',
  showSubscriptionModal: false,
  isDeleteDialogOpen: false,
  isResetUsageDialogOpen: false,
  isRevokeSubDialogOpen: false,
  isUsageModalOpen: false,
  isSetOwnerModalOpen: false,
  isActiveNextPlanModalOpen: false,
  isSubscriptionClientsModalOpen: false,
  isUserAllIPsModalOpen: false,
})

const ensureModalState = (user: UserResponse): ActionButtonsModalState => {
  if (!actionButtonsUserStore.has(user.id)) {
    actionButtonsUserStore.set(user.id, user)
  }

  const existing = actionButtonsModalStateStore.get(user.id)
  if (existing) return existing
  const initial = createDefaultModalState(user)
  actionButtonsModalStateStore.set(user.id, initial)
  return initial
}

const hasOpenModal = (state: ActionButtonsModalState) =>
  state.showSubscriptionModal ||
  state.isDeleteDialogOpen ||
  state.isResetUsageDialogOpen ||
  state.isRevokeSubDialogOpen ||
  state.isUsageModalOpen ||
  state.isSetOwnerModalOpen ||
  state.isActiveNextPlanModalOpen ||
  state.isSubscriptionClientsModalOpen ||
  state.isUserAllIPsModalOpen

const notifyGlobalListeners = () => {
  actionButtonsGlobalStateVersion += 1
  actionButtonsGlobalListeners.forEach(listener => listener())
}

const syncUserSnapshot = (user: UserResponse) => {
  const currentUser = actionButtonsUserStore.get(user.id)
  if (currentUser === user) return

  actionButtonsUserStore.set(user.id, user)

  const modalState = actionButtonsModalStateStore.get(user.id)
  if (modalState && hasOpenModal(modalState)) {
    actionButtonsModalStateListeners.get(user.id)?.forEach(listener => listener())
    notifyGlobalListeners()
  }
}

const subscribeModalState = (userId: number, listener: () => void) => {
  let listeners = actionButtonsModalStateListeners.get(userId)
  if (!listeners) {
    listeners = new Set()
    actionButtonsModalStateListeners.set(userId, listeners)
  }

  listeners.add(listener)

  return () => {
    const current = actionButtonsModalStateListeners.get(userId)
    if (!current) return
    current.delete(listener)
    if (current.size === 0) {
      actionButtonsModalStateListeners.delete(userId)
    }
  }
}

const subscribeGlobalModalState = (listener: () => void) => {
  actionButtonsGlobalListeners.add(listener)

  return () => {
    actionButtonsGlobalListeners.delete(listener)
  }
}

const getOpenModalUsers = (): UserResponse[] =>
  Array.from(actionButtonsModalStateStore.entries())
    .filter(([, state]) => hasOpenModal(state))
    .map(([userId]) => actionButtonsUserStore.get(userId))
    .filter((user): user is UserResponse => Boolean(user))

const getGlobalModalStateSnapshot = () => actionButtonsGlobalStateVersion

const updateModalState = (userId: number, updater: (prev: ActionButtonsModalState) => ActionButtonsModalState) => {
  const current = actionButtonsModalStateStore.get(userId)
  if (!current) return

  const next = updater(current)
  if (next === current) return

  actionButtonsModalStateStore.set(userId, next)
  actionButtonsModalStateListeners.get(userId)?.forEach(listener => listener())
  notifyGlobalListeners()
}

const ActionButtons: FC<ActionButtonsProps> = ({ user, isModalHost = true, renderActions = true }) => {
  const [subscribeLinks, setSubscribeLinks] = useState<SubscribeLink[]>([])
  const [isEditModalOpen, setEditModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null)
  const [isActionsMenuOpen, setActionsMenuOpen] = useState(false)
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const dir = useDirDetection()
  const configContentCacheRef = useRef<Record<string, string>>({})
  const pendingContentFetchRef = useRef<Record<string, Promise<string>>>({})
  const getModalStateSnapshot = useCallback(() => ensureModalState(user), [user])

  const modalState = useSyncExternalStore(
    useCallback(listener => subscribeModalState(user.id, listener), [user.id]),
    getModalStateSnapshot,
    getModalStateSnapshot,
  )

  const setModalState = useCallback(
    (updater: Partial<ActionButtonsModalState> | ((prev: ActionButtonsModalState) => ActionButtonsModalState)) => {
      ensureModalState(user)
      updateModalState(user.id, prev => (typeof updater === 'function' ? updater(prev) : { ...prev, ...updater }))
    },
    [user, user.id],
  )

  const {
    subscribeUrl,
    showSubscriptionModal,
    isDeleteDialogOpen,
    isResetUsageDialogOpen,
    isRevokeSubDialogOpen,
    isUsageModalOpen,
    isSetOwnerModalOpen,
    isActiveNextPlanModalOpen,
    isSubscriptionClientsModalOpen,
    isUserAllIPsModalOpen,
  } = modalState

  const setSubscribeUrl = useCallback((value: string) => setModalState({ subscribeUrl: value }), [setModalState])
  const setShowSubscriptionModal = useCallback((value: boolean) => setModalState({ showSubscriptionModal: value }), [setModalState])
  const setDeleteDialogOpen = useCallback((value: boolean) => setModalState({ isDeleteDialogOpen: value }), [setModalState])
  const setResetUsageDialogOpen = useCallback((value: boolean) => setModalState({ isResetUsageDialogOpen: value }), [setModalState])
  const setRevokeSubDialogOpen = useCallback((value: boolean) => setModalState({ isRevokeSubDialogOpen: value }), [setModalState])
  const setUsageModalOpen = useCallback((value: boolean) => setModalState({ isUsageModalOpen: value }), [setModalState])
  const setSetOwnerModalOpen = useCallback((value: boolean) => setModalState({ isSetOwnerModalOpen: value }), [setModalState])
  const setIsActiveNextPlanModalOpen = useCallback((value: boolean) => setModalState({ isActiveNextPlanModalOpen: value }), [setModalState])
  const setSubscriptionClientsModalOpen = useCallback((value: boolean) => setModalState({ isSubscriptionClientsModalOpen: value }), [setModalState])
  const setUserAllIPsModalOpen = useCallback((value: boolean) => setModalState({ isUserAllIPsModalOpen: value }), [setModalState])

  useEffect(() => {
    ensureModalState(user)
    syncUserSnapshot(user)
  }, [user])

  useEffect(() => {
    if (showSubscriptionModal) return
    const nextSubscribeUrl = user.subscription_url || ''
    if (nextSubscribeUrl === subscribeUrl) return
    setSubscribeUrl(nextSubscribeUrl)
  }, [showSubscriptionModal, subscribeUrl, user.subscription_url, setSubscribeUrl])

  const updateUserInCache = (updatedUser: UserResponse) => {
    upsertUserInUsersCache(queryClient, updatedUser)
    invalidateUserMetricsQueries(queryClient)
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
      expire: normalizeExpireForEditForm(user.expire),
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
      expire: normalizeExpireForEditForm(user.expire),
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
        { protocol: 'wireguard', link: `${subURL}/wireguard`, icon: '🛜' },
        { protocol: 'clash', link: `${subURL}/clash`, icon: '⚔️' },
        { protocol: 'clash-meta', link: `${subURL}/clash_meta`, icon: '🛡️' },
        { protocol: 'outline', link: `${subURL}/outline`, icon: '🔒' },
        { protocol: 'sing-box', link: `${subURL}/sing_box`, icon: '📦' },
      ]
      setSubscribeLinks(links)
    }
  }, [user.subscription_url])

  const { copy, copied } = useClipboard({ timeout: 1500 })

  useEffect(() => {
    configContentCacheRef.current = {}
    pendingContentFetchRef.current = {}
  }, [subscribeLinks])

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
      expire: normalizeExpireForEditForm(latestUser.expire),
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

  const isSafariDesktop = () => {
    const userAgent = navigator.userAgent
    return /Safari/.test(userAgent) && !/Chrome|Chromium|CriOS|Edg|OPR|Firefox|FxiOS/.test(userAgent)
  }

  const requiresSynchronousClipboard = () => {
    return isIOS() || isSafariDesktop()
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

  const fetchAndCacheContent = (link: string): Promise<string> => {
    const cachedContent = configContentCacheRef.current[link]
    if (cachedContent !== undefined) {
      return Promise.resolve(cachedContent)
    }

    const pendingRequest = pendingContentFetchRef.current[link]
    if (pendingRequest) {
      return pendingRequest
    }

    const request = fetchContent(link)
      .then(content => {
        configContentCacheRef.current[link] = content
        return content
      })
      .finally(() => {
        delete pendingContentFetchRef.current[link]
      })

    pendingContentFetchRef.current[link] = request
    return request
  }

  const prefetchCopyableConfigs = () => {
    subscribeLinks.forEach(({ protocol, link }) => {
      if (DOWNLOAD_ONLY_PROTOCOLS.includes(protocol)) return
      void fetchAndCacheContent(link).catch(error => {
        console.error('Failed to prefetch config content:', error)
      })
    })
  }

  const handleLinksCopy = async (link: string, type: string, icon: string) => {
    try {
      const cachedContent = configContentCacheRef.current[link]
      if (cachedContent !== undefined) {
        const copiedSuccessfully = await copy(cachedContent)
        if (copiedSuccessfully) {
          toast.success(`${icon} ${type} ${t('usersTable.copied', { defaultValue: 'Copied to clipboard' })}`)
        } else {
          toast.error(t('copyFailed', { defaultValue: 'Failed to copy content' }))
        }
        return
      }

      if (requiresSynchronousClipboard()) {
        void fetchAndCacheContent(link).catch(error => {
          console.error('Failed to fetch config content:', error)
        })
        toast.info(t('copyPrepareRetry', { defaultValue: 'Preparing configuration. Tap again to copy.' }))
        return
      }

      const content = await fetchAndCacheContent(link)
      const copiedSuccessfully = await copy(content)
      if (copiedSuccessfully) {
        toast.success(`${icon} ${type} ${t('usersTable.copied', { defaultValue: 'Copied to clipboard' })}`)
      } else {
        toast.error(t('copyFailed', { defaultValue: 'Failed to copy content' }))
      }
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
    if (DOWNLOAD_ONLY_PROTOCOLS.includes(type)) {
      handleConfigDownload(link, type)
    } else {
      handleLinksCopy(link, type, icon)
    }
  }

  return (
    <div onClick={renderActions ? (e => e.stopPropagation()) : undefined}>
      {renderActions && (
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
              showToast={true}
              toastSuccessMessage="userSettings.subscriptionUrlCopied"
            />
            <Tooltip>
              <DropdownMenu
                onOpenChange={open => {
                  if (open) prefetchCopyableConfigs()
                }}
              >
                <DropdownMenuTrigger asChild>
                  <TooltipTrigger asChild>
                    <Button size="icon" variant="ghost">
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </TooltipTrigger>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  {subscribeLinks.map((item, index) => (
                    <DropdownMenuItem dir='ltr' key={index} onClick={() => handleCopyOrDownload(item.link, item.protocol, item.icon)}>
                      <span className="mr-2">{item.icon}</span>
                      {item.protocol}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              <TooltipContent>{copied ? t('usersTable.copied') : t('usersTable.copyConfigs')}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <DropdownMenu modal={false} open={isActionsMenuOpen} onOpenChange={setActionsMenuOpen}>
            <DropdownMenuTrigger asChild>
              <Button size="icon" variant="ghost">
                <EllipsisVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              onPointerDownOutside={() => setActionsMenuOpen(false)}
              onInteractOutside={() => setActionsMenuOpen(false)}
              onEscapeKeyDown={() => setActionsMenuOpen(false)}
            >
              {/* Edit */}
              <DropdownMenuItem className="hidden md:flex" onSelect={handleEdit}>
                <Pencil className="mr-2 h-4 w-4" />
                <span>{t('edit')}</span>
              </DropdownMenuItem>

              {/* QR Code */}
              <DropdownMenuItem onSelect={onOpenSubscriptionModal}>
                <QrCode className="mr-2 h-4 w-4" />
                <span>{t('qrcodeDialog.title')}</span>
              </DropdownMenuItem>

              {/* Set Owner: only for sudo admins */}
              {currentAdmin?.is_sudo && (
                <DropdownMenuItem onSelect={handleSetOwner}>
                  <User className="mr-2 h-4 w-4" />
                  <span>{t('setOwnerModal.title')}</span>
                </DropdownMenuItem>
              )}

              {/* Copy Core Username for sudo admins */}
              {currentAdmin?.is_sudo && (
                <DropdownMenuItem onSelect={handleCopyCoreUsername}>
                  <Cpu className="mr-2 h-4 w-4" />
                  <span>{t('coreUsername')}</span>
                </DropdownMenuItem>
              )}

              <DropdownMenuSeparator />

              {/* Revoke Sub */}
              <DropdownMenuItem onSelect={handleRevokeSubscription}>
                <Link2Off className="mr-2 h-4 w-4" />
                <span>{t('userDialog.revokeSubscription')}</span>
              </DropdownMenuItem>

              {/* Reset Usage */}
              <DropdownMenuItem onSelect={handleResetUsage}>
                <RefreshCcw className="mr-2 h-4 w-4" />
                <span>{t('userDialog.resetUsage')}</span>
              </DropdownMenuItem>

              {/* Usage State */}
              <DropdownMenuItem onSelect={handleUsageState}>
                <PieChart className="mr-2 h-4 w-4" />
                <span>{t('userDialog.usage')}</span>
              </DropdownMenuItem>

              {/* Active Next Plan */}
              {user.next_plan && (
                <DropdownMenuItem onSelect={handleActiveNextPlan}>
                  <ListStart className="mr-2 h-4 w-4" />
                  <span>{t('usersTable.activeNextPlanSubmit')}</span>
                </DropdownMenuItem>
              )}

              {/* Subscription Info */}
              <DropdownMenuItem onSelect={() => setSubscriptionClientsModalOpen(true)}>
                <Users className="mr-2 h-4 w-4" />
                <span>{t('subscriptionClients.clients', { defaultValue: 'Clients' })}</span>
              </DropdownMenuItem>

              {/* View All IPs: only for sudo admins */}
              {currentAdmin?.is_sudo && (
                <DropdownMenuItem onSelect={() => setUserAllIPsModalOpen(true)}>
                  <Network className="mr-2 h-4 w-4" />
                  <span>{t('userAllIPs.ipAddresses', { defaultValue: 'IP addresses' })}</span>
                </DropdownMenuItem>
              )}

              <DropdownMenuSeparator />

              {/* Trash */}
              <DropdownMenuItem onSelect={handleDelete} className="text-red-600">
                <Trash2 className="mr-2 h-4 w-4" />
                <span>{t('remove')}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {isModalHost && (
        <>
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
              <AlertDialogFooter>
                <AlertDialogCancel onClick={() => setIsActiveNextPlanModalOpen(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
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
              <AlertDialogFooter>
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
              <AlertDialogFooter>
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
              <AlertDialogFooter>
                <AlertDialogCancel onClick={() => setRevokeSubDialogOpen(false)}>{t('usersTable.cancel')}</AlertDialogCancel>
                <AlertDialogAction onClick={confirmRevokeSubscription} disabled={revokeUserSubscriptionMutation.isPending}>
                  {t('revokeUserSub.title')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

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
        </>
      )}

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
    </div>
  )
}

export const ActionButtonsModalHost: FC = () => {
  const modalStateVersion = useSyncExternalStore(subscribeGlobalModalState, getGlobalModalStateSnapshot, getGlobalModalStateSnapshot)
  const usersWithOpenModals = useMemo(() => getOpenModalUsers(), [modalStateVersion])

  if (usersWithOpenModals.length === 0) return null

  return (
    <div className="hidden" aria-hidden="true">
      {usersWithOpenModals.map(user => (
        <ActionButtons key={`modal-host-${user.id}`} user={user} renderActions={false} />
      ))}
    </div>
  )
}

export default ActionButtons

