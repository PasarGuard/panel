import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type { AdminDetails, AdminsResponse, GetAdminsParams } from '@/service/api'

const ADMINS_QUERY_KEY = '/api/admins'

const toNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

const toTimestamp = (value: unknown): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (!Number.isNaN(parsed)) return parsed
    const asNumber = Number(value)
    if (Number.isFinite(asNumber)) return asNumber
  }
  return 0
}

const readAdminsParamsFromKey = (queryKey: QueryKey): GetAdminsParams | undefined => {
  if (!Array.isArray(queryKey)) return undefined
  if (queryKey[0] !== ADMINS_QUERY_KEY) return undefined
  const maybeParams = queryKey[1]
  if (!maybeParams || typeof maybeParams !== 'object' || Array.isArray(maybeParams)) return undefined
  return maybeParams as GetAdminsParams
}

const includesIgnoreCase = (value: string | null | undefined, needle: string): boolean => {
  if (!value) return false
  return value.toLowerCase().includes(needle.toLowerCase())
}

const isDisabled = (admin: AdminDetails): boolean => !!admin.is_disabled

const getCreatedAt = (admin: AdminDetails): unknown => {
  return (admin as AdminDetails & { created_at?: string | number | null }).created_at
}

const matchesAdminFilters = (admin: AdminDetails, params?: GetAdminsParams): boolean => {
  if (!params) return true

  if (params.username && params.username.trim() !== '') {
    const term = params.username.trim().toLowerCase()
    if (!includesIgnoreCase(admin.username, term)) {
      return false
    }
  }

  return true
}

const compareBySort = (a: AdminDetails, b: AdminDetails, sort?: string | null): number => {
  const resolvedSort = sort && sort.trim() !== '' ? sort : '-created_at'
  const desc = resolvedSort.startsWith('-')
  const field = desc ? resolvedSort.slice(1) : resolvedSort

  let comparison = 0

  switch (field) {
    case 'username':
      comparison = a.username.localeCompare(b.username)
      break
    case 'used_traffic':
      comparison = (a.used_traffic ?? 0) - (b.used_traffic ?? 0)
      break
    case 'created_at':
      comparison = toTimestamp(getCreatedAt(a)) - toTimestamp(getCreatedAt(b))
      break
    default:
      comparison = a.username.localeCompare(b.username)
      break
  }

  return desc ? -comparison : comparison
}

const shouldInsertIntoQueryPage = (params?: GetAdminsParams): boolean => {
  const offset = toNumber(params?.offset) ?? 0
  return offset <= 0
}

const decrementStatusCount = (active: number, disabled: number, admin: AdminDetails) => {
  if (isDisabled(admin)) {
    return { active, disabled: Math.max(0, disabled - 1) }
  }
  return { active: Math.max(0, active - 1), disabled }
}

const incrementStatusCount = (active: number, disabled: number, admin: AdminDetails) => {
  if (isDisabled(admin)) {
    return { active, disabled: disabled + 1 }
  }
  return { active: active + 1, disabled }
}

