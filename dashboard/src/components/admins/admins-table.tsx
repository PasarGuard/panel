import { useTranslation } from 'react-i18next'
import type { AdminDetails } from '@/service/api'
import {
  useActivateAllDisabledUsers,
  useBulkActivateAllDisabledUsers,
  useBulkDeleteAdmins,
  useBulkDisableAdmins,
  useBulkDisableAllActiveUsers,
  useBulkEnableAdmins,
  useBulkRemoveAllUsers,
  useBulkResetAdminsUsage,
  useDisableAllActiveUsers,
  useGetAdmins,
  useRemoveAllUsers,
} from '@/service/api'
import { DataTable } from './data-table'
import { setupColumns } from './columns'
import { Filters } from './filters'
import { useEffect, useState, useRef, useCallback } from 'react'
import { PaginationControls } from './filters'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import useDirDetection from '@/hooks/use-dir-detection'
import { Checkbox } from '@/components/ui/checkbox'
import { getAdminsPerPageLimitSize, setAdminsPerPageLimitSize } from '@/utils/userPreferenceStorage'
import { toast } from 'sonner'
import { useAdmin } from '@/hooks/use-admin'
import { patchAdminInAdminsCache } from '@/utils/adminsCache'
import { useQueryClient } from '@tanstack/react-query'
import { BulkActionItem, BulkActionsBar } from '@/components/users/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/components/users/bulk-action-alert-dialog'
import { Power, PowerOff, RefreshCw, Trash2, UserCheck, UserMinus, UserX } from 'lucide-react'

interface AdminFilters {
  sort?: string
  username?: string | null
  limit: number
  offset: number
}

interface AdminsTableProps {
  onEdit: (admin: AdminDetails) => void
  onDelete: (admin: AdminDetails) => void
  onToggleStatus: (admin: AdminDetails, checked: boolean) => void
  onResetUsage: (adminUsername: string) => void
  onTotalAdminsChange?: (counts: { total: number; active: number; disabled: number } | null) => void
}

type BulkUsersActionType = 'disable' | 'activate'
type BulkAdminActionType = 'delete' | 'reset' | 'disable' | 'enable' | 'disableUsers' | 'activateUsers' | 'removeUsers'

interface BulkActionDialogConfig {
  title: string
  description: string
  actionLabel: string
  onConfirm: () => Promise<void>
  isPending: boolean
  destructive?: boolean
}

