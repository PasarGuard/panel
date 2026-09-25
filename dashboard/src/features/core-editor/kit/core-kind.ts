import type { CoreKind } from '@pasarguard/core-kit'
import type { CoreResponse } from '@/service/api'

export function apiCoreTypeToKind(type: CoreResponse['type'] | undefined): CoreKind {
  if (type === 'wg') return 'wg'
  return 'xray'
}

export function isSupportedCoreEditorKind(type: CoreResponse['type'] | undefined): boolean {
  return type === 'wg' || type === 'xray' || type == null || type === undefined
}
