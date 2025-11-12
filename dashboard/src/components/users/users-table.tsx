import { setupColumns } from '@/components/users/columns'
import { DataTable } from '@/components/users/data-table'
import { Filters } from '@/components/users/filters'
import useDirDetection from '@/hooks/use-dir-detection'
import { UseEditFormValues } from '@/pages/_dashboard.users'
import { useGetUsers, UserResponse, UserStatus } from '@/service/api'
import { useAdmin } from '@/hooks/use-admin'
import { getUsersPerPageLimitSize, setUsersPerPageLimitSize } from '@/utils/userPreferenceStorage'
import { useQueryClient } from '@tanstack/react-query'
import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import UserModal from '../dialogs/user-modal'
import { PaginationControls } from './filters'
import AdvanceSearchModal, { AdvanceSearchFormValue } from '@/components/dialogs/advance-search-modal.tsx'

const UsersTable = memo(() => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const queryClient = useQueryClient()
  const [currentPage, setCurrentPage] = useState(0)
  const [itemsPerPage, setItemsPerPage] = useState(getUsersPerPageLimitSize())
  const [isChangingPage, setIsChangingPage] = useState(false)
  const [isEditModalOpen, setEditModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null)
  const [isAdvanceSearchOpen, setIsAdvanceSearchOpen] = useState(false)
  const [isSorting, setIsSorting] = useState(false)
  const isFirstLoadRef = useRef(true)
  const { admin } = useAdmin()
  const isSudo = admin?.is_sudo || false

  const [filters, setFilters] = useState<{
    limit: number
    sort: string
    load_sub: boolean
    offset: number
    search?: string
    proxy_id?: string
    is_protocol: boolean
    status?: UserStatus | null
    admin?: string[]
    group?: number[]
  }>({
    limit: itemsPerPage,
    sort: '-created_at',
    load_sub: true,
    offset: 0,
    search: undefined,
    proxy_id: undefined,
    is_protocol: false,
    status: undefined,
    admin: undefined,
    group: undefined,
  })

  const advanceSearchForm = useForm<AdvanceSearchFormValue>({
    defaultValues: {
      is_username: true,
      is_protocol: false,
      admin: [],
      group: [],
      status: '0',
    },
  }) as any

  // Create form for user editing
  const userForm = useForm<UseEditFormValues>({
    defaultValues: {
      username: selectedUser?.username,
      status: selectedUser?.status === 'active' || selectedUser?.status === 'on_hold' || selectedUser?.status === 'disabled' ? selectedUser?.status : 'active',
      data_limit: selectedUser?.data_limit ? Math.round((Number(selectedUser?.data_limit) / (1024 * 1024 * 1024)) * 100) / 100 : undefined, // Convert bytes to GB
      expire: selectedUser?.expire,
      note: selectedUser?.note || '',
      data_limit_reset_strategy: selectedUser?.data_limit_reset_strategy || undefined,
      group_ids: selectedUser?.group_ids || [], // Add group_ids
      on_hold_expire_duration: selectedUser?.on_hold_expire_duration || undefined,
      on_hold_timeout: selectedUser?.on_hold_timeout || undefined,
      proxy_settings: selectedUser?.proxy_settings || undefined,
      next_plan: selectedUser?.next_plan
        ? {
            user_template_id: selectedUser?.next_plan.user_template_id ? Number(selectedUser?.next_plan.user_template_id) : undefined,
            data_limit: selectedUser?.next_plan.data_limit ? Number(selectedUser?.next_plan.data_limit) : undefined,
            expire: selectedUser?.next_plan.expire ? Number(selectedUser?.next_plan.expire) : undefined,
            add_remaining_traffic: selectedUser?.next_plan.add_remaining_traffic || false,
          }
        : undefined,
    },
  })

  // Update form when selected user changes
  useEffect(() => {
    if (selectedUser) {
      const values: UseEditFormValues = {
        username: selectedUser.username,
        status: selectedUser.status === 'active' || selectedUser.status === 'on_hold' || selectedUser.status === 'disabled' ? selectedUser.status : 'active',
        data_limit: selectedUser.data_limit ? Math.round((Number(selectedUser.data_limit) / (1024 * 1024 * 1024)) * 100) / 100 : 0, // Convert bytes to GB
        expire: selectedUser.expire,
        note: selectedUser.note || '',
        data_limit_reset_strategy: selectedUser.data_limit_reset_strategy || undefined,
        group_ids: selectedUser.group_ids || [],
        on_hold_expire_duration: selectedUser.on_hold_expire_duration || undefined,
        on_hold_timeout: selectedUser.on_hold_timeout || undefined,
        proxy_settings: selectedUser.proxy_settings || undefined,
        next_plan: selectedUser.next_plan
          ? {
              user_template_id: selectedUser.next_plan.user_template_id ? Number(selectedUser.next_plan.user_template_id) : undefined,
              data_limit: selectedUser.next_plan.data_limit ? Number(selectedUser.next_plan.data_limit) : undefined,
              expire: selectedUser.next_plan.expire ? Number(selectedUser.next_plan.expire) : undefined,
              add_remaining_traffic: selectedUser.next_plan.add_remaining_traffic || false,
            }
          : undefined,
      }
      userForm.reset(values)
    }
  }, [selectedUser, userForm])

  // Update filters when pagination changes
  useEffect(() => {
    setFilters(prev => ({
      ...prev,
      limit: itemsPerPage,
      offset: currentPage * itemsPerPage,
    }))
  }, [currentPage, itemsPerPage])

  // Sync advance search form with current filters when modal opens
  useEffect(() => {
    if (isAdvanceSearchOpen) {
      advanceSearchForm.setValue('status', filters.status || '0')
      advanceSearchForm.setValue('admin', filters.admin || [])
      advanceSearchForm.setValue('group', filters.group || [])
    }
  }, [isAdvanceSearchOpen, filters.status, filters.admin, filters.group, advanceSearchForm])

  const {
    data: usersData,
    refetch,
    isLoading,
  } = useGetUsers(filters, {
    query: {
      staleTime: 0,
      gcTime: 0,
      retry: 1,
    },
  })

  // Track first load completion
  useEffect(() => {
    if (usersData && isFirstLoadRef.current) {
      isFirstLoadRef.current = false
    }
  }, [usersData])

  // Remove automatic refetch on filter change to prevent lag
  // Filters will trigger new queries automatically

  const handleSort = useCallback(
    (column: string, fromDropdown = false) => {
      // Prevent rapid clicking
      if (isSorting) return

      setIsSorting(true)

      let newSort: string

      // Clean the column name in case it comes with prefix
      const cleanColumn = column.startsWith('-') ? column.slice(1) : column

      if (fromDropdown) {
        // Dropdown behavior: click to sort, click again to reset
        if (column.startsWith('-')) {
          // Dropdown descending option clicked
          if (filters.sort === '-' + cleanColumn) {
            // If already descending, reset to default
            newSort = '-created_at'
          } else {
            // Set to descending
            newSort = '-' + cleanColumn
          }
        } else {
          // Dropdown ascending option clicked
          if (filters.sort === cleanColumn) {
            // If already ascending, reset to default
            newSort = '-created_at'
          } else {
            // Set to ascending
            newSort = cleanColumn
          }
        }
      } else {
        // Table column behavior: 3-state cycling (asc → desc → no sort)
        if (filters.sort === cleanColumn) {
          // If currently ascending, make it descending
          newSort = '-' + cleanColumn
        } else if (filters.sort === '-' + cleanColumn) {
          // If currently descending, remove sort (third state: no sort)
          newSort = '-created_at'
        } else {
          // If different column or default, make it ascending
          newSort = cleanColumn
        }
      }

      setFilters(prev => ({ ...prev, sort: newSort }))

      // Release the lock after a short delay
      setTimeout(() => setIsSorting(false), 100)
    },
    [filters.sort, isSorting],
  )

  const handleStatusFilter = useCallback(
    (value: any) => {
      // Sync with advance search form
      advanceSearchForm.setValue('status', value || '0')

      // If value is '0' or empty, set status to undefined to remove it from the URL
      if (value === '0' || value === '') {
        setFilters(prev => ({
          ...prev,
          status: undefined, // Set to undefined so it won't be included in the request
          offset: 0, // Reset to first page when changing filter
        }))
      } else {
        setFilters(prev => ({
          ...prev,
          status: value, // Otherwise set the actual status value
          offset: 0, // Reset to first page when changing filter
        }))
      }

      setCurrentPage(0) // Reset current page
    },
    [advanceSearchForm],
  )

  const handleFilterChange = useCallback((newFilters: Partial<typeof filters>) => {
    setFilters(prev => {
      let updated = { ...prev, ...newFilters }
      if ('search' in newFilters) {
        if (prev.is_protocol) {
          updated.proxy_id = newFilters.search
          updated.search = undefined
        } else {
          updated.search = newFilters.search
          updated.proxy_id = undefined
        }
        updated.offset = 0
      }
      return updated
    })

    if (newFilters.search !== undefined) {
      setCurrentPage(0)
    }
  }, [])

  const handleManualRefresh = async () => {
    // Invalidate queries to ensure fresh data
    queryClient.invalidateQueries({ queryKey: ['getUsers'] })
    // Then refetch
    return refetch()
  }

  const handlePageChange = (newPage: number) => {
    if (newPage === currentPage || isChangingPage) return

    setIsChangingPage(true)
    setCurrentPage(newPage)

    // Remove async/await and setTimeout for instant response
    setIsChangingPage(false)
  }

  const handleItemsPerPageChange = (value: number) => {
    setIsChangingPage(true)
    setItemsPerPage(value)
    setCurrentPage(0) // Reset to first page when items per page changes

    // Save to localStorage
    setUsersPerPageLimitSize(value.toString())

    // Remove async/await and setTimeout for instant response
    setIsChangingPage(false)
  }

  const handleEdit = (user: UserResponse) => {
    setSelectedUser(user)
    setEditModalOpen(true)
  }

  const handleEditSuccess = () => {
    setEditModalOpen(false)
    setSelectedUser(null)
    // No need to manually refresh - cache is already updated by the modal
  }

  const columns = setupColumns({
    t,
    dir,
    handleSort,
    filters: filters as { sort: string; status?: UserStatus | null; [key: string]: unknown },
    handleStatusFilter,
  })

  const handleAdvanceSearchSubmit = (values: AdvanceSearchFormValue) => {
    setFilters(prev => ({
      ...prev,
      admin: values.admin && values.admin.length > 0 ? values.admin : undefined,
      group: values.group && values.group.length > 0 ? values.group : undefined,
      status: values.status && values.status !== '0' ? values.status : undefined,
      is_protocol: values.is_protocol, // update is_protocol
      offset: 0, // Reset to first page
    }))
    setCurrentPage(0)
    setIsAdvanceSearchOpen(false)
    advanceSearchForm.reset(values)
  }

  const totalUsers = usersData?.total || 0
  const totalPages = Math.ceil(totalUsers / itemsPerPage)
  // Only show loading spinner on first load, not on refreshes
  const showLoadingSpinner = isLoading && isFirstLoadRef.current
  const isPageLoading = isChangingPage

  return (
    <div>
      <Filters
        filters={filters}
        onFilterChange={handleFilterChange}
        advanceSearchOnOpen={setIsAdvanceSearchOpen}
        refetch={handleManualRefresh}
        handleSort={handleSort}
        onClearAdvanceSearch={() => {
          advanceSearchForm.reset({
            is_username: true,
            is_protocol: false,
            admin: [],
            group: [],
            status: '0',
          })
          setFilters(prev => ({
            ...prev,
            admin: undefined,
            group: undefined,
            status: undefined,
            offset: 0,
          }))
          setCurrentPage(0)
        }}
      />
      <DataTable columns={columns} data={usersData?.users || []} isLoading={showLoadingSpinner} isFetching={false} onEdit={handleEdit} />
      <PaginationControls
        currentPage={currentPage}
        totalPages={totalPages}
        itemsPerPage={itemsPerPage}
        totalUsers={totalUsers}
        isLoading={isPageLoading}
        onPageChange={handlePageChange}
        onItemsPerPageChange={handleItemsPerPageChange}
      />
      {selectedUser && (
        <UserModal
          isDialogOpen={isEditModalOpen}
          onOpenChange={setEditModalOpen}
          form={userForm}
          editingUser={true}
          editingUserId={selectedUser.id || undefined}
          editingUserData={selectedUser}
          onSuccessCallback={handleEditSuccess}
        />
      )}
      {isAdvanceSearchOpen && (
        <AdvanceSearchModal
          isDialogOpen={isAdvanceSearchOpen}
          onOpenChange={open => {
            setIsAdvanceSearchOpen(open)
            if (!open) advanceSearchForm.reset() // Reset form when closing
          }}
          form={advanceSearchForm}
          onSubmit={handleAdvanceSearchSubmit}
          isSudo={isSudo}
        />
      )}
    </div>
  )
})

export default UsersTable
