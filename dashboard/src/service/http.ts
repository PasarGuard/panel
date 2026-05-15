import { handleUnauthorized } from '@/utils/authSession'
import { getAuthToken } from '@/utils/authStorage'
import { dateUtils } from '@/utils/dateFormatter'
import { FetchError, FetchOptions, $fetch as ofetch } from 'ofetch'

export const $fetch = ofetch.create({
  baseURL: import.meta.env.VITE_BASE_API,
  onRequest({ options }) {
    const token = getAuthToken()
    options.headers.set('X-Client-Timezone', dateUtils.getSystemTimeZone())
    options.headers.set('X-Client-Timezone-Offset-Minutes', String(-new Date().getTimezoneOffset()))
    if (token) {
      options.headers.set('Authorization', `Bearer ${token}`)
    }
  },
})

export const fetcher = <T>(url: string, ops: FetchOptions<'json'> = {}) => {
  return $fetch<T>(url, ops).catch(async e => {
    if (e.status === 401) {
      await handleUnauthorized()
    }
    throw e
  })
}

export const fetch = fetcher

export type ErrorType<Error> = FetchError<{ detail: Error }>
export type BodyType<BodyData> = BodyData

type OrvalFetchMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
type OrvalRequestBody = RequestInit['body']

type OrvalFetchOptions = Omit<FetchOptions<'json'>, 'body' | 'headers' | 'method' | 'params'> & {
  method: OrvalFetchMethod
  body?: OrvalRequestBody
  headers?: HeadersInit
  params?: Record<string, unknown>
  data?: OrvalRequestBody
}

const isPlainObject = (value: unknown): value is Record<string, unknown> => {
  return Object.prototype.toString.call(value) === '[object Object]'
}

const hasReactQueryOptions = (value: unknown): value is { staleTime?: unknown; gcTime?: unknown; retry?: unknown } => {
  if (!value || typeof value !== 'object') {
    return false
  }

  return 'staleTime' in value || 'gcTime' in value || 'retry' in value
}

export async function orvalFetcher<T>(url: string, options: OrvalFetchOptions): Promise<T> {
  const { method, params, data, body: requestBody, ...fetchOptions } = options

  let requestParams = params
  let body = data ?? requestBody

  if (method === 'GET') {
    // 1. If we have data in a GET request, it means arguments were shifted or
    // we manually passed data to rescue dropped parameters.
    if (body) {
      if (isPlainObject(body)) {
        const bodyParams: Record<string, unknown> = body
        requestParams = { ...(requestParams ?? {}), ...bodyParams }
      } else if (Array.isArray(body)) {
        // Specifically for cases like Admin list where the 'body' is actually a sort array
        requestParams = { ...requestParams, sort: body.join(',') }
      }
      body = undefined
    }

    // 2. If 'query' is present in params, check if it looks like React Query options.
    if (requestParams && 'query' in requestParams) {
      const queryVal = requestParams.query
      if (hasReactQueryOptions(queryVal)) {
        const nextParams: Record<string, unknown> = { ...requestParams }
        delete nextParams.query
        requestParams = nextParams
      }
    }
  }

  return fetcher(url, {
    ...fetchOptions,
    method,
    params: requestParams,
    body,
  })
}

export default orvalFetcher
