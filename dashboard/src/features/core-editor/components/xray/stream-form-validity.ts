import type { StreamFormT } from '@/features/core-editor/components/xray/stream-form-inputs'
import { blockingStreamFieldIssues, type StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

/** `onValidityChange` for inputs whose text always parses (trimmed text, a password written as typed). */
export const ignoreValidity = (): void => {}

/** Blocking messages listed in the Add/Modify toast. */
const COMMIT_BLOCK_MESSAGES = 6

/**
 * Why the inbound or outbound dialog cannot Add/Modify yet, or `null`: a MASQUE / XDrive input holds text that does
 * not parse (`issues` is then not run), or the kit reports an error those forms own (`blockingStreamFieldIssues`).
 */
export function streamFormsCommitBlock(t: StreamFormT, hasInvalidInputs: boolean, issues: () => readonly StreamFieldIssue[]): { title: string; description?: string } | null {
  if (hasInvalidInputs) return { title: t('coreEditor.streamForms.invalidInputs', { defaultValue: 'Some fields have values that cannot be saved. Fix the ones marked in red.' }) }
  const blockers = blockingStreamFieldIssues(issues())
  if (blockers.length === 0) return null
  return {
    title: t('coreEditor.streamForms.blockingTitle', { defaultValue: 'Fix these MASQUE or XDrive settings first' }),
    description: blockers
      .slice(0, COMMIT_BLOCK_MESSAGES)
      .map(issue => issue.message)
      .join('\n'),
  }
}

/** The Add/Modify guard both dialogs share: `true` when `streamFormsCommitBlock` finds nothing, else an error toast and `false`. */
export function guardStreamFormsCommit(t: StreamFormT, hasInvalidInputs: boolean, issues: () => readonly StreamFieldIssue[]): boolean {
  const block = streamFormsCommitBlock(t, hasInvalidInputs, issues)
  if (!block) return true
  toast.error(block.title, block.description === undefined ? undefined : { description: block.description })
  return false
}

/**
 * Collects which inputs hold text that does not parse. The returned `report(field, invalid)` is stable; the sorted
 * names of the invalid fields go to the latest `onInvalidInputsChange` whenever that set changes, and `[]` on unmount.
 */
export function useInvalidFieldsReporter(onInvalidInputsChange: (fields: readonly string[]) => void): (field: string, invalid: boolean) => void {
  const callback = useRef(onInvalidInputsChange)
  callback.current = onInvalidInputsChange
  const [invalidByField, setInvalidByField] = useState<Record<string, boolean>>({})
  const report = useCallback((field: string, invalid: boolean) => {
    setInvalidByField(prev => (Boolean(prev[field]) === invalid ? prev : { ...prev, [field]: invalid }))
  }, [])
  const invalidFields = Object.keys(invalidByField)
    .filter(field => invalidByField[field])
    .sort()
  const invalidKey = JSON.stringify(invalidFields)
  // Starts as "nothing invalid", which the parent already assumes, so mounting reports nothing.
  const reportedKey = useRef('[]')
  useEffect(() => {
    if (reportedKey.current === invalidKey) return
    reportedKey.current = invalidKey
    callback.current(JSON.parse(invalidKey) as string[])
  }, [invalidKey])
  useEffect(() => {
    // The ref object, not its value: unmounting reports to the latest callback.
    const latest = callback
    return () => latest.current([])
  }, [])
  return report
}
