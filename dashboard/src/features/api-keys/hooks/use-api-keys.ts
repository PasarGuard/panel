import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { orvalFetcher } from '@/service/http'

export type APIKeyStatus = 'active' | 'disabled'

export interface APIKeyResponse {
  id: number
  admin_id: number
  name: string
  note: string | null
  role_id: number
  created_at: string
  expire_date: string | null
  revoked_at: string | null
  status: APIKeyStatus
  is_expired: boolean
}

export interface APIKeyCreateResponse extends APIKeyResponse {
  api_key: string
}

export interface APIKeysResponse {
  api_keys: APIKeyResponse[]
  total: number
}

export interface APIKeysQuery {
  offset?: number
  limit?: number
  key_id?: number
  name?: string
  status?: APIKeyStatus
}

export const useListApiKeys = (query?: APIKeysQuery) => {
  return useQuery({
    queryKey: ['api-keys', query],
    queryFn: () =>
      orvalFetcher<APIKeysResponse>({
        url: '/api/api_key/s',
        method: 'GET',
        params: query,
      }),
  })
}

export const useCreateApiKey = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: any) =>
      orvalFetcher<APIKeyCreateResponse>({
        url: '/api/api_key',
        method: 'POST',
        data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })
}

export const useUpdateApiKey = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ keyId, data }: { keyId: number; data: any }) =>
      orvalFetcher<APIKeyResponse>({
        url: `/api/api_key/${keyId}`,
        method: 'PATCH',
        data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })
}

export const useRevokeApiKey = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (keyId: number) =>
      orvalFetcher<APIKeyCreateResponse>({
        url: `/api/api_key/${keyId}/revoke`,
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })
}

export const useDeleteApiKey = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (keyId: number) =>
      orvalFetcher<void>({
        url: `/api/api_key/${keyId}`,
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })
}
