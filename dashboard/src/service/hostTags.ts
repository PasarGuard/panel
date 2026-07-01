import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { UseMutationOptions, UseQueryOptions } from '@tanstack/react-query'

import { fetcher } from './http'
import type { HostTag, HostTagCreate, HostTagModify } from './api'

export const hostTagsQueryKey = ['host', 'tags'] as const

const invalidateHostAndTagQueries = (queryClient: ReturnType<typeof useQueryClient>) =>
  queryClient.invalidateQueries({
    predicate: query =>
      query.queryKey.some(part => typeof part === 'string' && part.toLowerCase().includes('host')),
  })

export const getHostTags = () => fetcher<HostTag[]>('/api/host/tags', { method: 'GET' })

export const createHostTag = (data: HostTagCreate) => fetcher<HostTag>('/api/host/tags', { method: 'POST', body: data })

export const modifyHostTag = (tagId: number, data: HostTagModify) =>
  fetcher<HostTag>(`/api/host/tags/${tagId}`, { method: 'PUT', body: data })

export const removeHostTag = (tagId: number) => fetcher<void>(`/api/host/tags/${tagId}`, { method: 'DELETE' })

export const useHostTags = (options?: Partial<UseQueryOptions<HostTag[]>>) =>
  useQuery({ queryKey: hostTagsQueryKey, queryFn: getHostTags, ...options })

export const useCreateHostTag = (options?: UseMutationOptions<HostTag, unknown, HostTagCreate>) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createHostTag,
    ...options,
    onSuccess: (...args) => {
      void invalidateHostAndTagQueries(queryClient)
      options?.onSuccess?.(...args)
    },
  })
}

export const useModifyHostTag = (
  options?: UseMutationOptions<HostTag, unknown, { tagId: number; data: HostTagModify }>,
) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ tagId, data }: { tagId: number; data: HostTagModify }) => modifyHostTag(tagId, data),
    ...options,
    onSuccess: (...args) => {
      void invalidateHostAndTagQueries(queryClient)
      options?.onSuccess?.(...args)
    },
  })
}

export const useRemoveHostTag = (options?: UseMutationOptions<void, unknown, number>) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: removeHostTag,
    ...options,
    onSuccess: (...args) => {
      void invalidateHostAndTagQueries(queryClient)
      options?.onSuccess?.(...args)
    },
  })
}
