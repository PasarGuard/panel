export type SubscriptionContentFormat = 'links' | 'links_base64' | 'wireguard'

const WIREGUARD_PROTOCOL = 'wireguard://'
const TEXT_FILE_MIME_TYPE = 'text/plain;charset=utf-8'

const safeDecodeURIComponent = (value: string) => {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

const normalizeSubscriptionPath = (value: string) => value.replace(/\/+$/, '')

const formatCommaSeparatedValue = (value: string) =>
  value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
    .join(', ')

const sanitizeFileNameSegment = (value: string | null | undefined) => {
  if (!value) return ''

  return safeDecodeURIComponent(value)
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^\.+|\.+$/g, '')
    .trim()
}

const getWireGuardEndpointHost = (hostname: string) => {
  if (hostname.includes(':') && !hostname.startsWith('[')) {
    return `[${hostname}]`
  }

  return hostname
}

type ParsedWireGuardUri = {
  address: string
  allowedIps: string
  endpoint: string
  hostname: string
  mtu: string
  port: string
  preSharedKey: string
  privateKey: string
  publicKey: string
  remark: string
  reserved: string
  source: string
  keepalive: string
}

const parseWireGuardUri = (value: string): ParsedWireGuardUri | null => {
  if (!isWireGuardConfigUrl(value)) {
    return null
  }

  try {
    const source = value.trim()
    const parsed = new URL(source)
    const hostname = parsed.hostname
    const port = parsed.port
    const endpointHost = getWireGuardEndpointHost(hostname)

    return {
      address: parsed.searchParams.get('address') || '',
      allowedIps: parsed.searchParams.get('allowedips') || '',
      endpoint: port ? `${endpointHost}:${port}` : endpointHost,
      hostname,
      mtu: parsed.searchParams.get('mtu') || '',
      port,
      preSharedKey: parsed.searchParams.get('presharedkey') || '',
      privateKey: safeDecodeURIComponent(parsed.username),
      publicKey: parsed.searchParams.get('publickey') || '',
      remark: safeDecodeURIComponent(parsed.hash.replace(/^#/, '')),
      reserved: parsed.searchParams.get('reserved') || '',
      source,
      keepalive: parsed.searchParams.get('keepalive') || '',
    }
  } catch {
    return null
  }
}

export const resolveSubscriptionQrUrl = (subscribeUrl: string | null | undefined) => {
  if (!subscribeUrl) return ''

  const value = String(subscribeUrl)
  return value.startsWith('/') ? `${window.location.origin}${value}` : value
}

export const resolveSubscriptionPublicUrl = (subscribeUrl: string | null | undefined) => resolveSubscriptionQrUrl(subscribeUrl)

export const resolveSubscriptionPanelBaseUrl = (subscribeUrl: string | null | undefined) => {
  if (!subscribeUrl) return ''

  const value = String(subscribeUrl)

  if (value.startsWith('/')) {
    return normalizeSubscriptionPath(`${window.location.origin}${value}`)
  }

  try {
    const parsed = new URL(value, window.location.origin)
    return normalizeSubscriptionPath(`${window.location.origin}${parsed.pathname}${parsed.search}${parsed.hash}`)
  } catch {
    return normalizeSubscriptionPath(value)
  }
}

export const resolveSubscriptionFetchBaseUrl = (subscribeUrl: string | null | undefined) => {
  return resolveSubscriptionPanelBaseUrl(subscribeUrl)
}

export const buildSubscriptionFormatUrl = (subscribeUrl: string | null | undefined, format: string) => {
  const baseUrl = resolveSubscriptionPanelBaseUrl(subscribeUrl)
  return baseUrl ? `${baseUrl}/${format}` : ''
}

const fetchSubscriptionResource = async <T>(url: string, parser: (response: Response) => Promise<T>, timeoutMs = 8000) => {
  if (!url) {
    throw new Error('Subscription URL is empty')
  }

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(url, {
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return parser(response)
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export const fetchSubscriptionContentFromUrl = (url: string, timeoutMs = 8000) => fetchSubscriptionResource(url, response => response.text(), timeoutMs)

export const fetchSubscriptionBlobFromUrl = (url: string, timeoutMs = 8000) => fetchSubscriptionResource(url, response => response.blob(), timeoutMs)

export const fetchSubscriptionContent = (subscribeUrl: string, format: SubscriptionContentFormat, timeoutMs = 8000) =>
  fetchSubscriptionContentFromUrl(buildSubscriptionFormatUrl(subscribeUrl, format), timeoutMs)

export const extractNameFromConfigUrl = (url: string): string | null => {
  const trimmedUrl = url.trim()
  const namePattern = /#([^#]*)/
  const match = trimmedUrl.match(namePattern)

  if (match) {
    return safeDecodeURIComponent(match[1])
  }

  if (trimmedUrl.startsWith('vmess://')) {
    const encodedString = trimmedUrl.replace('vmess://', '')

    try {
      const decodedString = atob(encodedString)
      return JSON.parse(decodedString).ps || null
    } catch {
      return null
    }
  }

  return null
}

export const extractAddressFromConfigUrl = (url: string): string | null => {
  const trimmedUrl = url.trim()

  if (trimmedUrl.startsWith('vmess://')) {
    try {
      const encodedString = trimmedUrl.replace('vmess://', '').split('#')[0]
      const decodedString = atob(encodedString)
      const config = JSON.parse(decodedString)
      return config.add || null
    } catch {
      return null
    }
  }

  try {
    const parsed = new URL(trimmedUrl)
    return parsed.hostname || null
  } catch {
    const protocolPattern = /^[a-z]+:\/\/([^@]+@)?([^:/?#]+)/i
    const match = trimmedUrl.match(protocolPattern)
    return match?.[2] || null
  }
}

export const isWireGuardConfigUrl = (value: string) => value.trim().toLowerCase().startsWith(WIREGUARD_PROTOCOL)

export const convertWireGuardUrlToConfig = (value: string) => {
  const parsed = parseWireGuardUri(value)

  if (!parsed || !parsed.privateKey || !parsed.publicKey || !parsed.address || !parsed.endpoint) {
    return null
  }

  const lines: string[] = []

  if (parsed.remark) {
    lines.push(`# Name = ${parsed.remark}`)
  }

  lines.push('[Interface]')
  lines.push(`PrivateKey = ${parsed.privateKey}`)
  lines.push(`Address = ${formatCommaSeparatedValue(parsed.address)}`)

  if (parsed.mtu) {
    lines.push(`MTU = ${parsed.mtu}`)
  }

  if (parsed.reserved) {
    lines.push(`Reserved = ${parsed.reserved}`)
  }

  lines.push('')
  lines.push('[Peer]')
  lines.push(`PublicKey = ${parsed.publicKey}`)

  if (parsed.preSharedKey) {
    lines.push(`PresharedKey = ${parsed.preSharedKey}`)
  }

  if (parsed.allowedIps) {
    lines.push(`AllowedIPs = ${formatCommaSeparatedValue(parsed.allowedIps)}`)
  }

  lines.push(`Endpoint = ${parsed.endpoint}`)

  if (parsed.keepalive) {
    lines.push(`PersistentKeepalive = ${parsed.keepalive}`)
  }

  lines.push('')
  lines.push(`# URI: ${parsed.source}`)

  return lines.join('\n')
}

export const buildWireGuardDownloadFileName = (value: string) => {
  const parsed = parseWireGuardUri(value)

  if (!parsed) {
    return 'wireguard.conf'
  }

  const fileNameParts = [
    sanitizeFileNameSegment(parsed.remark),
  ].filter(Boolean)

  const fallbackPart =
    sanitizeFileNameSegment(formatCommaSeparatedValue(parsed.address).replace(/[,:/[\]]+/g, '-')) || 'wireguard'

  return `${fileNameParts.join('_') || fallbackPart}.conf`
}

export const getWireGuardDownloadPayload = (value: string) => {
  if (!isWireGuardConfigUrl(value)) {
    return null
  }

  const content = convertWireGuardUrlToConfig(value)
  if (!content) {
    return null
  }

  return {
    content,
    fileName: buildWireGuardDownloadFileName(value),
  }
}

export const encodeSubscriptionContentToBase64 = (content: string) => {
  const bytes = new TextEncoder().encode(content)
  const chunkSize = 0x8000
  let binary = ''

  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize))
  }

  return btoa(binary)
}

export const prepareSubscriptionContentForCopy = (content: string) => {
  const configLines = content
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)

  if (configLines.length === 0 || !configLines.every(isWireGuardConfigUrl)) {
    return {
      content,
      downloadFileName: null,
      isWireGuard: false,
    }
  }

  const convertedConfigs = configLines
    .map(convertWireGuardUrlToConfig)
    .filter((value): value is string => Boolean(value))

  if (convertedConfigs.length !== configLines.length) {
    return {
      content,
      downloadFileName: null,
      isWireGuard: false,
    }
  }

  return {
    content: convertedConfigs.join('\n\n'),
    downloadFileName: configLines.length === 1 ? buildWireGuardDownloadFileName(configLines[0]) : 'wireguard.conf',
    isWireGuard: true,
  }
}

export const downloadTextFile = (content: string, fileName: string, mimeType = TEXT_FILE_MIME_TYPE) => {
  const blob = new Blob([content], { type: mimeType })
  const downloadUrl = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')

  anchor.href = downloadUrl
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.URL.revokeObjectURL(downloadUrl)
}
