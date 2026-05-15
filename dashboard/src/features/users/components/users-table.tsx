import { setupColumns } from '@/features/users/components/columns'
import { ActionButtonsModalHost } from '@/features/users/components/action-buttons'
import SetOwnerModal from '@/features/users/dialogs/set-owner-modal'
import ApplyTemplateModal from '@/features/templates/dialogs/apply-template-modal'
import { DataTable } from '@/features/users/components/data-table'
import { Filters } from '@/features/users/components/filters'
import { type UseEditFormValues } from '@/features/users/forms/user-form'
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
import { bytesToFormGigabytes, gbToBytes } from '@/utils/formatByte'
import { normalizeDatePickerValueForEditForm } from '@/utils/userEditDateUtils'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { endOfDay, startOfDay } from 'date-fns'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Layers, Link2Off, Power, PowerOff, RefreshCcw, Trash2, UserCog } from 'lucide-react'
import UserModal from '../dialogs/user-modal'
import { PaginationControls } from './filters'
import AdvanceSearchModal from '@/features/users/dialogs/advance-search-modal'
import type { AdvanceSearchFormValue } from '@/features/users/forms/advance-search-form'
import { BulkActionItem, BulkActionsBar } from '@/features/users/components/bulk-actions-bar'
import { BulkActionAlertDialog } from '@/features/users/components/bulk-action-alert-dialog'
import { Card, CardContent } from '@/components/ui/card'
import { removeUsersFromUsersCache } from '@/utils/usersCache'

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

