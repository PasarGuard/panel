import { setupColumns } from '@/components/users/columns'
import { ActionButtonsModalHost } from '@/components/users/action-buttons'
import SetOwnerModal from '@/components/dialogs/set-owner-modal'
import ApplyTemplateModal from '@/components/dialogs/apply-template-modal'
import { DataTable } from '@/components/users/data-table'
import { Filters } from '@/components/users/filters'
import { type UseEditFormValues } from '@/components/forms/user-form'
import useDirDetection from '@/hooks/use-dir-detection'
import {
  getGetUsersQueryOptions,
  bulkDeleteUsers,
  bulkDisableUsers,
  bulkEnableUsers,
  bulkResetUsersDataUsage,
  bulkRevokeUsersSubscription,
  useGetUsers,
  UserResponse,
  UserStatus,
  UsersResponse,
} from '@/service/api'

import { useAdmin } from '@/hooks/use-admin'
import {
  getUsersPerPageLimitSize,
  getUsersShowCreatedBy,
  getUsersShowSelectionCheckbox,
  setUsersPerPageLimitSize,
  setUsersShowCreatedBy,
  setUsersShowSelectionCheckbox,
} from '@/utils/userPreferenceStorage'
import { bytesToFormGigabytes } from '@/utils/formatByte'
import { normalizeExpireForEditForm } from '@/utils/userEditDateUtils'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Layers, Link2Off, Power, PowerOff, RefreshCcw, Trash2, UserCog } from 'lucide-react'
import UserModal from '../dialogs/user-modal'
import { PaginationControls } from './filters'
import AdvanceSearchModal from '@/components/dialogs/advance-search-modal'
import type { AdvanceSearchFormValue } from '@/components/forms/advance-search-form'
import { BulkActionItem, BulkActionsBar } from '@/components/users/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/components/users/bulk-action-alert-dialog'
import { Card, CardContent } from '@/components/ui/card'

// Helper function to get URL search params from hash
const getSearchParams = (): URLSearchParams => {
  const hash = window.location.hash
  const queryIndex = hash.indexOf('?')
  if (queryIndex === -1) return new URLSearchParams()
  return new URLSearchParams(hash.substring(queryIndex + 1))
}

// Helper function to update URL with search params
const updateURLParams = (params: URLSearchParams) => {
  const hash = window.location.hash
  const hashPath = hash.split('?')[0]
  const newHash = params.toString() ? `${hashPath}?${params.toString()}` : hashPath
  window.history.replaceState(null, '', newHash)
}

// Helper function to parse URL params into filters
const parseURLParams = (searchParams: URLSearchParams, defaultItemsPerPage: number) => {
  const pageParam = searchParams.get('page')
  // URL stores page as 1-indexed (what user sees), convert to 0-indexed for internal use
  const page = pageParam ? Math.max(0, parseInt(pageParam, 10) - 1) : 0
  const limit = parseInt(searchParams.get('limit') || defaultItemsPerPage.toString(), 10)
  const sort = searchParams.get('sort') || '-created_at'
  const search = searchParams.get('search') || undefined
  const statusParam = searchParams.get('status')
  const validStatuses: UserStatus[] = ['active', 'disabled', 'limited', 'expired', 'on_hold']
  const status = statusParam && validStatuses.includes(statusParam as UserStatus) ? (statusParam as UserStatus) : undefined
  const admin = searchParams.getAll('admin').filter(Boolean)
  const group = searchParams
    .getAll('group')
    .map(g => parseInt(g, 10))
    .filter(g => !isNaN(g))
  const isProtocol = searchParams.get('is_protocol') === 'true'

  return {
    page: Math.max(0, page),
    limit: limit > 0 ? limit : defaultItemsPerPage,
    sort,
    search,
    status,
    admin: admin.length > 0 ? admin : undefined,
    group: group.length > 0 ? group : undefined,
    isProtocol,
  }
}

