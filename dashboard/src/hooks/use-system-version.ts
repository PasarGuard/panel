import { useGetSystemStats } from '@/service/api'

const SYSTEM_VERSION_STALE_TIME = 5 * 60 * 1000

export function useSystemVersion() {
  const { data, isLoading, isError } = useGetSystemStats(undefined, {
    query: {
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
    currentVersion: data ?? null,
    isLoading,
    isError,
  }
}
