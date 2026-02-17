import { useGetSystemStats } from '@/service/api'

const SYSTEM_VERSION_STALE_TIME = 5 * 60 * 1000

interface UseSystemVersionOptions {
  enabled?: boolean
}

export function useSystemVersion(options: UseSystemVersionOptions = {}) {
  const enabled = options.enabled ?? true
  const { data, isLoading, isError } = useGetSystemStats(undefined, {
    query: {
      enabled,
      select: stats => stats?.version ?? null,
      staleTime: SYSTEM_VERSION_STALE_TIME,
      gcTime: SYSTEM_VERSION_STALE_TIME * 2,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      retry: 1,
    },
  })

  return {
    currentVersion: enabled ? (data ?? null) : null,
    isLoading: enabled ? isLoading : false,
    isError: enabled ? isError : false,
  }
}
