export interface TelegramProxyLink {
  server: string
  port: string
  secret: string
}

// tg://proxy?... (the panel's form) and https://t.me/proxy?...; scheme and host are case-insensitive
const TELEGRAM_PROXY_LINK_PREFIX = /^(?:tg:\/\/proxy|https:\/\/t\.me\/proxy)\?/i

/** Parse a Telegram MTProto proxy link; null unless it carries a server, a port and a secret. */
export const parseTelegramProxyLink = (url: string): TelegramProxyLink | null => {
  const value = url.trim()
  const prefix = TELEGRAM_PROXY_LINK_PREFIX.exec(value)
  if (!prefix) return null

  const params = new URLSearchParams(value.slice(prefix[0].length).split('#')[0])
  const server = params.get('server')
  const port = params.get('port')
  const secret = params.get('secret')
  if (!server || !port || !secret) return null

  return { server, port, secret }
}
