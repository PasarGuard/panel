import { v4 as uuid } from 'uuid'

export interface TlsCertificateItem {
  id: string
  raw: Record<string, unknown>
  mode: 'path' | 'content'
  certificateFile: string
  keyFile: string
  certificate: string
  key: string
  ocspStapling: string
  serveOnNode: boolean
}

const text = (value: unknown) => (Array.isArray(value) ? value.map(String).join('\n') : typeof value === 'string' ? value : '')

export function certificateItems(value: unknown): TlsCertificateItem[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((raw): raw is Record<string, unknown> => Boolean(raw) && typeof raw === 'object' && !Array.isArray(raw))
    .map(raw => ({
      id: uuid(),
      raw,
      mode: 'certificate' in raw || 'key' in raw ? 'content' : 'path',
      certificateFile: text(raw.certificateFile),
      keyFile: text(raw.keyFile),
      certificate: text(raw.certificate),
      key: text(raw.key),
      ocspStapling: raw.ocspStapling == null ? '' : String(raw.ocspStapling),
      serveOnNode: raw.serveOnNode === true,
    }))
}

export function newCertificateItem(): TlsCertificateItem {
  return certificateItems([{}])[0]
}

export function serializeCertificates(items: TlsCertificateItem[]): Record<string, unknown>[] {
  return items.map(item => {
    // Preserve Xray extension fields such as usage, oneTimeLoading and buildChain.
    const raw = { ...item.raw }
    for (const name of ['certificateFile', 'keyFile', 'certificate', 'key', 'ocspStapling', 'serveOnNode']) delete raw[name]
    raw.serveOnNode = item.serveOnNode
    if (item.mode === 'path') {
      raw.certificateFile = item.certificateFile.trim()
      raw.keyFile = item.keyFile.trim()
    } else {
      const lines = (value: string) =>
        value
          .split(/\r?\n/)
          .map(line => line.trim())
          .filter(Boolean)
      raw.certificate = lines(item.certificate)
      raw.key = lines(item.key)
    }
    if (item.ocspStapling.trim() !== '') raw.ocspStapling = Number(item.ocspStapling)
    return raw
  })
}
