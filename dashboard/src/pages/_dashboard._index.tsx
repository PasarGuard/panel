import AdminStatisticsCard from '@/components/dashboard/admin-statistics-card'
import DashboardStatistics from '@/components/dashboard/DashboardStatistics'
import AdminModal, { adminFormSchema, AdminFormValues } from '@/components/dialogs/AdminModal'
import { coreConfigFormSchema, CoreConfigFormValues } from '@/components/dialogs/CoreConfigModal'
import GroupModal, { groupFormSchema, GroupFormValues } from '@/components/dialogs/GroupModal'
import HostModal from '@/components/dialogs/HostModal'
import NodeModal, { nodeFormSchema, NodeFormValues } from '@/components/dialogs/NodeModal'
import QuickActionsModal from '@/components/dialogs/ShortcutsModal'
import UserModal from '@/components/dialogs/UserModal'
import UserTemplateModal, { userTemplateFormSchema, UserTemplatesFromValue } from '@/components/dialogs/UserTemplateModal'
import { HostFormValues } from '@/components/hosts/Hosts'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import useDirDetection from '@/hooks/use-dir-detection'
import { useClipboard } from '@/hooks/use-clipboard'
import { cn } from '@/lib/utils'
import type { AdminDetails, UserResponse } from '@/service/api'
import { useGetAdmins, useGetCurrentAdmin, useGetSystemStats } from '@/service/api'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { debounce } from 'es-toolkit'
import { Bookmark, Check, ChevronDown, Loader2, Sigma, UserCog, UserRound } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { getDefaultUserForm, UseEditFormValues, UseFormValues } from './_dashboard.users'
// Lazy load CoreConfigModal to prevent Monaco Editor from loading until needed
const CoreConfigModal = lazy(() => import('@/components/dialogs/CoreConfigModal'))

const PAGE_SIZE = 20

const totalAdmin: AdminDetails = {
  username: 'Total',
  is_sudo: false,
}

