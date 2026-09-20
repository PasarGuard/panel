const STORAGE_KEY = 'mcp-oauth-request'

const AUTHORIZE_PATH = '/mcp/authorize'

export const savePendingOAuthRequest = (request: string) => {
  try {
    sessionStorage.setItem(STORAGE_KEY, request)
  } catch {
    return
  }
}

const consumePendingOAuthRequest = (): string | null => {
  try {
    const request = sessionStorage.getItem(STORAGE_KEY)
    sessionStorage.removeItem(STORAGE_KEY)
    return request
  } catch {
    return null
  }
}

export const postLoginPath = (): string => {
  const request = consumePendingOAuthRequest()
  return request ? `${AUTHORIZE_PATH}?request=${encodeURIComponent(request)}` : '/'
}