const DeleteAlertDialog = ({ admin, isOpen, onClose, onConfirm }: { admin: AdminDetails; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('admins.deleteAdmin')}</AlertDialogTitle>
          <AlertDialogDescription>
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('deleteAdmin.prompt', { name: admin.username }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const ToggleAdminStatusModal = ({ admin, isOpen, onClose, onConfirm }: { admin: AdminDetails; isOpen: boolean; onClose: () => void; onConfirm: (clicked: boolean) => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [adminUsersToggle, setAdminUsersToggle] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      setAdminUsersToggle(false)
    }
  }, [isOpen])

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t(admin.is_disabled ? 'admin.enable' : 'admin.disable')}</AlertDialogTitle>
          <AlertDialogDescription className="flex items-center gap-2">
            <Checkbox checked={adminUsersToggle} onCheckedChange={() => setAdminUsersToggle(!adminUsersToggle)} />
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t(admin.is_disabled ? 'activeUsers.prompt' : 'disableUsers.prompt', { name: admin.username }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={() => onConfirm(adminUsersToggle)}>{t('confirm')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const ResetUsersUsageConfirmationDialog = ({ adminUsername, isOpen, onClose, onConfirm }: { adminUsername: string; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('admins.resetUsersUsage')}</AlertDialogTitle>
          <AlertDialogDescription className="flex items-center gap-2">
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('resetUsersUsage.prompt', { name: adminUsername }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t('confirm')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const RemoveAllUsersConfirmationDialog = ({ adminUsername, isOpen, onClose, onConfirm }: { adminUsername: string; isOpen: boolean; onClose: () => void; onConfirm: () => void }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('admins.removeAllUsers')}</AlertDialogTitle>
          <AlertDialogDescription className="flex items-center gap-2">
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t('removeAllUsers.prompt', { name: adminUsername }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t('confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const BulkUsersStatusConfirmationDialog = ({
  adminUsername,
  actionType,
  isOpen,
  onClose,
  onConfirm,
}: {
  adminUsername: string
  actionType: BulkUsersActionType
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
}) => {
  const { t } = useTranslation()
  const dir = useDirDetection()

  const titleKey = actionType === 'disable' ? 'admins.disableAllActiveUsers' : 'admins.activateAllDisabledUsers'
  const promptKey = actionType === 'disable' ? 'disableUsers.prompt' : 'activeUsers.prompt'

  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t(titleKey)}</AlertDialogTitle>
          <AlertDialogDescription className="flex items-center gap-2">
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t(promptKey, { name: adminUsername }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t('confirm')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default function AdminsTable({ onEdit, onDelete, onToggleStatus, onResetUsage, onTotalAdminsChange }: AdminsTableProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { admin: currentAdmin } = useAdmin()
  const [currentPage, setCurrentPage] = useState(0)
  const [itemsPerPage, setItemsPerPage] = useState(getAdminsPerPageLimitSize())
  const [isChangingPage, setIsChangingPage] = useState(false)
  const isFirstLoadRef = useRef(true)
  const [filters, setFilters] = useState<AdminFilters>({
    sort: '-created_at',
    limit: itemsPerPage,
    offset: 0,
  })
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [statusToggleDialogOpen, setStatusToggleDialogOpen] = useState(false)
  const [resetUsersUsageDialogOpen, setResetUsersUsageDialogOpen] = useState(false)
  const [bulkUsersStatusDialogOpen, setBulkUsersStatusDialogOpen] = useState(false)
  const [removeAllUsersDialogOpen, setRemoveAllUsersDialogOpen] = useState(false)
  const [selectedAdminUsernames, setSelectedAdminUsernames] = useState<string[]>([])
  const [resetSelectionKey, setResetSelectionKey] = useState(0)
  const [bulkAction, setBulkAction] = useState<BulkAdminActionType | null>(null)
  const [adminToDelete, setAdminToDelete] = useState<AdminDetails | null>(null)
  const [adminToToggleStatus, setAdminToToggleStatus] = useState<AdminDetails | null>(null)
  const [adminToReset, setAdminToReset] = useState<string | null>(null)
  const [bulkUsersStatusAction, setBulkUsersStatusAction] = useState<{ username: string; actionType: BulkUsersActionType } | null>(null)
  const [adminToRemoveAllUsers, setAdminToRemoveAllUsers] = useState<string | null>(null)
  const bulkDeleteAdminsMutation = useBulkDeleteAdmins()
  const bulkResetAdminsUsageMutation = useBulkResetAdminsUsage()
  const bulkDisableAdminsMutation = useBulkDisableAdmins()
  const bulkEnableAdminsMutation = useBulkEnableAdmins()
  const bulkDisableAllActiveUsersMutation = useBulkDisableAllActiveUsers()
  const bulkActivateAllDisabledUsersMutation = useBulkActivateAllDisabledUsers()
  const bulkRemoveAllUsersMutation = useBulkRemoveAllUsers()

  const {
    data: adminsResponse,
    isLoading,
    isFetching,
    refetch,
  } = useGetAdmins(filters, {
    query: {
      staleTime: 0,
      gcTime: 0,
      retry: 1,
    },
  })

  const adminsData = adminsResponse?.admins || []
  const selectedAdmins = adminsData.filter(admin => selectedAdminUsernames.includes(admin.username))
  const selectedEnableEligibleUsernames = selectedAdmins.filter(admin => admin.is_disabled).map(admin => admin.username)
  const selectedDisableEligibleUsernames = selectedAdmins.filter(admin => !admin.is_disabled).map(admin => admin.username)

  // Expose counts to parent component for statistics
  useEffect(() => {
    if (onTotalAdminsChange) {
      if (adminsResponse) {
        onTotalAdminsChange({
          total: adminsResponse.total,
          active: adminsResponse.active,
          disabled: adminsResponse.disabled,
        })
      } else {
        onTotalAdminsChange(null)
      }
    }
  }, [adminsResponse, onTotalAdminsChange])
  const disableAllActiveUsersMutation = useDisableAllActiveUsers()
  const activateAllDisabledUsersMutation = useActivateAllDisabledUsers()
  const removeAllUsersMutation = useRemoveAllUsers()

  // Update filters when pagination changes
  useEffect(() => {
    setFilters(prev => ({
      ...prev,
      limit: itemsPerPage,
      offset: currentPage * itemsPerPage,
    }))
  }, [currentPage, itemsPerPage])

  useEffect(() => {
    if (adminsData && isFirstLoadRef.current) {
      isFirstLoadRef.current = false
    }
  }, [adminsData])

  useEffect(() => {
    if (!isFetching && isChangingPage) {
      setIsChangingPage(false)
    }
  }, [isFetching, isChangingPage])

  // When filters change (e.g., search), reset page if needed
  const handleFilterChange = (newFilters: Partial<AdminFilters>) => {
    setFilters(prev => {
      const resetPage = newFilters.username !== undefined && newFilters.username !== prev.username
      const updatedFilters = {
        ...prev,
        ...newFilters,
        offset: resetPage ? 0 : newFilters.offset !== undefined ? newFilters.offset : prev.offset,
      }
      // If username is explicitly set to undefined, remove it from the filters
      if ('username' in newFilters && newFilters.username === undefined) {
        delete updatedFilters.username
      }
      return updatedFilters
    })
    // Reset page if search changes
    if (newFilters.username !== undefined && newFilters.username !== filters.username) {
      setCurrentPage(0)
    }
  }

  const handleManualRefresh = async () => {
    return refetch()
  }

  const handleDeleteClick = (admin: AdminDetails) => {
    setAdminToDelete(admin)
    setDeleteDialogOpen(true)
  }

  const clearSelection = () => {
    setResetSelectionKey(prev => prev + 1)
    setSelectedAdminUsernames([])
  }

  const invalidateAdminQueries = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['/api/admins'] })
    queryClient.invalidateQueries({ queryKey: ['/api/users'] })
  }, [queryClient])

  const handleStatusToggleClick = (admin: AdminDetails) => {
    setAdminToToggleStatus(admin)
    setStatusToggleDialogOpen(true)
  }

  const handleResetUsersUsageClick = (adminUsername: string) => {
    setAdminToReset(adminUsername)
    setResetUsersUsageDialogOpen(true)
  }
  const handleConfirmResetUsersUsage = async () => {
    if (adminToReset) {
      onResetUsage(adminToReset)
      setResetUsersUsageDialogOpen(false)
      setAdminToReset(null)
    }
  }

  const handleRemoveAllUsersClick = (adminUsername: string) => {
    setAdminToRemoveAllUsers(adminUsername)
    setRemoveAllUsersDialogOpen(true)
  }

  const handleDisableAllActiveUsersClick = (adminUsername: string) => {
    setBulkUsersStatusAction({ username: adminUsername, actionType: 'disable' })
    setBulkUsersStatusDialogOpen(true)
  }

  const handleActivateAllDisabledUsersClick = (adminUsername: string) => {
    setBulkUsersStatusAction({ username: adminUsername, actionType: 'activate' })
    setBulkUsersStatusDialogOpen(true)
  }

  const closeBulkUsersStatusDialog = () => {
    setBulkUsersStatusDialogOpen(false)
    setBulkUsersStatusAction(null)
  }

  const handleConfirmBulkUsersStatusAction = async () => {
    if (!bulkUsersStatusAction) return

    const { username, actionType } = bulkUsersStatusAction

    try {
      if (actionType === 'disable') {
        await disableAllActiveUsersMutation.mutateAsync({ username })
      } else {
        await activateAllDisabledUsersMutation.mutateAsync({ username })
      }

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t(actionType === 'disable' ? 'admins.disableAllActiveUsersSuccess' : 'admins.activateAllDisabledUsersSuccess', {
          name: username,
          defaultValue:
            actionType === 'disable' ? `All active users under admin "${username}" have been disabled successfully` : `All disabled users under admin "${username}" have been activated successfully`,
        }),
      })
      closeBulkUsersStatusDialog()
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t(actionType === 'disable' ? 'admins.disableAllActiveUsersFailed' : 'admins.activateAllDisabledUsersFailed', {
          name: username,
          defaultValue: actionType === 'disable' ? `Failed to disable all active users under admin "${username}"` : `Failed to activate all disabled users under admin "${username}"`,
        }),
      })
    }
  }

  const handleConfirmRemoveAllUsers = async () => {
    if (adminToRemoveAllUsers) {
      try {
        await removeAllUsersMutation.mutateAsync({
          username: adminToRemoveAllUsers,
        })
        toast.success(t('success', { defaultValue: 'Success' }), {
          description: t('admins.removeAllUsersSuccess', {
            name: adminToRemoveAllUsers,
            defaultValue: `All users under admin "{name}" have been removed successfully`,
          }),
        })
        patchAdminInAdminsCache(queryClient, adminToRemoveAllUsers, { total_users: 0 })
        setRemoveAllUsersDialogOpen(false)
        setAdminToRemoveAllUsers(null)
      } catch (error) {
        toast.error(t('error', { defaultValue: 'Error' }), {
          description: t('admins.removeAllUsersFailed', {
            name: adminToRemoveAllUsers,
            defaultValue: `Failed to remove all users under admin "{name}"`,
          }),
        })
      }
    }
  }
  const handleConfirmDelete = async () => {
    if (adminToDelete) {
      onDelete(adminToDelete)
      setDeleteDialogOpen(false)
      setAdminToDelete(null)
    }
  }

  const handleConfirmStatusToggle = async (clicked: boolean) => {
    if (adminToToggleStatus) {
      onToggleStatus(adminToToggleStatus, clicked)
      setStatusToggleDialogOpen(false)
      setAdminToToggleStatus(null)
    }
  }

  const handlePageChange = (newPage: number) => {
    if (newPage === currentPage || isChangingPage) return

    setIsChangingPage(true)
    setCurrentPage(newPage)
  }

  const handleItemsPerPageChange = (value: number) => {
    setIsChangingPage(true)
    setItemsPerPage(value)
    setCurrentPage(0) // Reset to first page when items per page changes
    setAdminsPerPageLimitSize(value.toString())
    setIsChangingPage(false)
  }

  const handleSort = (column: string, fromDropdown = false) => {
    const currentSort = filters.sort

    const cleanColumn = column.startsWith('-') ? column.slice(1) : column

    if (fromDropdown) {
      if (column.startsWith('-')) {
        if (currentSort === '-' + cleanColumn) {
          setFilters(prev => ({ ...prev, sort: '-created_at' }))
        } else {
          setFilters(prev => ({ ...prev, sort: '-' + cleanColumn }))
        }
      } else if (currentSort === cleanColumn) {
        setFilters(prev => ({ ...prev, sort: '-created_at' }))
      } else {
        setFilters(prev => ({ ...prev, sort: cleanColumn }))
      }
      return
    }

    if (currentSort === cleanColumn) {
      // First click: ascending, make it descending
      setFilters(prev => ({ ...prev, sort: '-' + cleanColumn }))
    } else if (currentSort === '-' + cleanColumn) {
      // Second click: descending, return to default sort
      setFilters(prev => ({ ...prev, sort: '-created_at' }))
    } else {
      // Default state or different column: make it ascending
      setFilters(prev => ({ ...prev, sort: cleanColumn }))
    }
  }

  const handleBulkDelete = async () => {
    if (!selectedAdminUsernames.length) return

    try {
      const response = await bulkDeleteAdminsMutation.mutateAsync({
        data: {
          usernames: selectedAdminUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkDeleteSuccess', {
          count: response.count,
          defaultValue: '{{count}} admins deleted successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description:
          error?.data?.detail ||
          error?.message ||
          t('admins.bulkDeleteFailed', {
            defaultValue: 'Failed to delete selected admins.',
          }),
      })
    }
  }

  const handleBulkResetUsage = async () => {
    if (!selectedAdminUsernames.length) return

    try {
      const response = await bulkResetAdminsUsageMutation.mutateAsync({
        data: {
          usernames: selectedAdminUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkResetSuccess', {
          count: response.count,
          defaultValue: 'Usage reset for {{count}} admins.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('admins.bulkResetFailed', { defaultValue: 'Failed to reset usage for selected admins.' }),
      })
    }
  }

  const handleBulkDisable = async () => {
    if (!selectedDisableEligibleUsernames.length) return

    try {
      const response = await bulkDisableAdminsMutation.mutateAsync({
        data: {
          usernames: selectedDisableEligibleUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkDisableSuccess', {
          count: response.count,
          defaultValue: '{{count}} admins disabled successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('admins.bulkDisableFailed', { defaultValue: 'Failed to disable selected admins.' }),
      })
    }
  }

  const handleBulkEnable = async () => {
    if (!selectedEnableEligibleUsernames.length) return

    try {
      const response = await bulkEnableAdminsMutation.mutateAsync({
        data: {
          usernames: selectedEnableEligibleUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkEnableSuccess', {
          count: response.count,
          defaultValue: '{{count}} admins enabled successfully.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('admins.bulkEnableFailed', { defaultValue: 'Failed to enable selected admins.' }),
      })
    }
  }

  const handleBulkDisableUsers = async () => {
    if (!selectedAdminUsernames.length) return

    try {
      const response = await bulkDisableAllActiveUsersMutation.mutateAsync({
        data: {
          usernames: selectedAdminUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkDisableUsersSuccess', {
          count: response.count,
          defaultValue: 'All active users were disabled for {{count}} admins.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('admins.bulkDisableUsersFailed', { defaultValue: 'Failed to disable active users for selected admins.' }),
      })
    }
  }

  const handleBulkActivateUsers = async () => {
    if (!selectedAdminUsernames.length) return

    try {
      const response = await bulkActivateAllDisabledUsersMutation.mutateAsync({
        data: {
          usernames: selectedAdminUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkActivateUsersSuccess', {
          count: response.count,
          defaultValue: 'All disabled users were activated for {{count}} admins.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('admins.bulkActivateUsersFailed', { defaultValue: 'Failed to activate disabled users for selected admins.' }),
      })
    }
  }

  const handleBulkRemoveUsers = async () => {
    if (!selectedAdminUsernames.length) return

    try {
      const response = await bulkRemoveAllUsersMutation.mutateAsync({
        data: {
          usernames: selectedAdminUsernames,
        },
      })
      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t('admins.bulkRemoveUsersSuccess', {
          count: response.count,
          defaultValue: 'All users removed for {{count}} admins.',
        }),
      })
      clearSelection()
      setBulkAction(null)
      invalidateAdminQueries()
    } catch (error: any) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: error?.data?.detail || error?.message || t('admins.bulkRemoveUsersFailed', { defaultValue: 'Failed to remove users for selected admins.' }),
      })
    }
  }

  const selectedCount = selectedAdminUsernames.length
  const enableEligibleCount = selectedEnableEligibleUsernames.length
  const disableEligibleCount = selectedDisableEligibleUsernames.length
  const bulkActions: BulkActionItem[] = selectedCount
    ? [
      {
        key: 'delete',
        label: t('delete'),
        icon: Trash2,
        onClick: () => setBulkAction('delete'),
        direct: true,
        destructive: true,
      },
      {
        key: 'reset',
        label: t('admins.reset'),
        icon: RefreshCw,
        onClick: () => setBulkAction('reset'),
      },
      ...(disableEligibleCount > 0
        ? [
          {
            key: 'disable',
            label: t('disable'),
            icon: PowerOff,
            onClick: () => setBulkAction('disable'),
          } as BulkActionItem,
        ]
        : []),
      ...(enableEligibleCount > 0
        ? [
          {
            key: 'enable',
            label: t('enable'),
            icon: Power,
            onClick: () => setBulkAction('enable'),
          } as BulkActionItem,
        ]
        : []),
      {
        key: 'disableUsers',
        label: t('admins.disableAllActiveUsers'),
        icon: UserMinus,
        onClick: () => setBulkAction('disableUsers'),
      },
      {
        key: 'activateUsers',
        label: t('admins.activateAllDisabledUsers'),
        icon: UserCheck,
        onClick: () => setBulkAction('activateUsers'),
      },
      {
        key: 'removeUsers',
        label: t('admins.removeAllUsers'),
        icon: UserX,
        onClick: () => setBulkAction('removeUsers'),
        destructive: true,
      },
    ]
    : []
  const bulkActionConfigs: Record<BulkAdminActionType, BulkActionDialogConfig> = {
    delete: {
      title: t('admins.bulkDeleteTitle', { defaultValue: 'Delete Selected Admins' }),
      description: t('admins.bulkDeletePrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to delete {{count}} selected admins? This action cannot be undone.',
      }),
      actionLabel: t('delete'),
      onConfirm: handleBulkDelete,
      isPending: bulkDeleteAdminsMutation.isPending,
      destructive: true,
    },
    reset: {
      title: t('admins.bulkResetTitle', { defaultValue: 'Reset Usage for Selected Admins' }),
      description: t('admins.bulkResetPrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to reset usage for {{count}} selected admins?',
      }),
      actionLabel: t('admins.reset'),
      onConfirm: handleBulkResetUsage,
      isPending: bulkResetAdminsUsageMutation.isPending,
    },
    enable: {
      title: t('admins.bulkEnableTitle', { defaultValue: 'Enable Selected Admins' }),
      description: t('admins.bulkEnablePrompt', {
        count: enableEligibleCount,
        defaultValue: 'Are you sure you want to enable {{count}} selected admins?',
      }),
      actionLabel: t('enable'),
      onConfirm: handleBulkEnable,
      isPending: bulkEnableAdminsMutation.isPending,
    },
    disable: {
      title: t('admins.bulkDisableTitle', { defaultValue: 'Disable Selected Admins' }),
      description: t('admins.bulkDisablePrompt', {
        count: disableEligibleCount,
        defaultValue: 'Are you sure you want to disable {{count}} selected admins?',
      }),
      actionLabel: t('disable'),
      onConfirm: handleBulkDisable,
      isPending: bulkDisableAdminsMutation.isPending,
    },
    disableUsers: {
      title: t('admins.bulkDisableUsersTitle', { defaultValue: 'Disable All Active Users for Selected Admins' }),
      description: t('admins.bulkDisableUsersPrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to disable all active users for {{count}} selected admins?',
      }),
      actionLabel: t('admins.disableAllActiveUsers'),
      onConfirm: handleBulkDisableUsers,
      isPending: bulkDisableAllActiveUsersMutation.isPending,
    },
    activateUsers: {
      title: t('admins.bulkActivateUsersTitle', { defaultValue: 'Activate All Disabled Users for Selected Admins' }),
      description: t('admins.bulkActivateUsersPrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to activate all disabled users for {{count}} selected admins?',
      }),
      actionLabel: t('admins.activateAllDisabledUsers'),
      onConfirm: handleBulkActivateUsers,
      isPending: bulkActivateAllDisabledUsersMutation.isPending,
    },
    removeUsers: {
      title: t('admins.bulkRemoveUsersTitle', { defaultValue: 'Remove All Users for Selected Admins' }),
      description: t('admins.bulkRemoveUsersPrompt', {
        count: selectedCount,
        defaultValue: 'Are you sure you want to remove all users for {{count}} selected admins? This action cannot be undone.',
      }),
      actionLabel: t('admins.removeAllUsers'),
      onConfirm: handleBulkRemoveUsers,
      isPending: bulkRemoveAllUsersMutation.isPending,
      destructive: true,
    },
  }
  const activeBulkActionConfig = bulkAction ? bulkActionConfigs[bulkAction] : null

  const columns = setupColumns({
    t,
    handleSort,
    filters,
    currentAdminUsername: currentAdmin?.username,
    onEdit,
    onDelete: handleDeleteClick,
    toggleStatus: handleStatusToggleClick,
    onResetUsage: handleResetUsersUsageClick,
    onDisableAllActiveUsers: handleDisableAllActiveUsersClick,
    onActivateAllDisabledUsers: handleActivateAllDisabledUsersClick,
    onRemoveAllUsers: handleRemoveAllUsersClick,
  })

  const isCurrentlyLoading = isLoading || (isFetching && !adminsResponse)
  const isPageLoading = isChangingPage || (isFetching && !isFirstLoadRef.current)

  return (
    <div>
      <Filters filters={filters} onFilterChange={handleFilterChange} handleSort={handleSort} refetch={handleManualRefresh} />
      <BulkActionsBar selectedCount={selectedCount} onClear={clearSelection} actions={bulkActions} />
      <DataTable
        columns={columns}
        data={adminsData || []}
        onEdit={onEdit}
        onDelete={handleDeleteClick}
        onToggleStatus={handleStatusToggleClick}
        onResetUsage={handleResetUsersUsageClick}
        onDisableAllActiveUsers={handleDisableAllActiveUsersClick}
        onActivateAllDisabledUsers={handleActivateAllDisabledUsersClick}
        onRemoveAllUsers={handleRemoveAllUsersClick}
        onSelectionChange={setSelectedAdminUsernames}
        resetSelectionKey={resetSelectionKey}
        currentAdminUsername={currentAdmin?.username}
        setStatusToggleDialogOpen={setStatusToggleDialogOpen}
        isLoading={isCurrentlyLoading && isFirstLoadRef.current}
        isFetching={isFetching && !isFirstLoadRef.current}
      />
      <PaginationControls
        currentPage={currentPage}
        totalPages={Math.ceil((adminsResponse?.total || 0) / itemsPerPage)}
        itemsPerPage={itemsPerPage}
        totalItems={adminsResponse?.total || 0}
        isLoading={isPageLoading}
        onPageChange={handlePageChange}
        onItemsPerPageChange={handleItemsPerPageChange}
      />
      {adminToDelete && <DeleteAlertDialog admin={adminToDelete} isOpen={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} onConfirm={handleConfirmDelete} />}
      {adminToToggleStatus && (
        <ToggleAdminStatusModal admin={adminToToggleStatus} isOpen={statusToggleDialogOpen} onClose={() => setStatusToggleDialogOpen(false)} onConfirm={handleConfirmStatusToggle} />
      )}
      {adminToReset && (
        <ResetUsersUsageConfirmationDialog
          adminUsername={adminToReset}
          onConfirm={handleConfirmResetUsersUsage}
          isOpen={resetUsersUsageDialogOpen}
          onClose={() => setResetUsersUsageDialogOpen(false)}
        />
      )}
      {bulkUsersStatusAction && (
        <BulkUsersStatusConfirmationDialog
          adminUsername={bulkUsersStatusAction.username}
          actionType={bulkUsersStatusAction.actionType}
          onConfirm={handleConfirmBulkUsersStatusAction}
          isOpen={bulkUsersStatusDialogOpen}
          onClose={closeBulkUsersStatusDialog}
        />
      )}
      {adminToRemoveAllUsers && (
        <RemoveAllUsersConfirmationDialog
          adminUsername={adminToRemoveAllUsers}
          onConfirm={handleConfirmRemoveAllUsers}
          isOpen={removeAllUsersDialogOpen}
          onClose={() => setRemoveAllUsersDialogOpen(false)}
        />
      )}
      {activeBulkActionConfig && (
        <BulkActionAlertDialog
          open={!!bulkAction}
          onOpenChange={open => setBulkAction(open ? bulkAction : null)}
          title={activeBulkActionConfig.title}
          description={activeBulkActionConfig.description}
          actionLabel={activeBulkActionConfig.actionLabel}
          onConfirm={activeBulkActionConfig.onConfirm}
          isPending={activeBulkActionConfig.isPending}
          destructive={activeBulkActionConfig.destructive}
        />
      )}
    </div>
  )
}
