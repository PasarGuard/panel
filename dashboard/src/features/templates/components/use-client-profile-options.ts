import { useAdmin } from '@/hooks/use-admin'
import { getGetClientProfilesQueryKey, getGetClientProfilesSimpleQueryKey, useGetClientProfiles, useGetClientProfilesSimple, type ClientProfileSimple } from '@/service/api'
import { hasPermission } from '@/utils/rbac'
import { queryClient } from '@/utils/query-client'

/** Selecting a profile on a user/user template needs client_profiles read or read_simple (same rule as the backend). */
export const useCanAssignClientProfile = () => {
  const { admin } = useAdmin()
  return hasPermission(admin, 'client_profiles', 'read_simple') || hasPermission(admin, 'client_profiles', 'read')
}

/**
 * Profiles for selects. Uses the simple list when allowed, otherwise the full list (admins with `read` only).
 * Cached by react-query, so opening several dialogs does not refetch.
 */
export const useClientProfileOptions = (enabled = true) => {
  const { admin } = useAdmin()
  const canReadSimple = hasPermission(admin, 'client_profiles', 'read_simple')
  const canRead = hasPermission(admin, 'client_profiles', 'read')
  const queryOptions = { staleTime: 5 * 60 * 1000, gcTime: 10 * 60 * 1000 }

  const simple = useGetClientProfilesSimple({ all: true }, { query: { ...queryOptions, enabled: enabled && canReadSimple } })
  const full = useGetClientProfiles(undefined, { query: { ...queryOptions, enabled: enabled && !canReadSimple && canRead } })

  const profiles: ClientProfileSimple[] = canReadSimple ? (simple.data?.profiles ?? []) : (full.data?.profiles ?? []).map(profile => ({ id: profile.id, name: profile.name }))
  const isLoading = canReadSimple ? simple.isLoading : canRead ? full.isLoading : false
  return { profiles, isLoading }
}

export const invalidateClientProfileQueries = () => {
  queryClient.invalidateQueries({ queryKey: getGetClientProfilesQueryKey() })
  queryClient.invalidateQueries({ queryKey: getGetClientProfilesSimpleQueryKey() })
}

export const getApiErrorDetail = (error: any): string | undefined => {
  const detail = error?.response?._data?.detail ?? error?.response?.data?.detail ?? error?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  return typeof error?.message === 'string' ? error.message : undefined
}
