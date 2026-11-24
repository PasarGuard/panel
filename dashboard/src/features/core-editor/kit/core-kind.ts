import type { CoreKind } from '@pasarguard/core-kit'
import type { CoreResponse } from '@/service/api'

export function apiCoreTypeToKind(type: CoreResponse['type'] | undefined): CoreKind {
  if (type === 'wg') return 'wg'
  return 'xray'
}

export function isSupportedCoreEditorKind(type: CoreResponse['type'] | undefined): boolean {
  return type === 'wg' || type === 'xray' || type == null || type === undefined
}

/** Gates Xray-only UI (api services, fallbacks, excluded inbounds, core and geofile updates); a missing type means Xray. */
export function isXrayCoreType(type: CoreResponse['type'] | null | undefined): boolean {
  return type === 'xray' || type == null
}

/** The core name a new-core type switch carries in the router location state. */
export function carriedCoreName(state: unknown): string {
  const name = state !== null && typeof state === 'object' ? (state as { coreName?: unknown }).coreName : undefined
  return typeof name === 'string' ? name : ''
}
