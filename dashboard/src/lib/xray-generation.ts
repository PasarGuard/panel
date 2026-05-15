/**
 * Single import path for Xray template generators used by core-config UI and the core editor.
 * All logic lives in `@pasarguard/xray-config-kit`.
 */
import {
  createDefaultVlessOptions,
  VLESS_ENCRYPTION_METHODS,
} from '@pasarguard/xray-config-kit'
import type { VlessBuilderOptions } from '@pasarguard/xray-config-kit'
import { encodeURLSafe } from '@stablelib/base64'
import { generateKeyPair } from '@stablelib/x25519'
import { generateMldsa65 as kitGenerateMldsa65 } from '@/utils/mldsa65'

export {
  createDefaultVlessOptions,
  createWireGuardCoreConfigJson,
  DEFAULT_VLESS_ENCRYPTION,
  DEFAULT_VLESS_HANDSHAKE,
  DEFAULT_VLESS_PADDING,
  DEFAULT_VLESS_RESUME,
  DEFAULT_VLESS_SERVER_TICKET,
  generateShadowsocksPassword,
  generateVlessEncryption,
  generateVLESSEncryption,
  SHADOWSOCKS_ENCRYPTION_METHODS,
  VLESS_ENCRYPTION_METHODS,
  VLESS_HANDSHAKE_OPTIONS,
  VLESS_RESUME_OPTIONS,
} from '@pasarguard/xray-config-kit'

export type { ShadowsocksPasswordResult, VlessEncryptionResult, VlessBuilderOptions } from '@pasarguard/xray-config-kit'

export type VlessEncryptionMethodSelect = 'none' | (typeof VLESS_ENCRYPTION_METHODS)[number]['value']

/** Parses the second segment of a vision `encryption` / `decryption` string, or a legacy single-token value. */
export function parseVlessEncryptionMethodTokenFromString(raw: string): VlessEncryptionMethodSelect | null {
  const trimmed = raw.trim()
  if (!trimmed || trimmed === 'none') return 'none'
  if (!trimmed.includes('.')) {
    return VLESS_ENCRYPTION_METHODS.some(m => m.value === trimmed) ? (trimmed as VlessEncryptionMethodSelect) : null
  }
  const seg = trimmed.split('.')[1]?.trim() ?? ''
  return VLESS_ENCRYPTION_METHODS.some(m => m.value === seg) ? (seg as VlessEncryptionMethodSelect) : null
}

/** Raw `encryption` string for the inbound form (empty when vision encryption is off). */
export function vlessInboundEncryptionRawForForm(row: { protocol: string; encryption?: string }): string {
  if (row.protocol !== 'vless') return ''
  const e = row.encryption
  if (e === undefined || e === '' || e === 'none') return ''
  return e
}

export function vlessInboundEncryptionMethodForForm(row: { protocol: string; encryption?: string }): VlessEncryptionMethodSelect {
  const raw = vlessInboundEncryptionRawForForm(row)
  return parseVlessEncryptionMethodTokenFromString(raw) ?? 'none'
}

/** Seeds the advanced builder from the inbound "encryption method" select (not the full encryption string). */
export function buildVlessGenerationOptionsFromInboundForm(methodSelect: string): VlessBuilderOptions {
  const base = createDefaultVlessOptions()
  const trimmed = methodSelect?.trim() ?? ''
  if (trimmed !== '' && trimmed !== 'none' && VLESS_ENCRYPTION_METHODS.some(m => m.value === trimmed)) {
    return { ...base, encryptionMethod: trimmed }
  }
  return base
}

// Reality Generators

export interface RealityKeyPair {
  publicKey: string
  privateKey: string
}

export function generateRealityKeyPair(): RealityKeyPair {
  const keyPair = generateKeyPair()
  return {
    privateKey: encodeURLSafe(keyPair.secretKey).replace(/=/g, '').replace(/\n/g, ''),
    publicKey: encodeURLSafe(keyPair.publicKey).replace(/=/g, '').replace(/\n/g, ''),
  }
}

export function generateRealityShortId(): string {
  const randomBytes = new Uint8Array(8)
  crypto.getRandomValues(randomBytes)
  return Array.from(randomBytes)
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('')
}

// ML-DSA-65 Generator

export interface Mldsa65Result {
  seed: string
  verify: string
}

export async function generateMldsa65Keys(): Promise<Mldsa65Result> {
  return await kitGenerateMldsa65()
}
