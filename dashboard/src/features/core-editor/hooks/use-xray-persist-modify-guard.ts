import {
  filterValidationListBlockingErrors,
  formatValidationListItemsToastLines,
} from '@/features/core-editor/components/shared/validation-summary'
import { useXrayPersistValidationItems } from '@/features/core-editor/hooks/use-xray-persist-validation-items'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

/**
 * Persist validation (strict Xray + core-kit) for in-modal actions only.
 * Do **not** use this to block opening edit dialogs — users must be able to open a row to fix it.
 */
export function useXrayPersistModifyGuard() {
  const items = useXrayPersistValidationItems()
  const blocking = useMemo(() => filterValidationListBlockingErrors(items), [items])
  const { t } = useTranslation()

  const notifyPersistBlockingErrors = useCallback(() => {
    const description = formatValidationListItemsToastLines(blocking, 8)
    toast.error(
      t('coreEditor.validationBlockedAction', {
        defaultValue: 'Fix validation errors before changing the profile.',
      }),
      {
        description: description || undefined,
        duration: 12_000,
      },
    )
  }, [blocking, t])

  /** Use on “Add to list” (and similar) inside a dialog — never on row open / edit open. */
  const assertNoPersistBlockingErrors = useCallback((): boolean => {
    if (blocking.length === 0) return true
    notifyPersistBlockingErrors()
    return false
  }, [blocking, notifyPersistBlockingErrors])

  return { blocking, notifyPersistBlockingErrors, assertNoPersistBlockingErrors }
}
