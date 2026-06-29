import type { CoreKind } from '@pasarguard/core-kit'
import type { CoreResponseType } from '@/service/api'

export function apiCoreTypeToKind(type: CoreResponseType | undefined): CoreKind {
  if (type === 'wg') return 'wg'
  return 'xray'
}

export function isSupportedCoreEditorKind(type: CoreResponseType | undefined): boolean {
  return type === 'wg' || type === 'xray' || type == null || type === undefined
}
