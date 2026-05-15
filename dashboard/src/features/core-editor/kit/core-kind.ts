import type { CoreType } from '@/service/api'
import type { CoreKind } from '@pasarguard/core-kit'

export function apiCoreTypeToKind(type: CoreType | null | undefined): CoreKind {
  if (type === 'wg') return 'wg'
  return 'xray'
}

export function isSupportedCoreEditorKind(type: CoreType | null | undefined): boolean {
  return type === 'wg' || type === 'xray' || type == null || type === undefined
}
