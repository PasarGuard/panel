import type { JsonValue } from '@pasarguard/wireguard-config-kit'
import {
  createDefaultWireGuardCoreDraft,
  generateWireGuardCoreConfigJsonFromDraft,
  syncWireGuardCoreDraftPublicKey,
  validateWireGuardCoreConfig,
  validateWireGuardCoreDraft,
} from '@pasarguard/wireguard-config-kit'
import type { WireGuardCoreConfig, WireGuardCoreDraft } from '@pasarguard/wireguard-config-kit'
import { validateCoreConfig } from '@pasarguard/core-kit'

const knownConfigKeys = new Set(['interface_name', 'private_key', 'pre_shared_key', 'listen_port', 'address'])

export function wireGuardConfigToDraft(raw: unknown): { ok: true; draft: WireGuardCoreDraft } | { ok: false; message: string } {
  const result = validateWireGuardCoreConfig(raw)
  if (!result.ok) {
    const first = result.issues[0]
    return { ok: false, message: first ? `${first.path}: ${first.message}` : 'Invalid WireGuard config' }
  }
  const c = result.config as WireGuardCoreConfig
  const extra: Record<string, JsonValue> = {}
  for (const [key, value] of Object.entries(c)) {
    if (!knownConfigKeys.has(key)) {
      extra[key] = value as JsonValue
    }
  }
  const draft = syncWireGuardCoreDraftPublicKey({
    interfaceName: c.interface_name,
    privateKey: c.private_key,
    publicKey: '',
    preSharedKey: typeof c.pre_shared_key === 'string' ? c.pre_shared_key : '',
    listenPort: c.listen_port,
    address: [...c.address],
    extra,
  })
  return { ok: true, draft }
}

export function createNewWireGuardDraft(): WireGuardCoreDraft {
  return createDefaultWireGuardCoreDraft()
}

export function draftToPersistedConfig(draft: WireGuardCoreDraft): Record<string, unknown> {
  const json = generateWireGuardCoreConfigJsonFromDraft(draft)
  return JSON.parse(json) as Record<string, unknown>
}

export function validateWireGuardDraftForSave(draft: WireGuardCoreDraft) {
  const issues = validateWireGuardCoreDraft(draft)
  if (issues.length > 0) {
    return { ok: false as const, issues }
  }
  const config = draftToPersistedConfig(draft)
  return validateCoreConfig('wg', config)
}

/** Draft issues + core-kit validation in one step for saves. */
export function getWireGuardPersistConfig(draft: WireGuardCoreDraft) {
  const issues = validateWireGuardCoreDraft(draft)
  if (issues.length > 0) {
    return { ok: false as const, draftIssues: issues }
  }
  const config = draftToPersistedConfig(draft)
  const r = validateCoreConfig('wg', config)
  if (!r.ok) {
    return { ok: false as const, kitIssues: r.issues }
  }
  return { ok: true as const, config: r.config as Record<string, unknown> }
}
