import type { ValidationListItem } from '@/features/core-editor/components/shared/validation-summary'
import { validateProfileForPersist } from '@/features/core-editor/kit/xray-adapter'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { useMemo } from 'react'

/** Same list as the Xray branch of `preSaveIssues` on the core editor page (strict blockers + core-kit issues). */
export function useXrayPersistValidationItems(): ValidationListItem[] {
  const hydrated = useCoreEditorStore(s => s.hydrated)
  const kind = useCoreEditorStore(s => s.kind)
  const profile = useCoreEditorStore(s => s.xrayProfile)

  return useMemo(() => {
    if (!hydrated || kind !== 'xray' || !profile) return []
    const r = validateProfileForPersist(profile)
    if (r.ok) return []
    const items: ValidationListItem[] = r.strictBlockers.map(issue => ({ source: 'xray' as const, issue }))
    for (const issue of r.coreKitIssues) {
      items.push({ source: 'core-kit' as const, issue })
    }
    return items
  }, [hydrated, kind, profile])
}
