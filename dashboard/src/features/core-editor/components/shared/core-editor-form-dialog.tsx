import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  filterValidationListItemsByPathPrefix,
  ValidationSummary,
} from '@/features/core-editor/components/shared/validation-summary'
import { useXrayPersistValidationItems } from '@/features/core-editor/hooks/use-xray-persist-validation-items'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'
import type { ReactNode } from 'react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

export interface CoreEditorFormDialogProps {
  /** Same naming as `HostModal` / bulk dialogs in this codebase. */
  isDialogOpen: boolean
  onOpenChange: (open: boolean) => void
  /** Main heading; use with {@link leadingIcon} to mirror `HostModal` (icon + label). */
  title: ReactNode
  /** Icon before the title; use `className="h-5 w-5"` on Lucide icons to match host modal. */
  leadingIcon?: ReactNode
  /** Secondary line; hidden visually unless `showDescription` (still announced when sr-only). */
  description?: ReactNode
  showDescription?: boolean
  children: ReactNode
  /** Max width on large screens — host modal uses `max-w-2xl`. */
  size?: 'md' | 'lg' | 'xl'
  /** Primary action before Cancel (e.g. Add / Save), same order as `LoaderButton` in `HostModal`. */
  footerExtra?: ReactNode
  className?: string
  /**
   * When the dialog is open, show global Xray persist/strict validation (same as the editor footer).
   * Set false only if the dialog embeds its own validation UI.
   */
  inlinePersistValidation?: boolean
  /**
   * When set (e.g. `/inbounds/3` for the third inbound), only show persist issues whose path is under
   * that prefix so another row’s errors do not appear in this dialog. Paths follow xray-config-kit
   * JSON pointers (first inbound is `/inbounds/1`).
   */
  persistValidationPathPrefix?: string
}

const sizeClass: Record<NonNullable<CoreEditorFormDialogProps['size']>, string> = {
  md: 'max-w-2xl',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
}

export function CoreEditorFormDialog({
  isDialogOpen,
  onOpenChange,
  title,
  leadingIcon,
  description,
  showDescription = false,
  children,
  size = 'lg',
  footerExtra,
  className,
  inlinePersistValidation = true,
  persistValidationPathPrefix,
}: CoreEditorFormDialogProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const allPersistValidationItems = useXrayPersistValidationItems()
  const persistValidationItems = useMemo(
    () => filterValidationListItemsByPathPrefix(allPersistValidationItems, persistValidationPathPrefix),
    [allPersistValidationItems, persistValidationPathPrefix],
  )

  return (
    <Dialog open={isDialogOpen} onOpenChange={onOpenChange}>
      <DialogContent
        dir={dir}
        onOpenAutoFocus={e => e.preventDefault()}
        className={cn('h-auto w-full gap-4', sizeClass[size], className)}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {leadingIcon}
            {typeof title === 'string' || typeof title === 'number' ? <span>{title}</span> : title}
          </DialogTitle>
          {description != null && (
            <DialogDescription className={cn(!showDescription && 'sr-only', showDescription && 'text-pretty')}>
              {description}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="-me-4 max-h-[80dvh] space-y-4 overflow-y-auto overscroll-contain px-2 pe-4 sm:max-h-[75dvh]">
          {isDialogOpen && inlinePersistValidation && persistValidationItems.length > 0 ? (
            <ValidationSummary items={persistValidationItems} className="shrink-0" />
          ) : null}
          {children}
        </div>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          {footerExtra}
        </div>
      </DialogContent>
    </Dialog>
  )
}
