const MLDSA65_SEED_LENGTH = 32
const BASE64_CHUNK_SIZE = 0x8000

type MlDsaImplementation = (typeof import('@noble/post-quantum/ml-dsa.js'))['ml_dsa65']

let mlDsa65Promise: Promise<MlDsaImplementation> | null = null

const base64UrlEncode = (bytes: Uint8Array) => {
  if (typeof window === 'undefined') {
    throw new Error('ML-DSA-65 generation is only supported in the browser runtime')
  }
  let binary = ''
  const length = bytes.length
  for (let i = 0; i < length; i += BASE64_CHUNK_SIZE) {
    const chunk = bytes.subarray(i, i + BASE64_CHUNK_SIZE)
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

const base64UrlDecode = (value: string): Uint8Array => {
  if (typeof window === 'undefined') {
    throw new Error('ML-DSA-65 generation is only supported in the browser runtime')
  }
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const padLength = normalized.length % 4
  const padded = padLength === 0 ? normalized : normalized + '='.repeat(4 - padLength)
  const binaryString = atob(padded)
  const bytes = new Uint8Array(binaryString.length)
  for (let i = 0; i < binaryString.length; i += 1) {
    bytes[i] = binaryString.charCodeAt(i)
  }
  return bytes
}

const loadMlDsa65 = async (): Promise<MlDsaImplementation> => {
  if (!mlDsa65Promise) {
    mlDsa65Promise = import('@noble/post-quantum/ml-dsa.js').then(mod => mod.ml_dsa65)
  }

  return mlDsa65Promise
}

const ensureSeed = (seed?: string): { bytes: Uint8Array; encoded: string } => {
  if (seed) {
    const decoded = base64UrlDecode(seed)
    if (decoded.length !== MLDSA65_SEED_LENGTH) {
      throw new Error(`Seed must be ${MLDSA65_SEED_LENGTH} bytes`)
    }
    return { bytes: decoded, encoded: seed }
  }

  const generated = new Uint8Array(MLDSA65_SEED_LENGTH)
  crypto.getRandomValues(generated)
  return { bytes: generated, encoded: base64UrlEncode(generated) }
}

export const generateMldsa65 = async (seed?: string): Promise<{ seed: string; verify: string }> => {
  if (typeof window === 'undefined') {
    throw new Error('ML-DSA-65 generation requires a browser environment')
  }

  const implementation = await loadMlDsa65()
  const { bytes: seedBytes, encoded } = ensureSeed(seed)

  const { publicKey } = implementation.keygen(seedBytes)

  return {
    seed: encoded,
    verify: base64UrlEncode(publicKey),
  }
}
