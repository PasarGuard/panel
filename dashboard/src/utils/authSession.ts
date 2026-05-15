import { removeAuthToken } from '@/utils/authStorage'
import { queryClient } from '@/utils/query-client'

let clearAuthSessionPromise: Promise<void> | null = null

export const clearAuthSession = () => {
  if (!clearAuthSessionPromise) {
    clearAuthSessionPromise = (async () => {
      await queryClient.cancelQueries()
      removeAuthToken()
      queryClient.clear()
    })().finally(() => {
      clearAuthSessionPromise = null
    })
  }

  return clearAuthSessionPromise
}

export const redirectToLogin = () => {
  if (typeof window === 'undefined') {
    return
  }

  if (window.location.hash !== '#/login') {
    window.location.hash = '#/login'
  }
}

export const handleUnauthorized = async () => {
  await clearAuthSession()
  redirectToLogin()
}
