export const HAPP_ROUTING_LINK_PREFIX = 'happ://routing/onadd/'

// Large headers can be cut by reverse proxies; above this the editor suggests body placement.
export const HAPP_ROUTING_LINK_WARN_BYTES = 4096

const bytesToBase64 = (bytes: Uint8Array): string => {
  let binary = ''
  bytes.forEach(byte => {
    binary += String.fromCharCode(byte)
  })
  return btoa(binary)
}

/**
 * Builds the link the panel sends with the subscription: standard Base64 of compact UTF-8 JSON,
 * same as the backend. Returns null when the content is not a JSON object.
 */
export const buildHappRoutingLink = (content: string): string | null => {
  let parsed: unknown
  try {
    parsed = JSON.parse(content)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null
  }
  return HAPP_ROUTING_LINK_PREFIX + bytesToBase64(new TextEncoder().encode(JSON.stringify(parsed)))
}
