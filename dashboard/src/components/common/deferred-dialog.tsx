import { Suspense, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Spinner } from '@/components/common/spinner'

type DeferredDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}

/** Load on first open, then retain the dialog for its close effects and exit animation. */
export function DeferredDialog({ open, onOpenChange, children }: DeferredDialogProps) {
  const [hasOpened, setHasOpened] = useState(open)
  const { t } = useTranslation()

  useEffect(() => {
    if (open) setHasOpened(true)
  }, [open])

  if (!open && !hasOpened) return null

  return (
    <Suspense
      fallback={
        <Dialog open={open} onOpenChange={onOpenChange}>
          <DialogContent
            aria-describedby={undefined}
            onCloseAutoFocus={event => {
              // Loading finished: let the real dialog receive focus.
              if (open) event.preventDefault()
            }}
          >
            <DialogHeader>
              <DialogTitle>{t('loading')}</DialogTitle>
            </DialogHeader>
            <div className="flex justify-center py-6" role="status" aria-label={t('loading')}>
              <Spinner />
            </div>
          </DialogContent>
        </Dialog>
      }
    >
      {children}
    </Suspense>
  )
}
