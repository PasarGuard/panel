import AdminStatisticsCard from '@/features/dashboard/components/admin-statistics-card'
import DashboardStatistics from '@/features/dashboard/components/dashboard-statistics'
import WorkersHealthCard from '@/features/dashboard/components/workers-health-card'
import AdminFilterCombobox from '@/components/common/admin-filter-combobox'
import AdminModal from '@/features/admins/dialogs/admin-modal'
import { adminFormDefaultValues, adminFormSchema, type AdminFormValuesInput } from '@/features/admins/forms/admin-form'
import { coreConfigFormDefaultValues, coreConfigFormSchema, type CoreConfigFormValues } from '@/features/nodes/forms/core-config-form'
import GroupModal from '@/features/groups/dialogs/group-modal'
import { groupFormDefaultValues, groupFormSchema, type GroupFormValues } from '@/features/groups/forms/group-form'
import HostModal from '@/features/hosts/dialogs/host-modal'
import NodeModal from '@/features/nodes/dialogs/node-modal'
import { nodeFormDefaultValues, nodeFormSchema, type NodeFormValues } from '@/features/nodes/forms/node-form'
import QuickActionsModal from '@/features/dashboard/dialogs/shortcuts-modal'
import UserModal from '@/features/users/dialogs/user-modal'
import UserTemplateModal from '@/features/templates/dialogs/user-template-modal'
import { createUserTemplateFormResolver, userTemplateFormDefaultValues, type UserTemplatesFromValueInput } from '@/features/templates/forms/user-template-form'
import { HostFormSchema, hostFormDefaultValues, type HostFormValues } from '@/features/hosts/forms/host-form'
import { Separator } from '@/components/ui/separator'
import { useAdmin } from '@/hooks/use-admin'
import { useClipboard } from '@/hooks/use-clipboard'
import type { AdminDetails, UserResponse } from '@/service/api'
import { useGetSystemResourceStats, useGetSystemUsersStats } from '@/service/api'
import { getInboundDetails } from '@/service/api'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { type Resolver, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import PageHeader from '@/components/layout/page-header'
import { type UseEditFormValues, type UseFormValues, getDefaultUserForm } from '@/features/users/forms/user-form'
import { hasPermission, hasScopeAll } from '@/utils/rbac'
// Lazy load CoreConfigModal to prevent Monaco Editor from loading until needed
const CoreConfigModal = lazy(() => import('@/features/nodes/dialogs/core-config-modal'))

type DashboardAdmin = Pick<AdminDetails, 'id' | 'username'>

const totalAdmin: DashboardAdmin = {
  username: 'Total',
  is_disabled: false,
  is_limited: false,
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
  const canReadAllUsers = hasScopeAll(currentAdmin, 'users', 'read')
  const canCreateUsers = hasPermission(currentAdmin, 'users', 'create')
  const canCreateGroups = hasPermission(currentAdmin, 'groups', 'create')
  const canCreateHosts = hasPermission(currentAdmin, 'hosts', 'create')
  const canCreateNodes = hasPermission(currentAdmin, 'nodes', 'create')
  const canCreateAdmins = hasPermission(currentAdmin, 'admins', 'create')
  const canCreateTemplates = hasPermission(currentAdmin, 'templates', 'create')
  const canCreateCores = hasPermission(currentAdmin, 'cores', 'create')
  const canReadNodeStats = hasPermission(currentAdmin, 'nodes', 'stats')
  const { t } = useTranslation()

  const [selectedAdmin, setSelectedAdmin] = useState<DashboardAdmin | undefined>(totalAdmin)

  const userForm = useForm<UseFormValues | UseEditFormValues>({
    defaultValues: getDefaultUserForm,
  })

  const groupForm = useForm<GroupFormValues>({
    resolver: zodResolver(groupFormSchema),
    defaultValues: groupFormDefaultValues,
  })

  const nodeForm = useForm<NodeFormValues>({
    resolver: zodResolver(nodeFormSchema),
    defaultValues: nodeFormDefaultValues,
  })

  const adminForm = useForm<AdminFormValuesInput>({
    resolver: zodResolver(adminFormSchema),
    defaultValues: adminFormDefaultValues,
  })

  const templateForm = useForm<UserTemplatesFromValueInput>({
    resolver: useMemo(() => createUserTemplateFormResolver(t), [t]),
    defaultValues: userTemplateFormDefaultValues,
  })

  const coreForm = useForm<CoreConfigFormValues>({
    resolver: zodResolver(coreConfigFormSchema),
    defaultValues: coreConfigFormDefaultValues,
  })

  const hostForm = useForm<HostFormValues>({
    resolver: zodResolver(HostFormSchema) as Resolver<HostFormValues>,
    defaultValues: hostFormDefaultValues,
  })

  const queryClient = useQueryClient()
  const { copy } = useClipboard()

  /** Match nodes list: delayed refetch so backend can settle after create/update (see nodes-list NodeModal onSuccess). */
  const handleNodeModalSuccess = () => {
    setTimeout(() => {
      void queryClient.refetchQueries({ queryKey: ['/api/nodes'] })
      void queryClient.refetchQueries({ queryKey: ['/api/nodes/simple'] })
    }, 2500)
  }

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
    if (!canCreateUsers) return
    userForm.reset()
    setUserModalOpen(true)
  }

  const handleCreateGroup = () => {
    if (!canCreateGroups) return
    groupForm.reset()
    setGroupModalOpen(true)
  }

  const handleCreateHost = () => {
    if (!canCreateHosts) return
    hostForm.reset()
    setHostModalOpen(true)
  }

  const handleCreateNode = () => {
    if (!canCreateNodes) return
    nodeForm.reset()
    setNodeModalOpen(true)
  }

  const handleCreateAdmin = () => {
    if (!canCreateAdmins) return
    adminForm.reset()
    setAdminModalOpen(true)
  }

  const handleCreateTemplate = () => {
    if (!canCreateTemplates) return
    templateForm.reset(userTemplateFormDefaultValues)
    setTemplateModalOpen(true)
  }

  const handleCreateCore = () => {
    if (!canCreateCores) return
    coreForm.reset()
    setCoreModalOpen(true)
  }

  const handleOpenQuickActions = () => {
    setQuickActionsModalOpen(true)
  }

  const handleHostSubmit = async () => {
    try {
      return { status: 200 }
    } catch (error: any) {
      console.error('Error submitting host:', error)
      toast.error(error?.message || 'Failed to create host')
      return { status: 500 }
    }
  }

  const { data: inboundDetails = [], isLoading: isLoadingInbounds } = useQuery({
    queryKey: ['getInboundDetailsQueryKey'],
    queryFn: ({ signal }) => getInboundDetails(signal),
    enabled: isHostModalOpen,
  })

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

  // Only user stats are admin-scoped. Resource stats are always global.
  const systemUsersStatsParams = canReadAllUsers && selectedAdmin && selectedAdmin.username !== 'Total' ? { admin_username: selectedAdmin.username } : undefined

  const { data: systemResourceStatsData } = useGetSystemResourceStats({
    query: {
      refetchInterval: 5000,
    },
  })

  const { data: systemUsersStatsData } = useGetSystemUsersStats(systemUsersStatsParams, {
    query: {
      refetchInterval: 5000,
    },
  })

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="animate-fade-in w-full transform-gpu" style={{ animationDuration: '400ms' }}>
        <PageHeader title="dashboard" description="dashboardDescription" buttonIcon={Bookmark} buttonText="quickActions.title" onButtonClick={handleOpenQuickActions} />
        <Separator />
      </div>

      <div className="w-full px-3 pt-2 sm:px-4">
        <div className="flex flex-col gap-4 sm:gap-6">
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}>
            <DashboardStatistics resourceData={systemResourceStatsData} usersData={systemUsersStatsData} />
          </div>
          {canReadNodeStats && (
            <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '180ms', animationFillMode: 'both' }}>
              <WorkersHealthCard />
            </div>
          )}
          <Separator className="my-4" />
          <div className="animate-slide-up transform-gpu" style={{ animationDuration: '500ms', animationDelay: '250ms', animationFillMode: 'both' }}>
            {canReadAllUsers ? (
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
                    setSelectedAdmin(prev => (prev?.username === username ? prev : { username, is_disabled: false, is_limited: false }))
                  }}
                  onAdminSelect={admin => {
                    if (!admin) return
                    setSelectedAdmin(admin)
                  }}
                  className="relative mb-3 w-full max-w-xs sm:mb-4 sm:max-w-sm lg:max-w-md"
                />
                {/* Show only the selected admin's card */}
                <div className="flex flex-col gap-3 sm:gap-4">
                  {selectedAdmin && <AdminStatisticsCard key={selectedAdmin.username} admin={selectedAdmin} systemStats={systemUsersStatsData} currentAdmin={currentAdmin} skipStatsFetch />}
                </div>
              </>
            ) : (
              <AdminStatisticsCard showAdminInfo={false} admin={currentAdmin} systemStats={systemUsersStatsData} currentAdmin={currentAdmin} skipStatsFetch />
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
          <HostModal isDialogOpen={isHostModalOpen} onOpenChange={setHostModalOpen} onSubmit={handleHostSubmit} form={hostForm} inboundDetails={inboundDetails} isLoadingInbounds={isLoadingInbounds} />
        </Suspense>
      )}
      {/* Only render NodeModal for sudo admins */}
      {canCreateNodes && isNodeModalOpen && (
        <Suspense fallback={<div />}>
          <NodeModal isDialogOpen={isNodeModalOpen} onOpenChange={setNodeModalOpen} form={nodeForm} editingNode={false} onSuccess={handleNodeModalSuccess} />
        </Suspense>
      )}
      {/* Only render AdminModal for sudo admins */}
      {canCreateAdmins && isAdminModalOpen && (
        <Suspense fallback={<div />}>
          <AdminModal isDialogOpen={isAdminModalOpen} onOpenChange={setAdminModalOpen} form={adminForm} editingAdmin={false} editingAdminId={undefined} />
        </Suspense>
      )}
      {isTemplateModalOpen && (
        <Suspense fallback={<div />}>
          <UserTemplateModal isDialogOpen={isTemplateModalOpen} onOpenChange={setTemplateModalOpen} form={templateForm} editingUserTemplate={false} />
        </Suspense>
      )}
      {/* Only render CoreConfigModal for sudo admins */}
      {canCreateCores && isCoreModalOpen && (
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
            canCreateUser={canCreateUsers}
            canCreateGroup={canCreateGroups}
            canCreateHost={canCreateHosts}
            canCreateNode={canCreateNodes}
            canCreateAdmin={canCreateAdmins}
            canCreateTemplate={canCreateTemplates}
            canCreateCore={canCreateCores}
          />
        </Suspense>
      )}
    </div>
  )
}

export default Dashboard
