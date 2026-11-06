export interface TelegramProxyLink {
  kind: 'proxy' | 'webproxy'
  server: string
  port: string
  secret: string
}

// tg://proxy?... (the panel's form) and https://t.me/proxy?...; scheme and host are case-insensitive
const TELEGRAM_PROXY_LINK_PREFIX = /^(?:tg:\/\/proxy|https:\/\/t\.me\/proxy)\?/i
// tg://webproxy?server=...&secret=... has no port: the WEB transport always uses 443
const TELEGRAM_WEBPROXY_LINK_PREFIX = /^tg:\/\/webproxy\?/i

/** Parse a Telegram MTProto proxy link; null unless it carries a server, a secret and (for tg://proxy) a port. */
export const parseTelegramProxyLink = (url: string): TelegramProxyLink | null => {
  const value = url.trim()
  const webPrefix = TELEGRAM_WEBPROXY_LINK_PREFIX.exec(value)
  const prefix = webPrefix ?? TELEGRAM_PROXY_LINK_PREFIX.exec(value)
  if (!prefix) return null

  const params = new URLSearchParams(value.slice(prefix[0].length).split('#')[0])
  const server = params.get('server')
  const port = webPrefix ? '443' : params.get('port')
  const secret = params.get('secret')
  if (!server || !port || !secret) return null

  return { kind: webPrefix ? 'webproxy' : 'proxy', server, port, secret }
}
