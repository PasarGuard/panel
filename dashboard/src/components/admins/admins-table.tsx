import { useTranslation } from 'react-i18next'
import type { AdminDetails } from '@/service/api'
import { useGetAdmins, useRemoveAllUsers } from '@/service/api'
import { DataTable } from './data-table'
import { setupColumns } from './columns'
import { Filters } from './filters'
import { useEffect, useState, useRef } from 'react'
import { PaginationControls } from './filters.tsx'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import { Checkbox } from '@/components/ui/checkbox.tsx'
import { getAdminsPerPageLimitSize, setAdminsPerPageLimitSize } from '@/utils/userPreferenceStorage'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'

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
        <AlertDialogHeader className={cn(dir === 'rtl' && 'sm:text-right')}>
          <AlertDialogTitle>{t(admin.is_disabled ? 'admin.enable' : 'admin.disable')}</AlertDialogTitle>
          <AlertDialogDescription className="flex items-center gap-2">
            <Checkbox checked={adminUsersToggle} onCheckedChange={() => setAdminUsersToggle(!adminUsersToggle)} />
            <span dir={dir} dangerouslySetInnerHTML={{ __html: t(admin.is_disabled ? 'activeUsers.prompt' : 'disableUsers.prompt', { name: admin.username }) }} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className={cn(dir === 'rtl' && 'sm:flex-row-reverse sm:gap-x-2')}>
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
        <AlertDialogHeader className={cn(dir === 'rtl' && 'sm:text-right')}>
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
        <AlertDialogHeader className={cn(dir === 'rtl' && 'sm:text-right')}>
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

export default function AdminsTable({ onEdit, onDelete, onToggleStatus, onResetUsage, onTotalAdminsChange }: AdminsTableProps) {
  const { t } = useTranslation()
  const [currentPage, setCurrentPage] = useState(0)
  const [itemsPerPage, setItemsPerPage] = useState(getAdminsPerPageLimitSize())
  const [isChangingPage, setIsChangingPage] = useState(false)
  const isFirstLoadRef = useRef(true)
  const isAutoRefreshingRef = useRef(false)
  const [filters, setFilters] = useState<AdminFilters>({
    limit: itemsPerPage,
    offset: 0,
  })
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [statusToggleDialogOpen, setStatusToggleDialogOpen] = useState(false)
  const [resetUsersUsageDialogOpen, setResetUsersUsageDialogOpen] = useState(false)
  const [removeAllUsersDialogOpen, setRemoveAllUsersDialogOpen] = useState(false)
  const [adminToDelete, setAdminToDelete] = useState<AdminDetails | null>(null)
  const [adminToToggleStatus, setAdminToToggleStatus] = useState<AdminDetails | null>(null)
  const [adminToReset, setAdminToReset] = useState<string | null>(null)
  const [adminToRemoveAllUsers, setAdminToRemoveAllUsers] = useState<string | null>(null)

  const {
    data: adminsResponse,
    isLoading,
    isFetching,
  } = useGetAdmins(filters, {
    query: {
      staleTime: 0,
      gcTime: 0,
      retry: 1,
    },
  })

  const adminsData = adminsResponse?.admins || []

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
    if (!isFetching && isAutoRefreshingRef.current) {
      isAutoRefreshingRef.current = false
    }
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

  const handleDeleteClick = (admin: AdminDetails) => {
    setAdminToDelete(admin)
    setDeleteDialogOpen(true)
  }

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
        queryClient.invalidateQueries({ queryKey: ['/api/admins'] })
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

  const handleSort = (column: string) => {
    const currentSort = filters.sort

    if (currentSort === column) {
      // First click: ascending, make it descending
      setFilters(prev => ({ ...prev, sort: '-' + column }))
    } else if (currentSort === '-' + column) {
      // Second click: descending, remove sort (third state: no sort)
      setFilters(prev => {
        const { sort, ...restFilters } = prev
        return restFilters as AdminFilters
      })
    } else {
      // Default state or different column: make it ascending
      setFilters(prev => ({ ...prev, sort: column }))
    }
  }

  const columns = setupColumns({
    t,
    handleSort,
    filters,
    onEdit,
    onDelete: handleDeleteClick,
    toggleStatus: handleStatusToggleClick,
    onResetUsage: handleResetUsersUsageClick,
    onRemoveAllUsers: handleRemoveAllUsersClick,
  })

  const showLoadingSpinner = isLoading && isFirstLoadRef.current
  const isPageLoading = isChangingPage || (isFetching && !isFirstLoadRef.current && !isAutoRefreshingRef.current)

  return (
    <div>
      <Filters filters={filters} onFilterChange={handleFilterChange} />
      <DataTable
        columns={columns}
        data={adminsData || []}
        onEdit={onEdit}
        onDelete={handleDeleteClick}
        onToggleStatus={handleStatusToggleClick}
        onResetUsage={handleResetUsersUsageClick}
        onRemoveAllUsers={handleRemoveAllUsersClick}
        setStatusToggleDialogOpen={setStatusToggleDialogOpen}
        isLoading={showLoadingSpinner}
        isFetching={isFetching && !isFirstLoadRef.current && !isAutoRefreshingRef.current}
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
      {adminToRemoveAllUsers && (
        <RemoveAllUsersConfirmationDialog
          adminUsername={adminToRemoveAllUsers}
          onConfirm={handleConfirmRemoveAllUsers}
          isOpen={removeAllUsersDialogOpen}
          onClose={() => setRemoveAllUsersDialogOpen(false)}
        />
      )}
    </div>
  )
}
