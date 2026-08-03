const MLDSA65_SEED_LENGTH = 32
/** FIPS 204 ML-DSA-65 public key size in bytes. */
const MLDSA65_VERIFY_LENGTH = 1952
const BASE64_CHUNK_SIZE = 0x8000

type MlDsaImplementation = (typeof import('@noble/post-quantum/ml-dsa.js'))['ml_dsa65']

let mlDsa65Promise: Promise<MlDsaImplementation> | null = null

export { MLDSA65_SEED_LENGTH, MLDSA65_VERIFY_LENGTH }

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

/** Decode a URL-safe Base64 (no padding) value; returns null if encoding is invalid. */
export const decodeMldsa65Base64Url = (value: string): Uint8Array | null => {
  const trimmed = value.trim()
  if (!trimmed || !/^[A-Za-z0-9_-]+$/.test(trimmed)) return null
  try {
    return base64UrlDecode(trimmed)
  } catch {
    return null
  }
}

export type Mldsa65FieldValidation =
  | { ok: true }
  | { ok: false; reason: 'empty' | 'encoding' | 'length' }

export const validateMldsa65Seed = (seed: string): Mldsa65FieldValidation => {
  const trimmed = seed.trim()
  if (!trimmed) return { ok: false, reason: 'empty' }
  const decoded = decodeMldsa65Base64Url(trimmed)
  if (!decoded) return { ok: false, reason: 'encoding' }
  if (decoded.length !== MLDSA65_SEED_LENGTH) return { ok: false, reason: 'length' }
  return { ok: true }
}

export const validateMldsa65Verify = (verify: string): Mldsa65FieldValidation => {
  const trimmed = verify.trim()
  if (!trimmed) return { ok: false, reason: 'empty' }
  const decoded = decodeMldsa65Base64Url(trimmed)
  if (!decoded) return { ok: false, reason: 'encoding' }
  if (decoded.length !== MLDSA65_VERIFY_LENGTH) return { ok: false, reason: 'length' }
  return { ok: true }
}

/** True when verify is the public key derived from seed. */
export const mldsa65PairMatches = async (seed: string, verify: string): Promise<boolean> => {
  const seedCheck = validateMldsa65Seed(seed)
  const verifyCheck = validateMldsa65Verify(verify)
  if (!seedCheck.ok || !verifyCheck.ok) return false

  const derived = await generateMldsa65(seed.trim())
  return derived.verify === verify.trim()
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