const UsersTable = memo(() => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const queryClient = useQueryClient()
  const isFirstLoadRef = useRef(true)
  const isAutoRefreshingRef = useRef(false)
  const isInitializingFromURLRef = useRef(false)
  const { admin } = useAdmin()
  const isSudo = admin?.is_sudo || false

  // Initialize from URL params on mount
  const getInitialStateFromURL = () => {
    const searchParams = getSearchParams()
    const urlParams = parseURLParams(searchParams, getUsersPerPageLimitSize())

    return {
      page: urlParams.page,
      limit: urlParams.limit,
      filters: {
        limit: urlParams.limit,
        sort: urlParams.sort,
        load_sub: true,
        offset: urlParams.page * urlParams.limit,
        search: urlParams.search,
        proxy_id: urlParams.isProtocol && urlParams.search ? urlParams.search : undefined,
        is_protocol: urlParams.isProtocol,
        status: urlParams.status || undefined,
        admin: urlParams.admin,
        group: urlParams.group,
      },
    }
  }

  const initialState = getInitialStateFromURL()
  const [currentPage, setCurrentPage] = useState(initialState.page)
  const [itemsPerPage, setItemsPerPage] = useState(initialState.limit)
  const [isChangingPage, setIsChangingPage] = useState(false)
  const [isEditModalOpen, setEditModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null)
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([])
  const [resetSelectionKey, setResetSelectionKey] = useState(0)
  const [bulkAction, setBulkAction] = useState<'delete' | 'reset' | 'revoke' | 'disable' | 'enable' | 'apply_template' | null>(null)
  const [isBulkSetOwnerModalOpen, setIsBulkSetOwnerModalOpen] = useState(false)
  const [isBulkApplyTemplateModalOpen, setIsBulkApplyTemplateModalOpen] = useState(false)
  const [isAdvanceSearchOpen, setIsAdvanceSearchOpen] = useState(false)
  const [isAdvanceSearchApplying, setIsAdvanceSearchApplying] = useState(false)
  const [isSorting, setIsSorting] = useState(false)
  const [showCreatedBy, setShowCreatedBy] = useState(getUsersShowCreatedBy())
  const [showSelectionCheckbox, setShowSelectionCheckbox] = useState(getUsersShowSelectionCheckbox())

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
  }>(initialState.filters)

  // Mark that we're initializing from URL to prevent URL updates during initialization
  useEffect(() => {
    isInitializingFromURLRef.current = true
    const timer = setTimeout(() => {
      isInitializingFromURLRef.current = false
    }, 100)
    return () => clearTimeout(timer)
  }, [])

  // After initialization, ensure URL params are written back to preserve them on refresh
  useEffect(() => {
    if (isInitializingFromURLRef.current) return

    const searchParams = new URLSearchParams()
    if (currentPage > 0) {
      // Store page as 1-indexed in URL (what user sees), convert from 0-indexed internal value
      searchParams.set('page', (currentPage + 1).toString())
    }
    if (itemsPerPage !== getUsersPerPageLimitSize()) {
      searchParams.set('limit', itemsPerPage.toString())
    }
    if (filters.sort && filters.sort !== '-created_at') {
      searchParams.set('sort', filters.sort)
    }
    if (filters.search) {
      searchParams.set('search', filters.search)
    }
    if (filters.proxy_id) {
      searchParams.set('search', filters.proxy_id)
      searchParams.set('is_protocol', 'true')
    } else if (filters.is_protocol) {
      searchParams.set('is_protocol', 'true')
    }
    if (filters.status) {
      searchParams.set('status', filters.status)
    }
    if (filters.admin && filters.admin.length > 0) {
      filters.admin.forEach(admin => searchParams.append('admin', admin))
    }
    if (filters.group && filters.group.length > 0) {
      filters.group.forEach(group => searchParams.append('group', group.toString()))
    }
    updateURLParams(searchParams)
  }, [currentPage, itemsPerPage, filters.sort, filters.search, filters.proxy_id, filters.is_protocol, filters.status, filters.admin, filters.group])

  // Initialize advance search form from URL params
  const getInitialAdvanceSearchValues = (): AdvanceSearchFormValue => {
    const searchParams = getSearchParams()
    const urlParams = parseURLParams(searchParams, getUsersPerPageLimitSize())

    return {
      is_username: !urlParams.isProtocol,
      is_protocol: urlParams.isProtocol,
      show_created_by: getUsersShowCreatedBy(),
      show_selection_checkbox: getUsersShowSelectionCheckbox(),
      admin: urlParams.admin || [],
      group: urlParams.group || [],
      status: urlParams.status || '0',
    }
  }

  const advanceSearchForm = useForm<AdvanceSearchFormValue>({
    defaultValues: getInitialAdvanceSearchValues(),
  }) as any

  const userForm = useForm<UseEditFormValues>({
    defaultValues: {
      username: selectedUser?.username,
      status: selectedUser?.status === 'active' || selectedUser?.status === 'on_hold' || selectedUser?.status === 'disabled' ? selectedUser?.status : 'active',
      data_limit: selectedUser?.data_limit ? bytesToFormGigabytes(Number(selectedUser.data_limit)) : undefined,
      expire: normalizeExpireForEditForm(selectedUser?.expire),
      note: selectedUser?.note || '',
      data_limit_reset_strategy: selectedUser?.data_limit_reset_strategy || undefined,
      group_ids: selectedUser?.group_ids || [],
      on_hold_expire_duration: selectedUser?.on_hold_expire_duration || undefined,
      on_hold_timeout: selectedUser?.on_hold_timeout || undefined,
      proxy_settings: selectedUser?.proxy_settings || undefined,
      next_plan: selectedUser?.next_plan
        ? {
          user_template_id: selectedUser?.next_plan.user_template_id ? Number(selectedUser?.next_plan.user_template_id) : undefined,
          data_limit: selectedUser?.next_plan.data_limit ? Math.round(Number(selectedUser?.next_plan.data_limit)) : undefined,
          expire: selectedUser?.next_plan.expire ? Math.round(Number(selectedUser?.next_plan.expire)) : undefined,
          add_remaining_traffic: selectedUser?.next_plan.add_remaining_traffic || false,
        }
        : undefined,
    },
  })

  useEffect(() => {
    if (selectedUser) {
      const values: UseEditFormValues = {
        username: selectedUser.username,
        status: selectedUser.status === 'active' || selectedUser.status === 'on_hold' || selectedUser.status === 'disabled' ? selectedUser.status : 'active',
        data_limit: selectedUser.data_limit ? bytesToFormGigabytes(Number(selectedUser.data_limit)) : 0,
        expire: normalizeExpireForEditForm(selectedUser.expire),
        note: selectedUser.note || '',
        data_limit_reset_strategy: selectedUser.data_limit_reset_strategy || undefined,
        group_ids: selectedUser.group_ids || [],
        on_hold_expire_duration: selectedUser.on_hold_expire_duration || undefined,
        on_hold_timeout: selectedUser.on_hold_timeout || undefined,
        proxy_settings: selectedUser.proxy_settings || undefined,
        next_plan: selectedUser.next_plan
          ? {
            user_template_id: selectedUser.next_plan.user_template_id ? Number(selectedUser.next_plan.user_template_id) : undefined,
            data_limit: selectedUser.next_plan.data_limit ? Math.round(Number(selectedUser.next_plan.data_limit)) : undefined,
            expire: selectedUser.next_plan.expire ? Math.round(Number(selectedUser.next_plan.expire)) : undefined,
            add_remaining_traffic: selectedUser.next_plan.add_remaining_traffic || false,
          }
          : undefined,
      }
      userForm.reset(values)
    }
  }, [selectedUser, userForm])

  useEffect(() => {
    setFilters(prev => ({
      ...prev,
      limit: itemsPerPage,
      offset: currentPage * itemsPerPage,
    }))
  }, [currentPage, itemsPerPage])

  useEffect(() => {
    if (isAdvanceSearchOpen) {
      advanceSearchForm.setValue('status', filters.status || '0')
      advanceSearchForm.setValue('admin', filters.admin || [])
      advanceSearchForm.setValue('group', filters.group || [])
      advanceSearchForm.setValue('show_created_by', showCreatedBy)
      advanceSearchForm.setValue('show_selection_checkbox', showSelectionCheckbox)
    }
  }, [isAdvanceSearchOpen, filters.status, filters.admin, filters.group, showCreatedBy, showSelectionCheckbox, advanceSearchForm])

  const {
    data: usersData,
    refetch,
    isLoading,
    isFetching,
  } = useGetUsers(filters, {
    query: {
      staleTime: 0,
      gcTime: 0,
      retry: 1,
      placeholderData: previousData => previousData,
    },
  })

  // Listen for hash changes (e.g., browser back/forward or manual URL changes)
  useEffect(() => {
    const handleHashChange = () => {
      if (isInitializingFromURLRef.current) return

      const searchParams = getSearchParams()
      const urlParams = parseURLParams(searchParams, itemsPerPage)

      // Only update if values actually changed to avoid infinite loops
      if (urlParams.page !== currentPage) {
        setCurrentPage(urlParams.page)
      }
      if (urlParams.limit !== itemsPerPage) {
        setItemsPerPage(urlParams.limit)
      }
      if (urlParams.sort !== filters.sort) {
        setFilters(prev => ({ ...prev, sort: urlParams.sort }))
      }
      if (urlParams.search !== filters.search && urlParams.search !== filters.proxy_id) {
        if (urlParams.isProtocol) {
          setFilters(prev => ({ ...prev, proxy_id: urlParams.search, search: undefined, is_protocol: true }))
        } else {
          setFilters(prev => ({ ...prev, search: urlParams.search, proxy_id: undefined, is_protocol: false }))
        }
      }
      if (urlParams.status !== filters.status) {
        setFilters(prev => ({ ...prev, status: urlParams.status }))
      }
      if (JSON.stringify(urlParams.admin) !== JSON.stringify(filters.admin)) {
        setFilters(prev => ({ ...prev, admin: urlParams.admin }))
      }
      if (JSON.stringify(urlParams.group) !== JSON.stringify(filters.group)) {
        setFilters(prev => ({ ...prev, group: urlParams.group }))
      }
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [currentPage, itemsPerPage, filters.sort, filters.search, filters.proxy_id, filters.status, filters.admin, filters.group])

  useEffect(() => {
    if (usersData && isFirstLoadRef.current) {
      isFirstLoadRef.current = false
    }
  }, [usersData])

  useEffect(() => {
    if (!isFetching && isAutoRefreshingRef.current) {
      isAutoRefreshingRef.current = false
    }
  }, [isFetching])

  const handleSort = useCallback(
    (column: string, fromDropdown = false) => {
      if (isSorting) return

      setIsSorting(true)

      let newSort: string

      const cleanColumn = column.startsWith('-') ? column.slice(1) : column

      if (fromDropdown) {
        if (column.startsWith('-')) {
          if (filters.sort === '-' + cleanColumn) {
            newSort = '-created_at'
          } else {
            newSort = '-' + cleanColumn
          }
        } else {
          if (filters.sort === cleanColumn) {
            newSort = '-created_at'
          } else {
            newSort = cleanColumn
          }
        }
      } else {
        if (filters.sort === cleanColumn) {
          newSort = '-' + cleanColumn
        } else if (filters.sort === '-' + cleanColumn) {
          newSort = '-created_at'
        } else {
          newSort = cleanColumn
        }
      }

      setFilters(prev => ({ ...prev, sort: newSort }))

      setTimeout(() => setIsSorting(false), 100)
    },
    [filters.sort, isSorting],
  )

  const handleStatusFilter = useCallback(
    (value: any) => {
      advanceSearchForm.setValue('status', value || '0')

      if (value === '0' || value === '') {
        setFilters(prev => ({
          ...prev,
          status: undefined,
          offset: 0,
        }))
      } else {
        setFilters(prev => ({
          ...prev,
          status: value,
          offset: 0,
        }))
      }

      setCurrentPage(0)
    },
    [advanceSearchForm],
  )

  const handleFilterChange = useCallback(
    (newFilters: Partial<typeof filters>) => {
      setFilters(prev => {
        let updated = { ...prev, ...newFilters }
        if ('search' in newFilters) {
          // Only reset offset and page if search actually changed
          const searchChanged = newFilters.search !== prev.search && newFilters.search !== prev.proxy_id
          if (searchChanged) {
            if (prev.is_protocol) {
              updated.proxy_id = newFilters.search
              updated.search = undefined
            } else {
              updated.search = newFilters.search
              updated.proxy_id = undefined
            }
            updated.offset = 0
          } else {
            // Preserve current offset if search didn't change
            updated.offset = prev.offset
          }
        }
        return updated
      })

      // Only reset page if search actually changed
      if (newFilters.search !== undefined && newFilters.search !== filters.search && newFilters.search !== filters.proxy_id) {
        setCurrentPage(0)
      }
    },
    [filters.search, filters.proxy_id],
  )

  const handleManualRefresh = async () => {
    isAutoRefreshingRef.current = false
    return refetch()
  }

  const handleAutoRefresh = async () => {
    isAutoRefreshingRef.current = true
    return refetch()
  }

  const clearSelection = useCallback(() => {
    setResetSelectionKey(prev => prev + 1)
    setSelectedUserIds([])
  }, [])

  const invalidateUsers = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['/api/users'] })
  }, [queryClient])

  const selectedCount = selectedUserIds.length
  const selectedUsers = (usersData?.users || []).filter(user => selectedUserIds.includes(user.id))
  const selectedDisableEligibleIds = selectedUsers.filter(user => user.status !== 'disabled').map(user => user.id)
  const selectedEnableEligibleIds = selectedUsers.filter(user => user.status === 'disabled').map(user => user.id)
  const disableEligibleCount = selectedDisableEligibleIds.length
  const enableEligibleCount = selectedEnableEligibleIds.length

  useEffect(() => {
    if (!showSelectionCheckbox && selectedUserIds.length > 0) {
      clearSelection()
    }
  }, [clearSelection, selectedUserIds.length, showSelectionCheckbox])

  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) => bulkDeleteUsers({ ids }),
    onSuccess: response => {
      invalidateUsers()
      clearSelection()
      toast.success(t('bulkUserActions.deleteSuccess', { count: response.count }))
    },
    onError: (error: any) => {
      toast.error(t('bulkUserActions.deleteError'), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const resetUsageMutation = useMutation({
    mutationFn: (ids: number[]) => bulkResetUsersDataUsage({ ids }),
    onSuccess: response => {
      invalidateUsers()
      clearSelection()
      toast.success(t('bulkUserActions.resetSuccess', { count: response.count }))
    },
    onError: (error: any) => {
      toast.error(t('bulkUserActions.resetError'), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const revokeSubscriptionMutation = useMutation({
    mutationFn: (ids: number[]) => bulkRevokeUsersSubscription({ ids }),
    onSuccess: response => {
      invalidateUsers()
      clearSelection()
      toast.success(t('bulkUserActions.revokeSuccess', { count: response.count }))
    },
    onError: (error: any) => {
      toast.error(t('bulkUserActions.revokeError'), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const disableUsersMutation = useMutation({
    mutationFn: (ids: number[]) => bulkDisableUsers({ ids }),
    onSuccess: response => {
      invalidateUsers()
      clearSelection()
      toast.success(t('bulkUserActions.disableSuccess', { count: response.count, defaultValue: '{{count}} users disabled successfully.' }))
    },
    onError: (error: any) => {
      toast.error(t('bulkUserActions.disableError', { defaultValue: 'Failed to disable selected users.' }), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const enableUsersMutation = useMutation({
    mutationFn: (ids: number[]) => bulkEnableUsers({ ids }),
    onSuccess: response => {
      invalidateUsers()
      clearSelection()
      toast.success(t('bulkUserActions.enableSuccess', { count: response.count, defaultValue: '{{count}} users enabled successfully.' }))
    },
    onError: (error: any) => {
      toast.error(t('bulkUserActions.enableError', { defaultValue: 'Failed to enable selected users.' }), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const handleBulkDelete = async () => {
    if (!selectedUserIds.length) return
    await deleteMutation.mutateAsync(selectedUserIds)
  }

  const handleBulkResetUsage = async () => {
    if (!selectedUserIds.length) return
    await resetUsageMutation.mutateAsync(selectedUserIds)
  }

  const handleBulkRevokeSubscription = async () => {
    if (!selectedUserIds.length) return
    await revokeSubscriptionMutation.mutateAsync(selectedUserIds)
  }

  const handleBulkDisableUsers = async () => {
    if (!selectedDisableEligibleIds.length) return
    await disableUsersMutation.mutateAsync(selectedDisableEligibleIds)
  }

  const handleBulkEnableUsers = async () => {
    if (!selectedEnableEligibleIds.length) return
    await enableUsersMutation.mutateAsync(selectedEnableEligibleIds)
  }

  const bulkActions: BulkActionItem[] = selectedCount
    ? [
      {
        key: 'delete',
        label: t('usersTable.delete'),
        icon: Trash2,
        onClick: () => setBulkAction('delete'),
        direct: true,
        destructive: true,
      },
      {
        key: 'reset',
        label: t('userDialog.resetUsage'),
        icon: RefreshCcw,
        onClick: () => setBulkAction('reset'),
      },
      {
        key: 'revoke',
        label: t('userDialog.revokeSubscription'),
        icon: Link2Off,
        onClick: () => setBulkAction('revoke'),
      },
      ...(        isSudo
        ? [
          {
            key: 'owner',
            label: t('setOwnerModal.title'),
            icon: UserCog,
            onClick: () => setIsBulkSetOwnerModalOpen(true),
          } as BulkActionItem,
        ]
        : []),
      {
        key: 'apply_template',
        label: t('bulk.applyTemplate'),
        icon: Layers,
        onClick: () => setIsBulkApplyTemplateModalOpen(true),
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
    ]
    : []

  const handlePageChange = (newPage: number) => {
    if (newPage === currentPage || isChangingPage) return

    setIsChangingPage(true)
    setCurrentPage(newPage)
    setIsChangingPage(false)
  }

  const handleItemsPerPageChange = (value: number) => {
    setIsChangingPage(true)
    setItemsPerPage(value)
    setCurrentPage(0)
    setUsersPerPageLimitSize(value.toString())
    setIsChangingPage(false)
  }

  const handleEdit = (user: UserResponse) => {
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

    setSelectedUser(latestUser)
    setEditModalOpen(true)
  }

  const handleEditSuccess = (_updatedUser: UserResponse) => {
    setEditModalOpen(false)
  }

  const handleEditModalClose = (open: boolean) => {
    setEditModalOpen(open)
    if (!open) {
      setSelectedUser(null)
    }
  }

  const columns = useMemo(
    () =>
      setupColumns({
        t,
        dir,
        showCreatedBy: isSudo && showCreatedBy,
        showSelectionCheckbox,
        handleSort,
        filters: {
          sort: filters.sort,
          status: filters.status,
        },
        handleStatusFilter,
      }),
    [t, dir, isSudo, showCreatedBy, showSelectionCheckbox, handleSort, filters.sort, filters.status, handleStatusFilter],
  )

  const handleAdvanceSearchSubmit = async (values: AdvanceSearchFormValue) => {
    if (isAdvanceSearchApplying) return

    const nextFilters = {
      ...filters,
      admin: values.admin && values.admin.length > 0 ? values.admin : undefined,
      group: values.group && values.group.length > 0 ? values.group : undefined,
      status: values.status && values.status !== '0' ? values.status : undefined,
      is_protocol: values.is_protocol,
      offset: 0,
    }

    setIsAdvanceSearchApplying(true)

    try {
      try {
        await queryClient.fetchQuery(
          getGetUsersQueryOptions(nextFilters, {
            query: {
              staleTime: 0,
              gcTime: 0,
              retry: 1,
            },
          }),
        )
      } catch {
        // Preserve previous behavior: apply filters even if the eager fetch fails.
      }

      if (isSudo) {
        setShowCreatedBy(values.show_created_by)
        setUsersShowCreatedBy(values.show_created_by)
      }
      setShowSelectionCheckbox(values.show_selection_checkbox)
      setUsersShowSelectionCheckbox(values.show_selection_checkbox)
      if (!values.show_selection_checkbox) {
        clearSelection()
      }
      setFilters(() => ({
        ...nextFilters,
      }))
      setCurrentPage(0)
      setIsAdvanceSearchOpen(false)
      advanceSearchForm.reset(values)
    } finally {
      setIsAdvanceSearchApplying(false)
    }
  }

  const handleClearAdvanceSearch = () => {
    if (isAdvanceSearchApplying) return

    advanceSearchForm.reset({
      is_username: true,
      is_protocol: false,
      show_created_by: showCreatedBy,
      show_selection_checkbox: showSelectionCheckbox,
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
  }

  const totalUsers = usersData?.total || 0
  const totalPages = Math.ceil(totalUsers / itemsPerPage)
  const isPageLoading = isChangingPage || (isFetching && !isFirstLoadRef.current && !isAutoRefreshingRef.current)
  const hasActiveFilters = !!(filters.search || filters.proxy_id || filters.status || filters.admin?.length || filters.group?.length)
  const usersList = usersData?.users || []
  const isCurrentlyLoading = isLoading || (isFetching && !usersData)
  const isEmpty = !isCurrentlyLoading && usersList.length === 0 && totalUsers === 0 && !hasActiveFilters
  const isSearchEmpty = !isCurrentlyLoading && usersList.length === 0 && hasActiveFilters

  return (
    <div>
      <Filters
        filters={filters}
        onFilterChange={handleFilterChange}
        advanceSearchOnOpen={setIsAdvanceSearchOpen}
        refetch={handleManualRefresh}
        autoRefetch={handleAutoRefresh}
        handleSort={handleSort}
        onClearAdvanceSearch={handleClearAdvanceSearch}
      />
      <BulkActionsBar
        selectedCount={selectedCount}
        onClear={clearSelection}
        actions={bulkActions}
      />
      {isEmpty && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('users.noUsers')}</h3>
              <p className="mx-auto max-w-2xl text-muted-foreground">{t('users.noUsersDescription')}</p>
            </div>
          </CardContent>
        </Card>
      )}
      {isSearchEmpty && (
        <Card className="mb-12">
          <CardContent className="p-8 text-center">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">{t('noResults')}</h3>
              <p className="mx-auto max-w-2xl text-muted-foreground">{t('users.noSearchResults')}</p>
            </div>
          </CardContent>
        </Card>
      )}
      {isCurrentlyLoading && !isSearchEmpty && (
        <DataTable columns={columns} data={[]} isLoading={true} isFetching={false} onEdit={handleEdit} onSelectionChange={setSelectedUserIds} resetSelectionKey={resetSelectionKey} />
      )}
      {!isEmpty && !isSearchEmpty && !isCurrentlyLoading && (
        <DataTable
          columns={columns}
          data={usersList}
          isLoading={false}
          isFetching={isFetching && !isFirstLoadRef.current && !isAutoRefreshingRef.current}
          onEdit={handleEdit}
          onSelectionChange={setSelectedUserIds}
          resetSelectionKey={resetSelectionKey}
        />
      )}
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
          onOpenChange={handleEditModalClose}
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
            if (isAdvanceSearchApplying && !open) return
            setIsAdvanceSearchOpen(open)
            if (!open) advanceSearchForm.reset()
          }}
          form={advanceSearchForm}
          onSubmit={handleAdvanceSearchSubmit}
          isSudo={isSudo}
          isApplying={isAdvanceSearchApplying}
        />
      )}
      <BulkActionAlertDialog
        open={bulkAction === 'delete'}
        onOpenChange={open => setBulkAction(open ? 'delete' : null)}
        title={t('bulkUserActions.deleteTitle')}
        description={t('bulkUserActions.deletePrompt', { count: selectedCount })}
        actionLabel={t('usersTable.delete')}
        onConfirm={handleBulkDelete}
        isPending={deleteMutation.isPending}
        destructive
      />
      <BulkActionAlertDialog
        open={bulkAction === 'reset'}
        onOpenChange={open => setBulkAction(open ? 'reset' : null)}
        title={t('bulkUserActions.resetTitle')}
        description={t('bulkUserActions.resetPrompt', { count: selectedCount })}
        actionLabel={t('usersTable.resetUsageSubmit')}
        onConfirm={handleBulkResetUsage}
        isPending={resetUsageMutation.isPending}
      />
      <BulkActionAlertDialog
        open={bulkAction === 'revoke'}
        onOpenChange={open => setBulkAction(open ? 'revoke' : null)}
        title={t('bulkUserActions.revokeTitle')}
        description={t('bulkUserActions.revokePrompt', { count: selectedCount })}
        actionLabel={t('revokeUserSub.title')}
        onConfirm={handleBulkRevokeSubscription}
        isPending={revokeSubscriptionMutation.isPending}
      />
      <BulkActionAlertDialog
        open={bulkAction === 'disable'}
        onOpenChange={open => setBulkAction(open ? 'disable' : null)}
        title={t('bulkUserActions.disableTitle', { defaultValue: 'Disable Selected Users' })}
        description={t('bulkUserActions.disablePrompt', {
          count: disableEligibleCount,
          defaultValue: 'Are you sure you want to disable {{count}} selected users?',
        })}
        actionLabel={t('disable')}
        onConfirm={handleBulkDisableUsers}
        isPending={disableUsersMutation.isPending}
      />
      <BulkActionAlertDialog
        open={bulkAction === 'enable'}
        onOpenChange={open => setBulkAction(open ? 'enable' : null)}
        title={t('bulkUserActions.enableTitle', { defaultValue: 'Enable Selected Users' })}
        description={t('bulkUserActions.enablePrompt', {
          count: enableEligibleCount,
          defaultValue: 'Are you sure you want to enable {{count}} selected users?',
        })}
        actionLabel={t('enable')}
        onConfirm={handleBulkEnableUsers}
        isPending={enableUsersMutation.isPending}
      />
      <SetOwnerModal
        open={isBulkSetOwnerModalOpen}
        onClose={() => setIsBulkSetOwnerModalOpen(false)}
        userIds={selectedUserIds}
        selectedCount={selectedCount}
        onSuccess={() => {
          invalidateUsers()
          clearSelection()
        }}
      />
      <ApplyTemplateModal
        open={isBulkApplyTemplateModalOpen}
        onClose={() => setIsBulkApplyTemplateModalOpen(false)}
        userIds={selectedUserIds}
        selectedCount={selectedCount}
        onSuccess={() => {
          invalidateUsers()
          clearSelection()
        }}
      />
      <ActionButtonsModalHost />
    </div>
  )
})

export default UsersTable
