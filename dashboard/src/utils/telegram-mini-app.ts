import { retrieveRawInitData } from '@telegram-apps/sdk'

let initDataFromLaunchHash = ''

/**
 * Telegram puts Mini App launch parameters in the URL fragment. Capture the
 * signed init data before the hash router interprets that fragment as a route,
 * then point the router at the login page that performs the token exchange.
 */
export function prepareTelegramMiniAppRoute() {
  if (typeof window === 'undefined') return

  const launchParams = new URLSearchParams(window.location.hash.replace(/^#\??/, ''))
  const initData = launchParams.get('tgWebAppData')
  if (!initData) return

  initDataFromLaunchHash = initData
  const { pathname, search } = window.location
  window.history.replaceState(window.history.state, '', `${pathname}${search}#/login`)
}

export function getTelegramMiniAppInitData() {
  if (initDataFromLaunchHash) return initDataFromLaunchHash

  try {
    return retrieveRawInitData() || ''
  } catch {
    return ''
  }
}