const Dashboard = () => {
  const [isUserModalOpen, setUserModalOpen] = useState(false)
  const [isGroupModalOpen, setGroupModalOpen] = useState(false)
  const [isHostModalOpen, setHostModalOpen] = useState(false)
  const [isNodeModalOpen, setNodeModalOpen] = useState(false)
  const [isAdminModalOpen, setAdminModalOpen] = useState(false)
  const [isTemplateModalOpen, setTemplateModalOpen] = useState(false)
  const [isCoreModalOpen, setCoreModalOpen] = useState(false)
  const [isQuickActionsModalOpen, setQuickActionsModalOpen] = useState(false)
  const { data: currentAdmin } = useGetCurrentAdmin()
  const is_sudo = currentAdmin?.is_sudo || false

  // Admin search state - only for sudo admins
  const [selectedAdmin, setSelectedAdmin] = useState<AdminDetails | undefined>(totalAdmin)
  const [adminSearch, setAdminSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [admins, setAdmins] = useState<AdminDetails[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  // Debounced search - only for sudo admins
  const debouncedSearch = useCallback(
    debounce((value: string) => {
      if (!is_sudo) return // Don't run for non-sudo admins
      setOffset(0)
      setAdmins([])
      setHasMore(true)
      setAdminSearch(value)
    }, 300),
    [is_sudo],
  )

  // In the useGetAdmins call, only set username if searching and not current admin or 'system'
  let usernameParam: string | undefined = undefined
  if (is_sudo && adminSearch && adminSearch !== 'system' && adminSearch !== currentAdmin?.username) {
    usernameParam = adminSearch
  }

  // Only fetch admins for sudo admins
  const { data: fetchedAdmins = [] } = useGetAdmins(
    {
      limit: PAGE_SIZE,
      offset,
      ...(usernameParam ? { username: usernameParam } : {}),
    },
    {
      query: {
        enabled: is_sudo, // Only fetch admins for sudo admins
      },
    },
  )

  // When fetchedAdmins changes, update admins and hasMore - only for sudo admins
  useEffect(() => {
    if (!is_sudo) return // Don't run for non-sudo admins
    if (fetchedAdmins) {
      setAdmins(prev => (offset === 0 ? fetchedAdmins : [...prev, ...fetchedAdmins]))
      setHasMore(fetchedAdmins.length === PAGE_SIZE)
      setIsLoading(false)
    }
  }, [fetchedAdmins, offset, is_sudo])

  // Infinite scroll - only for sudo admins
  const handleScroll = useCallback(() => {
    if (!is_sudo || !listRef.current || isLoading || !hasMore) return
    const { scrollTop, scrollHeight, clientHeight } = listRef.current
    if (scrollHeight - scrollTop - clientHeight < 100) {
      setIsLoading(true)
      setOffset(prev => prev + PAGE_SIZE)
    }
  }, [isLoading, hasMore, is_sudo])

  useEffect(() => {
    if (!is_sudo) return // Don't add scroll listeners for non-sudo admins
    const el = listRef.current
    if (!el) return
    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [handleScroll, is_sudo])

  const userForm = useForm<UseFormValues | UseEditFormValues>({
    defaultValues: getDefaultUserForm,
  })

  const groupForm = useForm<GroupFormValues>({
    resolver: zodResolver(groupFormSchema),
    defaultValues: {
      name: '',
      inbound_tags: [],
      is_disabled: false,
    },
  })

  const nodeForm = useForm<NodeFormValues>({
    resolver: zodResolver(nodeFormSchema),
    defaultValues: {
      name: '',
      address: '',
      port: 62050,
      usage_coefficient: 1,
      connection_type: 'grpc' as any,
      server_ca: '',
      keep_alive: 60,
      keep_alive_unit: 'seconds',
      max_logs: 1000,
      api_key: '',
      core_config_id: 1,
      gather_logs: true,
    },
  })

  const adminForm = useForm<AdminFormValues>({
    resolver: zodResolver(adminFormSchema),
    defaultValues: {
      username: '',
      password: '',
      passwordConfirm: '',
      is_sudo: false,
      is_disabled: false,
      discord_webhook: '',
      sub_domain: '',
      sub_template: '',
      support_url: '',
      telegram_id: undefined,
      profile_title: '',
      discord_id: undefined,
    },
  })

  const templateForm = useForm<UserTemplatesFromValue>({
    resolver: zodResolver(userTemplateFormSchema),
    defaultValues: {
      name: '',
      status: 'active' as any,
      username_prefix: '',
      username_suffix: '',
      data_limit: undefined,
      expire_duration: undefined,
      on_hold_timeout: undefined,
      method: undefined,
      flow: undefined,
      groups: [],
      data_limit_reset_strategy: undefined,
    },
  })

  const coreForm = useForm<CoreConfigFormValues>({
    resolver: zodResolver(coreConfigFormSchema),
    defaultValues: {
      name: '',
      config: '',
      fallback_id: [],
      excluded_inbound_ids: [],
      public_key: '',
      private_key: '',
      restart_nodes: true,
    },
  })

  const hostForm = useForm<HostFormValues, any, HostFormValues>({
    defaultValues: {
      inbound_tag: '',
      status: [],
      remark: '',
      address: [],
      port: 443,
      sni: [],
      host: [],
      path: '',
      priority: 1,
      alpn: undefined,
      fingerprint: undefined,
      security: 'none',
      allowinsecure: false,
      is_disabled: false,
      random_user_agent: false,
      use_sni_as_host: false,
      mux_settings: undefined,
      fragment_settings: undefined,
      ss2022_relay_inbound_tags: [],
    },
  })

  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const dir = useDirDetection()
  const { copy } = useClipboard()

  const refreshAllUserData = () => {
    queryClient.invalidateQueries({ queryKey: ['getUsers'] })
    queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
    queryClient.invalidateQueries({ queryKey: ['/api/users/'] })
  }

  const handleCreateUserSuccess = (user: UserResponse) => {
    if (user.subscription_url) {
      copy(user.subscription_url)
      toast.success(t('userSettings.subscriptionUrlCopied'))
    }
    refreshAllUserData()
  }

  const handleCreateUser = () => {
    userForm.reset()
    setUserModalOpen(true)
  }

  const handleCreateGroup = () => {
    groupForm.reset()
    setGroupModalOpen(true)
  }

  const handleCreateHost = () => {
    hostForm.reset()
    setHostModalOpen(true)
  }

  const handleCreateNode = () => {
    nodeForm.reset()
    setNodeModalOpen(true)
  }

  const handleCreateAdmin = () => {
    adminForm.reset()
    setAdminModalOpen(true)
  }

  const handleCreateTemplate = () => {
    templateForm.reset()
    setTemplateModalOpen(true)
  }

  const handleCreateCore = () => {
    coreForm.reset()
    setCoreModalOpen(true)
  }

  const handleOpenQuickActions = () => {
    setQuickActionsModalOpen(true)
  }

  const handleHostSubmit = async () => {
    try {
      // For now, just pass the form data directly to the modal
      // The modal will handle the complex type conversions
      return { status: 200 }
    } catch (error: any) {
      console.error('Error submitting host:', error)
      toast.error(error?.message || 'Failed to create host')
      return { status: 500 }
    }
  }

  // Keyboard shortcuts for dashboard actions
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Ctrl/Cmd + N - Create new user
      if (event.key === 'n' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        handleCreateUser()
      }
      // Ctrl/Cmd + R - Refresh data
      if (event.key === 'r' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        refreshAllUserData()
      }
      // Ctrl/Cmd + K - Open quick actions modal
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        handleOpenQuickActions()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Auto-select current admin when it loads - only for sudo admins
  useEffect(() => {
    if (is_sudo && currentAdmin && !selectedAdmin) {
      setSelectedAdmin(totalAdmin)
    }
  }, [currentAdmin, selectedAdmin, is_sudo])

  // Only send admin_username if selectedAdmin is explicitly set and not 'Total'
  // When current admin is selected, we want to show their specific stats, not global stats
  const systemStatsParams = is_sudo && selectedAdmin && selectedAdmin.username !== 'Total' ? { admin_username: selectedAdmin.username } : undefined

  const { data: systemStatsData } = useGetSystemStats(systemStatsParams, {
    query: {
      refetchInterval: 5000,
    },
  })

  // Filter out current admin and 'system' - only for sudo admins
  const filteredAdmins = is_sudo ? admins.filter(admin => admin.username !== currentAdmin?.username && admin.username !== 'system') : []

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <div className="mx-auto flex w-full flex-row items-start justify-between gap-2 px-3 py-3 sm:gap-4 sm:px-4 md:py-4 lg:pt-6">
          <div className="flex min-w-0 flex-1 flex-col gap-y-1 pr-2 sm:pr-0">
            <h1 className="truncate text-base font-medium sm:text-lg lg:text-xl">{t('dashboard')}</h1>
            <span className="whitespace-normal text-xs leading-relaxed text-muted-foreground sm:text-sm">{t('dashboardDescription')}</span>
          </div>
          <div className="flex flex-shrink-0 gap-1 sm:gap-2">
            <Button onClick={handleOpenQuickActions} size="sm" variant="outline" className="hidden text-xs sm:flex sm:text-sm">
              <Bookmark className="h-3 w-3 sm:h-4 sm:w-4" />
              <span className="hidden lg:inline">{t('quickActions.title')}</span>
            </Button>
            <Button onClick={handleOpenQuickActions} size="sm" variant="outline" className="p-2 sm:hidden">
              <Bookmark className="h-3 w-3" />
            </Button>
          </div>
        </div>
        <Separator />
      </div>

      <div className="w-full px-3 pt-2 sm:px-4">
        <div className="flex flex-col gap-4 sm:gap-6">
          <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
            <DashboardStatistics systemData={systemStatsData} />
          </div>
          <Separator className="my-4" />
          <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
            {is_sudo ? (
              <>
                {/* Admin Switcher for Sudo */}
                <div className="relative mb-3 w-full max-w-xs sm:mb-4 sm:max-w-sm lg:max-w-md" dir={dir}>
                  <Popover open={dropdownOpen} onOpenChange={setDropdownOpen}>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className={cn('h-8 w-full justify-between px-2 transition-colors hover:bg-muted/50 sm:h-9 sm:px-3', 'min-w-0 text-xs font-medium sm:text-sm')}>
                        <div className={cn('flex min-w-0 flex-1 items-center gap-1 sm:gap-2', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}>
                          <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                            <AvatarFallback className="bg-muted text-xs font-medium">
                              {selectedAdmin?.username === 'Total' ? <Sigma className="h-3 w-3" /> : selectedAdmin?.username?.charAt(0).toUpperCase() || '?'}
                            </AvatarFallback>
                          </Avatar>
                          <span className="truncate text-xs sm:text-sm">{selectedAdmin?.username === 'Total' ? t('admins.total') : selectedAdmin?.username || t('advanceSearch.selectAdmin')}</span>
                          {selectedAdmin && selectedAdmin.username !== 'Total' && (
                            <div className="flex-shrink-0">{selectedAdmin.is_sudo ? <UserCog className="h-3 w-3 text-primary" /> : <UserRound className="h-3 w-3 text-primary" />}</div>
                          )}
                        </div>
                        <ChevronDown className="ml-1 h-3 w-3 flex-shrink-0 text-muted-foreground" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-64 p-1 sm:w-72 lg:w-80" sideOffset={4} align={dir === 'rtl' ? 'end' : 'start'}>
                      <Command>
                        <CommandInput placeholder={t('search')} onValueChange={debouncedSearch} className="mb-1 h-7 text-xs sm:h-8 sm:text-sm" />
                        <CommandList ref={listRef}>
                          <CommandEmpty>
                            <div className="py-3 text-center text-xs text-muted-foreground sm:py-4 sm:text-sm">{t('noAdminsFound') || 'No admins found'}</div>
                          </CommandEmpty>

                          <CommandItem
                            onSelect={() => {
                              setSelectedAdmin(totalAdmin)
                              setDropdownOpen(false)
                            }}
                            className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                          >
                            <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                              <AvatarFallback className="bg-primary/10 text-xs font-medium">
                                <Sigma className="h-3 w-3" />
                              </AvatarFallback>
                            </Avatar>
                            <span className="flex-1 truncate">{t('admins.total')}</span>
                            <div className="flex flex-shrink-0 items-center gap-1">{selectedAdmin?.username === 'Total' && <Check className="h-3 w-3 text-primary" />}</div>
                          </CommandItem>

                          {currentAdmin && (
                            <CommandItem
                              onSelect={() => {
                                setSelectedAdmin(currentAdmin)
                                setDropdownOpen(false)
                              }}
                              className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                            >
                              <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                                <AvatarFallback className="bg-primary/10 text-xs font-medium">{currentAdmin.username.charAt(0).toUpperCase()}</AvatarFallback>
                              </Avatar>
                              <span className="flex-1 truncate">{currentAdmin.username}</span>
                              <div className="flex flex-shrink-0 items-center gap-1">
                                {currentAdmin.is_sudo ? <UserCog className="h-3 w-3 text-primary" /> : <UserRound className="h-3 w-3 text-primary" />}
                                {selectedAdmin?.username === currentAdmin.username && <Check className="h-3 w-3 text-primary" />}
                              </div>
                            </CommandItem>
                          )}

                          {filteredAdmins.map(admin => (
                            <CommandItem
                              key={admin.username}
                              onSelect={() => {
                                setSelectedAdmin(admin)
                                setDropdownOpen(false)
                              }}
                              className={cn('flex min-w-0 items-center gap-2 px-2 py-1.5 text-xs sm:text-sm', dir === 'rtl' ? 'flex-row-reverse' : 'flex-row')}
                            >
                              <Avatar className="h-4 w-4 flex-shrink-0 sm:h-5 sm:w-5">
                                <AvatarFallback className="bg-muted text-xs font-medium">{admin.username.charAt(0).toUpperCase()}</AvatarFallback>
                              </Avatar>
                              <span className="flex-1 truncate">{admin.username}</span>
                              <div className="flex flex-shrink-0 items-center gap-1">
                                {admin.is_sudo ? <UserCog className="h-3 w-3 text-primary" /> : <UserRound className="h-3 w-3 text-primary" />}
                                {selectedAdmin?.username === admin.username && <Check className="h-3 w-3 text-primary" />}
                              </div>
                            </CommandItem>
                          ))}

                          {isLoading && (
                            <div className="flex justify-center py-2">
                              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                            </div>
                          )}
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>
                {/* Show only the selected admin's card */}
                <div className="flex flex-col gap-3 sm:gap-4">
                  {selectedAdmin && <AdminStatisticsCard key={selectedAdmin.username} admin={selectedAdmin} systemStats={systemStatsData} currentAdmin={currentAdmin} />}
                </div>
              </>
            ) : (
              <AdminStatisticsCard showAdminInfo={false} admin={currentAdmin} systemStats={systemStatsData} currentAdmin={currentAdmin} />
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      <Suspense fallback={<div />}>
        <UserModal isDialogOpen={isUserModalOpen} onOpenChange={setUserModalOpen} form={userForm} editingUser={false} onSuccessCallback={handleCreateUserSuccess} />
      </Suspense>
      <Suspense fallback={<div />}>
        <GroupModal isDialogOpen={isGroupModalOpen} onOpenChange={setGroupModalOpen} form={groupForm} editingGroup={false} />
      </Suspense>
      <Suspense fallback={<div />}>
        <HostModal isDialogOpen={isHostModalOpen} onOpenChange={setHostModalOpen} onSubmit={handleHostSubmit} form={hostForm} />
      </Suspense>
      {/* Only render NodeModal for sudo admins */}
      {is_sudo && (
        <Suspense fallback={<div />}>
          <NodeModal isDialogOpen={isNodeModalOpen} onOpenChange={setNodeModalOpen} form={nodeForm} editingNode={false} />
        </Suspense>
      )}
      {/* Only render AdminModal for sudo admins */}
      {is_sudo && (
        <Suspense fallback={<div />}>
          <AdminModal isDialogOpen={isAdminModalOpen} onOpenChange={setAdminModalOpen} form={adminForm} editingAdmin={false} editingAdminUserName="" />
        </Suspense>
      )}
      <Suspense fallback={<div />}>
        <UserTemplateModal isDialogOpen={isTemplateModalOpen} onOpenChange={setTemplateModalOpen} form={templateForm} editingUserTemplate={false} />
      </Suspense>
      {/* Only render CoreConfigModal for sudo admins */}
      {is_sudo && (
        <Suspense fallback={<div />}>
          <CoreConfigModal isDialogOpen={isCoreModalOpen} onOpenChange={setCoreModalOpen} form={coreForm} editingCore={false} />
        </Suspense>
      )}
      <Suspense fallback={<div />}>
        <QuickActionsModal
          open={isQuickActionsModalOpen}
          onClose={() => setQuickActionsModalOpen(false)}
          onCreateUser={handleCreateUser}
          onCreateGroup={handleCreateGroup}
          onCreateHost={handleCreateHost}
          onCreateNode={handleCreateNode}
          onCreateAdmin={handleCreateAdmin}
          onCreateTemplate={handleCreateTemplate}
          onCreateCore={handleCreateCore}
          isSudo={is_sudo}
        />
      </Suspense>
    </div>
  )
}

export default Dashboard
