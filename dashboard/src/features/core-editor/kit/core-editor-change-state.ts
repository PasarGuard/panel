import type { CoreEditorStoreState } from '@/features/core-editor/state/core-editor-store'
import { profileToPersistedConfig } from '@/features/core-editor/kit/xray-adapter'
import { draftToPersistedConfig } from '@/features/core-editor/kit/wireguard-adapter'

function stableStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return ''
  }
}

function safeConfigString(label: string, factory: () => unknown): string {
  try {
    return stableStringify(factory())
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return `__invalid_${label}__:${message}`
  }
}

function sameStringArray(a: string[], b: string[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function currentConfigString(s: CoreEditorStoreState): string {
  if (s.monacoDirty) {
    try {
      return stableStringify(JSON.parse(s.monacoJson))
    } catch {
      return `__invalid_monaco_json__:${s.monacoJson}`
    }
  }
  if (s.kind === 'wg' && s.wgDraft) {
    const draft = s.wgDraft
    return safeConfigString('wg_current_config', () => draftToPersistedConfig(draft))
  }
  if (s.kind === 'xray' && s.xrayProfile) {
    const profile = s.xrayProfile
    return safeConfigString('xray_current_config', () => profileToPersistedConfig(profile))
  }
  return ''
}

function baselineConfigString(s: CoreEditorStoreState): string {
  if (s.kind === 'wg' && s.wgBaseline) {
    const draft = s.wgBaseline
    return safeConfigString('wg_baseline_config', () => draftToPersistedConfig(draft))
  }
  if (s.kind === 'xray' && s.xrayBaseline) {
    const profile = s.xrayBaseline
    return safeConfigString('xray_baseline_config', () => profileToPersistedConfig(profile))
  }
  return ''
}

export function selectCoreEditorHasActualChanges(s: CoreEditorStoreState): boolean {
  if (!s.hydrated) return false

  const snap = s.persistedSnapshot
  if (!snap) return s.dirty
  if (s.kind !== snap.kind) return true
  if (s.coreName.trim() !== snap.coreName.trim()) return true
  if (!sameStringArray(s.fallbacksInboundTags, snap.fallbacksInboundTags)) return true
  if (!sameStringArray(s.excludeInboundTags, snap.excludeInboundTags)) return true

  return currentConfigString(s) !== baselineConfigString(s)
}
