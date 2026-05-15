import { debounce } from 'es-toolkit'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { toast } from 'sonner'
import { useCoreEditorStore } from './core-editor-store'

const APPLY_DEBOUNCE_MS = 420

/** Debounced push from structured draft → Monaco when not dirty from user edits. */
export function useCoreDraftMonacoSync(debounceMs = 200) {
  const monacoJson = useCoreEditorStore(s => s.monacoJson)
  const monacoDirty = useCoreEditorStore(s => s.monacoDirty)
  const syncMonacoFromDraft = useCoreEditorStore(s => s.syncMonacoFromDraft)

  const debouncedSync = useMemo(
    () =>
      debounce(() => {
        if (!useCoreEditorStore.getState().monacoDirty) {
          useCoreEditorStore.getState().syncMonacoFromDraft()
        }
      }, debounceMs),
    [debounceMs],
  )

  const debouncedApplyFromMonaco = useMemo(
    () =>
      debounce(() => {
        const s = useCoreEditorStore.getState()
        if (!s.monacoDirty) return
        const r = s.applyMonacoJson()
        if (r.ok) return
        try {
          JSON.parse(s.monacoJson)
          toast.error(r.error)
        } catch {
          /* incomplete JSON while editing */
        }
      }, APPLY_DEBOUNCE_MS),
    [],
  )

  useEffect(() => {
    if (!monacoDirty) {
      debouncedApplyFromMonaco.cancel()
      return
    }
    debouncedApplyFromMonaco()
    return () => debouncedApplyFromMonaco.cancel()
  }, [monacoJson, monacoDirty, debouncedApplyFromMonaco])

  const prevDraftSig = useRef<string>('')

  useEffect(() => {
    const unsub = useCoreEditorStore.subscribe(s => {
      const sig =
        s.kind === 'wg'
          ? JSON.stringify(s.wgDraft)
          : s.kind === 'xray' && s.xrayProfile
            ? JSON.stringify(s.xrayProfile)
            : ''
      if (sig !== prevDraftSig.current) {
        prevDraftSig.current = sig
        if (!s.monacoDirty) debouncedSync()
      }
    })
    return () => {
      unsub()
      debouncedSync.cancel()
    }
  }, [debouncedSync])

  const forceSync = useCallback(() => {
    useCoreEditorStore.setState({ monacoDirty: false })
    syncMonacoFromDraft()
  }, [syncMonacoFromDraft])

  return { monacoDirty, forceSync }
}
