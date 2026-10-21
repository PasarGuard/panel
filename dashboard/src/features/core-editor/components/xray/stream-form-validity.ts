import { useCallback, useEffect, useRef, useState } from 'react'

/** `onValidityChange` for inputs whose text always parses (trimmed text, a password written as typed). */
export const ignoreValidity = (): void => {}

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