const parseOptionalPositiveNumber = (value: string | null) => {
  if (!value) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

const parseOptionalDateString = (value: string | null) => {
  if (!value) return undefined
  return Number.isNaN(Date.parse(value)) ? undefined : value
}

const toOptionalBytesFilter = (gigabytes: number | undefined) => {
  if (gigabytes === undefined || !Number.isFinite(gigabytes) || gigabytes <= 0) return undefined
  return gbToBytes(gigabytes)
}

const parseBooleanFlag = (value: string | null) => value === 'true'

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
  const dataLimitMin = parseOptionalPositiveNumber(searchParams.get('data_limit_min'))
  const dataLimitMax = parseOptionalPositiveNumber(searchParams.get('data_limit_max'))
  const expireAfter = parseOptionalDateString(searchParams.get('expire_after'))
  const expireBefore = parseOptionalDateString(searchParams.get('expire_before'))
  const onlineAfter = parseOptionalDateString(searchParams.get('online_after'))
  const onlineBefore = parseOptionalDateString(searchParams.get('online_before'))
  const online = parseBooleanFlag(searchParams.get('online'))
  const noDataLimit = parseBooleanFlag(searchParams.get('no_data_limit'))
  const noExpire = parseBooleanFlag(searchParams.get('no_expire'))

  return {
    page: Math.max(0, page),
    limit: limit > 0 ? limit : defaultItemsPerPage,
    sort,
    search,
    status,
    admin: admin.length > 0 ? admin : undefined,
    group: group.length > 0 ? group : undefined,
    isProtocol,
    dataLimitMin: noDataLimit ? undefined : dataLimitMin,
    dataLimitMax: noDataLimit ? undefined : dataLimitMax,
    expireAfter: noExpire ? undefined : expireAfter,
    expireBefore: noExpire ? undefined : expireBefore,
    onlineAfter: online ? undefined : onlineAfter,
    onlineBefore: online ? undefined : onlineBefore,
    online,
    noDataLimit,
    noExpire,
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
        search: urlParams.isProtocol ? undefined : urlParams.search,
        proxy_id: urlParams.isProtocol && urlParams.search ? urlParams.search : undefined,
        is_protocol: urlParams.isProtocol,
        status: urlParams.status || undefined,
        admin: urlParams.admin,
        group: urlParams.group,
        data_limit_min: toOptionalBytesFilter(urlParams.dataLimitMin),
        data_limit_max: toOptionalBytesFilter(urlParams.dataLimitMax),
        expire_after: urlParams.expireAfter,
        expire_before: urlParams.expireBefore,
        online_after: urlParams.onlineAfter,
        online_before: urlParams.onlineBefore,
        online: urlParams.online || undefined,
        no_data_limit: urlParams.noDataLimit || undefined,
        no_expire: urlParams.noExpire || undefined,
      },
    }
  }

  const initialState = getInitialStateFromURL()
  const [currentPage, setCurrentPage] = useState(initialState.page)
  const [itemsPerPage, setItemsPerPage] = useState(initialState.limit)
  const [isChangingPage, setIsChangingPage] = useState(false)
  const [isEditModalOpen, setEditModalOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null)
  const clearSelectedUserTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([])
  const [resetSelectionKey, setResetSelectionKey] = useState(0)
  const [bulkAction, setBulkAction] = useState<'delete' | 'reset' | 'revoke' | 'disable' | 'enable' | 'apply_template' | null>(null)
  const [isBulkSetOwnerModalOpen, setIsBulkSetOwnerModalOpen] = useState(false)
  const [isBulkApplyTemplateModalOpen, setIsBulkApplyTemplateModalOpen] = useState(false)
  const [isAdvanceSearchOpen, setIsAdvanceSearchOpen] = useState(false)
  const [isAdvanceSearchApplying, setIsAdvanceSearchApplying] = useState(false)
  const resetAdvanceSearchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
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
    data_limit_min?: number | null
    data_limit_max?: number | null
    expire_after?: string | null
    expire_before?: string | null
    online_after?: string | null
    online_before?: string | null
    online?: boolean
    no_data_limit?: boolean
    no_expire?: boolean
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
    if (filters.data_limit_min) {
      searchParams.set('data_limit_min', String(bytesToFormGigabytes(filters.data_limit_min)))
    }
    if (filters.data_limit_max) {
      searchParams.set('data_limit_max', String(bytesToFormGigabytes(filters.data_limit_max)))
    }
    if (filters.expire_after) {
      searchParams.set('expire_after', filters.expire_after)
    }
    if (filters.expire_before) {
      searchParams.set('expire_before', filters.expire_before)
    }
    if (filters.online_after) {
      searchParams.set('online_after', filters.online_after)
    }
    if (filters.online_before) {
      searchParams.set('online_before', filters.online_before)
    }
    if (filters.online) {
      searchParams.set('online', 'true')
    }
    if (filters.no_data_limit) {
      searchParams.set('no_data_limit', 'true')
    }
    if (filters.no_expire) {
      searchParams.set('no_expire', 'true')
    }
    updateURLParams(searchParams)
  }, [currentPage, itemsPerPage, filters.sort, filters.search, filters.proxy_id, filters.is_protocol, filters.status, filters.admin, filters.group, filters.data_limit_min, filters.data_limit_max, filters.expire_after, filters.expire_before, filters.online_after, filters.online_before, filters.online, filters.no_data_limit, filters.no_expire])

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
      no_data_limit: urlParams.noDataLimit,
      no_expire: urlParams.noExpire,
      data_limit_min: urlParams.dataLimitMin,
      data_limit_max: urlParams.dataLimitMax,
      expire_after: urlParams.expireAfter ? new Date(urlParams.expireAfter) : undefined,
      expire_before: urlParams.expireBefore ? new Date(urlParams.expireBefore) : undefined,
      online_after: urlParams.onlineAfter ? new Date(urlParams.onlineAfter) : undefined,
      online_before: urlParams.onlineBefore ? new Date(urlParams.onlineBefore) : undefined,
      online: urlParams.online,
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
      hwid_limit: selectedUser?.hwid_limit ?? undefined,
      expire: normalizeDatePickerValueForEditForm(selectedUser?.expire),
      note: selectedUser?.note || '',
      data_limit_reset_strategy: selectedUser?.data_limit_reset_strategy || undefined,
      group_ids: selectedUser?.group_ids || [],
      on_hold_expire_duration: selectedUser?.on_hold_expire_duration || undefined,
      on_hold_timeout: normalizeDatePickerValueForEditForm(selectedUser?.on_hold_timeout),
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
        hwid_limit: selectedUser.hwid_limit ?? undefined,
        expire: normalizeDatePickerValueForEditForm(selectedUser.expire),
        note: selectedUser.note || '',
        data_limit_reset_strategy: selectedUser.data_limit_reset_strategy || undefined,
        group_ids: selectedUser.group_ids || [],
        on_hold_expire_duration: selectedUser.on_hold_expire_duration || undefined,
        on_hold_timeout: normalizeDatePickerValueForEditForm(selectedUser.on_hold_timeout),
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
      advanceSearchForm.setValue('is_protocol', Boolean(filters.proxy_id || filters.is_protocol))
      advanceSearchForm.setValue('is_username', !Boolean(filters.proxy_id || filters.is_protocol))
      advanceSearchForm.setValue('show_created_by', showCreatedBy)
      advanceSearchForm.setValue('show_selection_checkbox', showSelectionCheckbox)
      advanceSearchForm.setValue('no_data_limit', Boolean(filters.no_data_limit))
      advanceSearchForm.setValue('no_expire', Boolean(filters.no_expire))
      advanceSearchForm.setValue('data_limit_min', filters.data_limit_min ? bytesToFormGigabytes(filters.data_limit_min) : undefined)
      advanceSearchForm.setValue('data_limit_max', filters.data_limit_max ? bytesToFormGigabytes(filters.data_limit_max) : undefined)
      advanceSearchForm.setValue('expire_after', filters.expire_after ? new Date(filters.expire_after) : undefined)
      advanceSearchForm.setValue('expire_before', filters.expire_before ? new Date(filters.expire_before) : undefined)
      advanceSearchForm.setValue('online_after', filters.online_after ? new Date(filters.online_after) : undefined)
      advanceSearchForm.setValue('online_before', filters.online_before ? new Date(filters.online_before) : undefined)
      advanceSearchForm.setValue('online', Boolean(filters.online))
    }
  }, [isAdvanceSearchOpen, filters.status, filters.admin, filters.group, filters.proxy_id, filters.is_protocol, filters.data_limit_min, filters.data_limit_max, filters.expire_after, filters.expire_before, filters.online_after, filters.online_before, filters.online, filters.no_data_limit, filters.no_expire, showCreatedBy, showSelectionCheckbox, advanceSearchForm])

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
      const currentSearch = filters.proxy_id || filters.search
      const nextIsProtocol = Boolean(urlParams.isProtocol && urlParams.search)
      if (urlParams.search !== currentSearch || nextIsProtocol !== filters.is_protocol) {
        if (nextIsProtocol) {
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
      const nextDataLimitMin = toOptionalBytesFilter(urlParams.dataLimitMin)
      if (nextDataLimitMin !== filters.data_limit_min) {
        setFilters(prev => ({ ...prev, data_limit_min: nextDataLimitMin }))
      }
      const nextDataLimitMax = toOptionalBytesFilter(urlParams.dataLimitMax)
      if (nextDataLimitMax !== filters.data_limit_max) {
        setFilters(prev => ({ ...prev, data_limit_max: nextDataLimitMax }))
      }
      if (urlParams.expireAfter !== filters.expire_after) {
        setFilters(prev => ({ ...prev, expire_after: urlParams.expireAfter }))
      }
      if (urlParams.expireBefore !== filters.expire_before) {
        setFilters(prev => ({ ...prev, expire_before: urlParams.expireBefore }))
      }
      if (urlParams.onlineAfter !== filters.online_after) {
        setFilters(prev => ({ ...prev, online_after: urlParams.onlineAfter }))
      }
      if (urlParams.onlineBefore !== filters.online_before) {
        setFilters(prev => ({ ...prev, online_before: urlParams.onlineBefore }))
      }
      const nextOnline = urlParams.online || undefined
      if (nextOnline !== filters.online) {
        setFilters(prev => ({ ...prev, online: nextOnline }))
      }
      const nextNoDataLimit = urlParams.noDataLimit || undefined
      if (nextNoDataLimit !== filters.no_data_limit) {
        setFilters(prev => ({ ...prev, no_data_limit: nextNoDataLimit }))
      }
      const nextNoExpire = urlParams.noExpire || undefined
      if (nextNoExpire !== filters.no_expire) {
        setFilters(prev => ({ ...prev, no_expire: nextNoExpire }))
      }
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [currentPage, itemsPerPage, filters.sort, filters.search, filters.proxy_id, filters.is_protocol, filters.status, filters.admin, filters.group, filters.data_limit_min, filters.data_limit_max, filters.expire_after, filters.expire_before, filters.online_after, filters.online_before, filters.online, filters.no_data_limit, filters.no_expire])

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
          const nextSearch = newFilters.search?.trim() || undefined
          const currentSearch = prev.proxy_id || prev.search
          const nextIsProtocol = nextSearch ? (newFilters.is_protocol ?? prev.is_protocol) : false
          // Only reset offset and page if search actually changed
          const searchChanged = nextSearch !== currentSearch || nextIsProtocol !== prev.is_protocol
          if (searchChanged) {
            if (nextIsProtocol) {
              updated.proxy_id = nextSearch
              updated.search = undefined
            } else {
              updated.search = nextSearch
              updated.proxy_id = undefined
            }
            updated.is_protocol = nextIsProtocol
            updated.offset = 0
          } else {
            // Preserve current offset if search didn't change
            updated.offset = prev.offset
          }
        }
        return updated
      })

      const nextSearch = newFilters.search?.trim() || undefined
      const currentSearch = filters.proxy_id || filters.search
      const nextIsProtocol = nextSearch ? (newFilters.is_protocol ?? filters.is_protocol) : false
      // Only reset page if search actually changed
      if ('search' in newFilters && (nextSearch !== currentSearch || nextIsProtocol !== filters.is_protocol)) {
        setCurrentPage(0)
      }
    },
    [filters.search, filters.proxy_id, filters.is_protocol],
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
    onSuccess: (response, ids) => {
      removeUsersFromUsersCache(queryClient, selectedUsers.filter(user => ids.includes(user.id)))
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
    if (clearSelectedUserTimeoutRef.current) {
      clearTimeout(clearSelectedUserTimeoutRef.current)
      clearSelectedUserTimeoutRef.current = null
    }

    const cachedData = queryClient.getQueriesData<UsersResponse>({
      queryKey: ['/api/users'],
      exact: false,
    })

    let latestUser = user
    for (const [, data] of cachedData) {
      if (data?.users) {
        const foundUser = data.users.find(u => u.id === user.id)
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
    handleEditModalClose(false)
  }

  const handleEditModalClose = (open: boolean) => {
    if (open) {
      if (clearSelectedUserTimeoutRef.current) {
        clearTimeout(clearSelectedUserTimeoutRef.current)
        clearSelectedUserTimeoutRef.current = null
      }
      setEditModalOpen(true)
      return
    }

    setEditModalOpen(false)
    if (clearSelectedUserTimeoutRef.current) {
      clearTimeout(clearSelectedUserTimeoutRef.current)
    }
    clearSelectedUserTimeoutRef.current = setTimeout(() => {
      setSelectedUser(null)
      clearSelectedUserTimeoutRef.current = null
    }, 220)
  }

  useEffect(() => {
    return () => {
      if (clearSelectedUserTimeoutRef.current) {
        clearTimeout(clearSelectedUserTimeoutRef.current)
      }
      if (resetAdvanceSearchTimeoutRef.current) {
        clearTimeout(resetAdvanceSearchTimeoutRef.current)
      }
    }
  }, [])

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
    const currentSearch = filters.proxy_id || filters.search

    const nextFilters = {
      ...filters,
      search: values.is_protocol ? undefined : currentSearch,
      proxy_id: values.is_protocol ? currentSearch : undefined,
      admin: values.admin && values.admin.length > 0 ? values.admin : undefined,
      group: values.group && values.group.length > 0 ? values.group : undefined,
      status: values.status && values.status !== '0' ? values.status : undefined,
      no_data_limit: values.no_data_limit || undefined,
      no_expire: values.no_expire || undefined,
      data_limit_min: values.no_data_limit ? undefined : toOptionalBytesFilter(values.data_limit_min),
      data_limit_max: values.no_data_limit ? undefined : toOptionalBytesFilter(values.data_limit_max),
      expire_after: values.no_expire ? undefined : values.expire_after ? startOfDay(values.expire_after).toISOString() : undefined,
      expire_before: values.no_expire ? undefined : values.expire_before ? endOfDay(values.expire_before).toISOString() : undefined,
      online: values.online || undefined,
      online_after: values.online ? undefined : values.online_after ? startOfDay(values.online_after).toISOString() : undefined,
      online_before: values.online ? undefined : values.online_before ? endOfDay(values.online_before).toISOString() : undefined,
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

  const handleAdvanceSearchOpenChange = (open: boolean) => {
    if (isAdvanceSearchApplying && !open) return

    if (resetAdvanceSearchTimeoutRef.current) {
      clearTimeout(resetAdvanceSearchTimeoutRef.current)
      resetAdvanceSearchTimeoutRef.current = null
    }

    setIsAdvanceSearchOpen(open)
    if (!open) {
      resetAdvanceSearchTimeoutRef.current = setTimeout(() => {
        advanceSearchForm.reset()
        resetAdvanceSearchTimeoutRef.current = null
      }, 220)
    }
  }

  const handleClearAdvanceSearch = () => {
    if (isAdvanceSearchApplying) return

    advanceSearchForm.reset({
      is_username: true,
      is_protocol: false,
      show_created_by: showCreatedBy,
      show_selection_checkbox: showSelectionCheckbox,
      no_data_limit: false,
      no_expire: false,
      online: false,
      admin: [],
      group: [],
      status: '0',
      data_limit_min: undefined,
      data_limit_max: undefined,
      expire_after: undefined,
      expire_before: undefined,
      online_after: undefined,
      online_before: undefined,
    })
    setFilters(prev => ({
      ...prev,
      admin: undefined,
      group: undefined,
      status: undefined,
      data_limit_min: undefined,
      data_limit_max: undefined,
      expire_after: undefined,
      expire_before: undefined,
      online_after: undefined,
      online_before: undefined,
      online: undefined,
      no_data_limit: undefined,
      no_expire: undefined,
      is_protocol: false,
      proxy_id: undefined,
      offset: 0,
    }))
    setCurrentPage(0)
  }

  const totalUsers = usersData?.total || 0
  const totalPages = Math.ceil(totalUsers / itemsPerPage)
  const isPageLoading = isChangingPage || (isFetching && !isFirstLoadRef.current && !isAutoRefreshingRef.current)
  const hasActiveFilters = !!(
    filters.search ||
    filters.proxy_id ||
    filters.status ||
    filters.admin?.length ||
    filters.group?.length ||
    filters.data_limit_min ||
    filters.data_limit_max ||
    filters.expire_after ||
    filters.expire_before ||
    filters.online_after ||
    filters.online_before ||
    filters.online ||
    filters.no_data_limit ||
    filters.no_expire
  )
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
          isFetching={isPageLoading}
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
      <AdvanceSearchModal
        isDialogOpen={isAdvanceSearchOpen}
        onOpenChange={handleAdvanceSearchOpenChange}
        form={advanceSearchForm}
        onSubmit={handleAdvanceSearchSubmit}
        isSudo={isSudo}
        isApplying={isAdvanceSearchApplying}
      />
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
