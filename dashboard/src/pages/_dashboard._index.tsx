import AdminStatisticsCard from '@/components/dashboard/admin-statistics-card'
import DashboardStatistics from '@/components/dashboard/dashboard-statistics'
import WorkersHealthCard from '@/components/dashboard/workers-health-card'
import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import AdminModal from '@/components/dialogs/admin-modal'
import { adminFormSchema, type AdminFormValuesInput } from '@/components/forms/admin-form'
import { coreConfigFormSchema, type CoreConfigFormValues } from '@/components/forms/core-config-form'
import GroupModal from '@/components/dialogs/group-modal'
import { groupFormSchema, type GroupFormValues } from '@/components/forms/group-form'
import HostModal from '@/components/dialogs/host-modal'
import NodeModal from '@/components/dialogs/node-modal'
import { nodeFormSchema, type NodeFormValues } from '@/components/forms/node-form'
import QuickActionsModal from '@/components/dialogs/shortcuts-modal'
import UserModal from '@/components/dialogs/user-modal'
import UserTemplateModal from '@/components/dialogs/user-template-modal'
import { userTemplateFormSchema, type UserTemplatesFromValueInput } from '@/components/forms/user-template-form'
import { HostFormValues } from '@/components/hosts/hosts-list'
import { Separator } from '@/components/ui/separator'
import { useAdmin } from '@/hooks/use-admin'
import { useClipboard } from '@/hooks/use-clipboard'
import type { AdminDetails, UserResponse } from '@/service/api'
import { useGetSystemStats } from '@/service/api'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import PageHeader from '@/components/layout/page-header'
import { type UseEditFormValues, type UseFormValues, getDefaultUserForm } from '@/components/forms/user-form'
// Lazy load CoreConfigModal to prevent Monaco Editor from loading until needed
const CoreConfigModal = lazy(() => import('@/components/dialogs/core-config-modal'))

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
  const { admin: currentAdmin } = useAdmin()
  const is_sudo = currentAdmin?.is_sudo || false

  const [selectedAdmin, setSelectedAdmin] = useState<AdminDetails | undefined>(totalAdmin)

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
      api_key: '',
      core_config_id: 1,
    },
  })

  const adminForm = useForm<AdminFormValuesInput>({
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
      notification_enable: {
        create: true,
        modify: true,
        delete: true,
        status_change: true,
        reset_data_usage: true,
        data_reset_by_next: true,
        subscription_revoked: true,
      },
    },
  })

  const templateForm = useForm<UserTemplatesFromValueInput>({
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
    },
  })

  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const { copy } = useClipboard()

  const refreshAllUserData = () => {
    queryClient.invalidateQueries({ queryKey: ['getUsers'] })
    queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
    queryClient.invalidateQueries({ queryKey: ['/api/users/'] })
  }

  const handleCreateUserSuccess = async (user: UserResponse) => {
    if (user.subscription_url) {
      const subURL = user.subscription_url.startsWith('/') ? window.location.origin + user.subscription_url : user.subscription_url
      await copy(subURL)
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

  // Only send admin_username if selectedAdmin is explicitly set and not 'Total'
  // When current admin is selected, we want to show their specific stats, not global stats
  const systemStatsParams = is_sudo && selectedAdmin && selectedAdmin.username !== 'Total' ? { admin_username: selectedAdmin.username } : undefined

  const { data: systemStatsData } = useGetSystemStats(systemStatsParams, {
    query: {
      refetchInterval: 5000,
    },
  })

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu animate-fade-in" style={{ animationDuration: '400ms' }}>
        <PageHeader title="dashboard" description="dashboardDescription" buttonIcon={Bookmark} buttonText="quickActions.title" onButtonClick={handleOpenQuickActions} />
        <Separator />
      </div>

      <div className="w-full px-3 pt-2 sm:px-4">
        <div className="flex flex-col gap-4 sm:gap-6">
          <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
            <DashboardStatistics systemData={systemStatsData} />
          </div>
          {is_sudo && (
            <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '180ms', animationFillMode: 'both' }}>
              <WorkersHealthCard />
            </div>
          )}
          <Separator className="my-4" />
          <div className="transform-gpu animate-slide-up" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
            {is_sudo ? (
              <>
                <AdminFilterCombobox
                  value={selectedAdmin?.username === 'Total' ? 'all' : (selectedAdmin?.username ?? 'all')}
                  onValueChange={username => {
                    if (username === 'all') {
                      setSelectedAdmin(totalAdmin)
                      return
                    }
                    if (currentAdmin?.username === username) {
                      setSelectedAdmin(currentAdmin)
                      return
                    }
                    setSelectedAdmin(prev => (prev?.username === username ? prev : { username, is_sudo: false }))
                  }}
                  onAdminSelect={admin => {
                    if (!admin) return
                    setSelectedAdmin(admin)
                  }}
                  className="relative mb-3 w-full max-w-xs sm:mb-4 sm:max-w-sm lg:max-w-md"
                />
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
      {isUserModalOpen && (
        <Suspense fallback={<div />}>
          <UserModal isDialogOpen={isUserModalOpen} onOpenChange={setUserModalOpen} form={userForm} editingUser={false} onSuccessCallback={handleCreateUserSuccess} />
        </Suspense>
      )}
      {isGroupModalOpen && (
        <Suspense fallback={<div />}>
          <GroupModal isDialogOpen={isGroupModalOpen} onOpenChange={setGroupModalOpen} form={groupForm} editingGroup={false} />
        </Suspense>
      )}
      {isHostModalOpen && (
        <Suspense fallback={<div />}>
          <HostModal isDialogOpen={isHostModalOpen} onOpenChange={setHostModalOpen} onSubmit={handleHostSubmit} form={hostForm} />
        </Suspense>
      )}
      {/* Only render NodeModal for sudo admins */}
      {is_sudo && isNodeModalOpen && (
        <Suspense fallback={<div />}>
          <NodeModal isDialogOpen={isNodeModalOpen} onOpenChange={setNodeModalOpen} form={nodeForm} editingNode={false} />
        </Suspense>
      )}
      {/* Only render AdminModal for sudo admins */}
      {is_sudo && isAdminModalOpen && (
        <Suspense fallback={<div />}>
          <AdminModal isDialogOpen={isAdminModalOpen} onOpenChange={setAdminModalOpen} form={adminForm} editingAdmin={false} editingAdminUserName="" />
        </Suspense>
      )}
      {isTemplateModalOpen && (
        <Suspense fallback={<div />}>
          <UserTemplateModal isDialogOpen={isTemplateModalOpen} onOpenChange={setTemplateModalOpen} form={templateForm} editingUserTemplate={false} />
        </Suspense>
      )}
      {/* Only render CoreConfigModal for sudo admins */}
      {is_sudo && isCoreModalOpen && (
        <Suspense fallback={<div />}>
          <CoreConfigModal isDialogOpen={isCoreModalOpen} onOpenChange={setCoreModalOpen} form={coreForm} editingCore={false} />
        </Suspense>
      )}
      {isQuickActionsModalOpen && (
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
      )}
    </div>
  )
}

export default Dashboard


