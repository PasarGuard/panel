import { getAuthToken } from '@/utils/authStorage'
import { dateUtils } from '@/utils/dateFormatter'
import { isUnauthorizedError } from '@/utils/error-utils'
import { FetchError, FetchOptions, $fetch as ofetch } from 'ofetch'

export const $fetch = ofetch.create({
  baseURL: import.meta.env.VITE_BASE_API,
  onRequest({ options }) {
    const token = getAuthToken()
    options.headers.set('X-Client-Timezone', dateUtils.getSystemTimeZone())
    options.headers.set('X-Client-Timezone-Offset-Minutes', String(-new Date().getTimezoneOffset()))
    if (token) {
      options.headers.set('Authorization', `Bearer ${getAuthToken()}`)
    }
  },
})

export const fetcher = <T>(url: string, ops: FetchOptions<'json'> = {}) => {
  return $fetch<T>(url, ops).catch(e => {
    if (isUnauthorizedError(e)) {
      const url = new URL(window.location.href)
      if (url.hash !== '#/login') {
        url.hash = '#/login'
        window.location.href = url.href
      }
    }
    throw e
  })
}

export const fetch = fetcher

export type ErrorType<Error> = FetchError<{ detail: Error }>
export type BodyType<BodyData> = BodyData

/**
 * Mutator called by orval v8+ generated code.
 * Orval v8 uses the signature: (url: string, options: RequestInit)
 * Query params are pre-encoded into the URL by the generated getXxxUrl() helpers.
 */
export const orvalFetcher = async <T>(url: string, options: RequestInit = {}): Promise<T> => {
  const { method = 'GET', body, headers, signal } = options

  return fetcher<T>(url, {
    method: method as FetchOptions<'json'>['method'],
    body: body ?? undefined,
    headers: headers as HeadersInit | undefined,
    signal: signal ?? undefined,
  })
}

export default orvalFetcher