const upsertInSingleAdminsQuery = (oldData: AdminsResponse, admin: AdminDetails, params: GetAdminsParams | undefined, allowInsert: boolean): AdminsResponse | undefined => {
  const oldAdmins = oldData.admins ?? []
  const existingIndex = oldAdmins.findIndex(a => a.username === admin.username)
  const matchesFilters = matchesAdminFilters(admin, params)

  let admins = oldAdmins
  let total = oldData.total
  let active = oldData.active
  let disabled = oldData.disabled
  let changed = false

  if (existingIndex >= 0) {
    const previous = oldAdmins[existingIndex]

    if (matchesFilters) {
      admins = oldAdmins.map(a => (a.username === admin.username ? admin : a))
      changed = true

      if (isDisabled(previous) !== isDisabled(admin)) {
        if (isDisabled(previous)) {
          disabled = Math.max(0, disabled - 1)
          active += 1
        } else {
          active = Math.max(0, active - 1)
          disabled += 1
        }
      }
    } else {
      admins = oldAdmins.filter(a => a.username !== admin.username)
      total = Math.max(0, total - 1)
      const dec = decrementStatusCount(active, disabled, previous)
      active = dec.active
      disabled = dec.disabled
      changed = true
    }
  } else if (allowInsert && matchesFilters && shouldInsertIntoQueryPage(params)) {
    const resolvedSort = params?.sort && params.sort.trim() !== '' ? params.sort : '-created_at'

    // For default sort (newest first), place created admins at the top immediately.
    if (resolvedSort === '-created_at') {
      admins = [admin, ...oldAdmins]
    } else if (resolvedSort === 'created_at') {
      admins = [...oldAdmins, admin]
    } else {
      admins = [...oldAdmins, admin].sort((a, b) => compareBySort(a, b, resolvedSort))
    }

    total += 1
    const inc = incrementStatusCount(active, disabled, admin)
    active = inc.active
    disabled = inc.disabled
    changed = true
  }

  if (!changed) return undefined

  const pageLimit = toNumber(params?.limit)
  if (pageLimit && pageLimit > 0 && admins.length > pageLimit) {
    admins = admins.slice(0, pageLimit)
  }

  return {
    ...oldData,
    admins,
    total,
    active,
    disabled,
  }
}

export const upsertAdminInAdminsCache = (queryClient: QueryClient, admin: AdminDetails, options?: { allowInsert?: boolean }) => {
  const allowInsert = options?.allowInsert ?? false
  const cachedQueries = queryClient.getQueriesData<AdminsResponse>({
    queryKey: [ADMINS_QUERY_KEY],
    exact: false,
  })

  cachedQueries.forEach(([queryKey, oldData]) => {
    if (!oldData) return
    const params = readAdminsParamsFromKey(queryKey)
    const updatedData = upsertInSingleAdminsQuery(oldData, admin, params, allowInsert)
    if (updatedData) {
      queryClient.setQueryData(queryKey, updatedData)
    }
  })
}

export const removeAdminFromAdminsCache = (queryClient: QueryClient, username: string) => {
  const cachedQueries = queryClient.getQueriesData<AdminsResponse>({
    queryKey: [ADMINS_QUERY_KEY],
    exact: false,
  })

  cachedQueries.forEach(([queryKey, oldData]) => {
    if (!oldData) return
    const existing = oldData.admins.find(a => a.username === username)
    if (!existing) return

    const admins = oldData.admins.filter(a => a.username !== username)
    const total = Math.max(0, oldData.total - 1)
    const dec = decrementStatusCount(oldData.active, oldData.disabled, existing)

    queryClient.setQueryData(queryKey, {
      ...oldData,
      admins,
      total,
      active: dec.active,
      disabled: dec.disabled,
    })
  })
}

export const patchAdminInAdminsCache = (queryClient: QueryClient, username: string, patch: Partial<AdminDetails>) => {
  const cachedQueries = queryClient.getQueriesData<AdminsResponse>({
    queryKey: [ADMINS_QUERY_KEY],
    exact: false,
  })

  cachedQueries.forEach(([queryKey, oldData]) => {
    if (!oldData) return
    const index = oldData.admins.findIndex(a => a.username === username)
    if (index < 0) return

    const oldAdmin = oldData.admins[index]
    const updatedAdmin = { ...oldAdmin, ...patch }
    const admins = oldData.admins.map(a => (a.username === username ? updatedAdmin : a))

    let active = oldData.active
    let disabled = oldData.disabled
    if (isDisabled(oldAdmin) !== isDisabled(updatedAdmin)) {
      if (isDisabled(oldAdmin)) {
        disabled = Math.max(0, disabled - 1)
        active += 1
      } else {
        active = Math.max(0, active - 1)
        disabled += 1
      }
    }

    queryClient.setQueryData(queryKey, {
      ...oldData,
      admins,
      active,
      disabled,
    })
  })
}
