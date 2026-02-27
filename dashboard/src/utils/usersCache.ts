import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type { GetUsersParams, UserResponse, UsersResponse } from '@/service/api'

const USERS_QUERY_KEY = '/api/users'

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

const readUsersParamsFromKey = (queryKey: QueryKey): GetUsersParams | undefined => {
  if (!Array.isArray(queryKey)) return undefined
  if (queryKey[0] !== USERS_QUERY_KEY) return undefined
  const maybeParams = queryKey[1]
  if (!maybeParams || typeof maybeParams !== 'object' || Array.isArray(maybeParams)) return undefined
  return maybeParams as GetUsersParams
}

const includesIgnoreCase = (value: string | null | undefined, needle: string): boolean => {
  if (!value) return false
  return value.toLowerCase().includes(needle.toLowerCase())
}

const getSortableUserValue = (user: UserResponse, field: string): unknown => {
  switch (field) {
    case 'id':
      return user.id
    case 'username':
      return user.username
    case 'status':
      return user.status
    case 'used_traffic':
      return user.used_traffic
    case 'lifetime_used_traffic':
      return user.lifetime_used_traffic
    case 'created_at':
      return user.created_at
    case 'edit_at':
      return user.edit_at
    case 'online_at':
      return user.online_at
    case 'expire':
      return user.expire
    case 'data_limit':
      return user.data_limit
    default:
      return undefined
  }
}

const matchesUserFilters = (user: UserResponse, params?: GetUsersParams): boolean => {
  if (!params) return true

  if (params.status && user.status !== params.status) {
    return false
  }

  if (params.username && params.username.length > 0 && !params.username.includes(user.username)) {
    return false
  }

  if (params.admin && params.admin.length > 0) {
    const adminUsername = user.admin?.username
    if (!adminUsername || !params.admin.includes(adminUsername)) {
      return false
    }
  }

  if (params.group && params.group.length > 0) {
    const groupIds = user.group_ids ?? []
    const hasAnyGroup = params.group.some(groupId => groupIds.includes(groupId))
    if (!hasAnyGroup) {
      return false
    }
  }

  if (params.search && params.search.trim() !== '') {
    const term = params.search.trim().toLowerCase()
    const foundInText = includesIgnoreCase(user.username, term) || includesIgnoreCase(user.note, term)
    if (!foundInText) {
      return false
    }
  }

  if (params.proxy_id && params.proxy_id.trim() !== '') {
    const proxyTerm = params.proxy_id.trim().toLowerCase()
    const proxyPayload = JSON.stringify(user.proxy_settings ?? '').toLowerCase()
    if (!proxyPayload.includes(proxyTerm)) {
      return false
    }
  }

  return true
}

const compareBySort = (a: UserResponse, b: UserResponse, sort?: string | null): number => {
  const resolvedSort = sort && sort.trim() !== '' ? sort : '-created_at'
  const desc = resolvedSort.startsWith('-')
  const field = desc ? resolvedSort.slice(1) : resolvedSort

  let comparison = 0

  if (field === 'created_at' || field === 'edit_at' || field === 'expire') {
    const aValue = toTimestamp(getSortableUserValue(a, field))
    const bValue = toTimestamp(getSortableUserValue(b, field))
    comparison = aValue - bValue
  } else {
    const aRaw = getSortableUserValue(a, field)
    const bRaw = getSortableUserValue(b, field)

    const aNumber = toNumber(aRaw)
    const bNumber = toNumber(bRaw)
    if (aNumber !== undefined && bNumber !== undefined) {
      comparison = aNumber - bNumber
    } else {
      const aText = String(aRaw ?? '')
      const bText = String(bRaw ?? '')
      comparison = aText.localeCompare(bText)
    }
  }

  return desc ? -comparison : comparison
}

const shouldInsertIntoQueryPage = (params?: GetUsersParams): boolean => {
  const offset = toNumber(params?.offset) ?? 0
  return offset <= 0
}

const upsertInSingleUsersQuery = (oldData: UsersResponse, user: UserResponse, params: GetUsersParams | undefined, allowInsert: boolean): UsersResponse | undefined => {
  const oldUsers = oldData.users ?? []
  const existingIndex = oldUsers.findIndex(u => u.username === user.username)
  const matchesFilters = matchesUserFilters(user, params)

  let users = oldUsers
  let total = oldData.total
  let changed = false

  if (existingIndex >= 0) {
    if (matchesFilters) {
      users = oldUsers.map(u => (u.username === user.username ? user : u))
      changed = true
    } else {
      users = oldUsers.filter(u => u.username !== user.username)
      total = Math.max(0, total - 1)
      changed = true
    }
  } else if (allowInsert && matchesFilters && shouldInsertIntoQueryPage(params)) {
    users = [...oldUsers, user].sort((a, b) => compareBySort(a, b, params?.sort))
    total += 1
    changed = true
  }

  if (!changed) {
    return undefined
  }

  const pageLimit = toNumber(params?.limit)
  if (pageLimit && pageLimit > 0 && users.length > pageLimit) {
    users = users.slice(0, pageLimit)
  }

  return {
    ...oldData,
    users,
    total,
  }
}

export const upsertUserInUsersCache = (queryClient: QueryClient, user: UserResponse, options?: { allowInsert?: boolean }) => {
  const allowInsert = options?.allowInsert ?? false
  const cachedQueries = queryClient.getQueriesData<UsersResponse>({
    queryKey: [USERS_QUERY_KEY],
    exact: false,
  })

  cachedQueries.forEach(([queryKey, oldData]) => {
    if (!oldData) return
    const params = readUsersParamsFromKey(queryKey)
    const updatedData = upsertInSingleUsersQuery(oldData, user, params, allowInsert)
    if (updatedData) {
      queryClient.setQueryData(queryKey, updatedData)
    }
  })
}

export const invalidateUserMetricsQueries = (queryClient: QueryClient) => {
  queryClient.invalidateQueries({ queryKey: ['getUsersUsage'] })
  queryClient.invalidateQueries({ queryKey: ['getUserStats'] })
  queryClient.invalidateQueries({ queryKey: ['getInboundStats'] })
  queryClient.invalidateQueries({ queryKey: ['getUserOnlineStats'] })
}
