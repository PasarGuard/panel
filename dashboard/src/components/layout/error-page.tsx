import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useClipboard } from '@/hooks/use-clipboard'
import useDirDirection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { getErrorMessage, getErrorStack, getErrorStatus, getSerializableError } from '@/utils/error-utils'
import { AlertTriangle, ArrowLeft, Check, Copy, LogIn, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { isRouteErrorResponse, useRouteError } from 'react-router'
import { toast } from 'sonner'

type ErrorPageProps = {
  error?: unknown
  componentStack?: string
  resetError?: () => void
}

function getErrorCopyKey(error: unknown) {
  const status = getErrorStatus(error)

  if (status === 401) {
    return 'unauthorized'
  }

  if (status === 403) {
    return 'forbidden'
  }

  if (status === 404) {
    return 'notFound'
  }

  if (status && status >= 500) {
    return 'serverError'
  }

  return 'generic'
}

export function ErrorPage({ error, componentStack, resetError }: ErrorPageProps) {
  const { t } = useTranslation(undefined, { useSuspense: false })
  const dir = useDirDirection()
  const isRtl = dir === 'rtl'
  const { copy, copied, error: copyError } = useClipboard({ timeout: 1500 })
  const shouldShowCopyToast = useRef(false)
  const copyKey = getErrorCopyKey(error)
  const status = getErrorStatus(error)
  const eyebrow = status ? String(status) : t('errorPage.errorCode', { defaultValue: 'Error' })
  const title = t(`errorPage.${copyKey}.title`)
  const description = t(`errorPage.${copyKey}.description`)
  const message = getErrorMessage(error)
  const showLoginAction = getErrorStatus(error) === 401
  const stack = getErrorStack(error)
  const serializedError = getSerializableError(error)
  const errorReport = useMemo(() => {
    return [
      `URL: ${window.location.href}`,
      `Time: ${new Date().toISOString()}`,
      status ? `Status: ${status}` : undefined,
      `Title: ${title}`,
      `Message: ${message}`,
      stack ? `Stack:\n${stack}` : undefined,
      componentStack ? `React component stack:\n${componentStack}` : undefined,
      serializedError ? `Raw error:\n${serializedError}` : undefined,
    ]
      .filter(Boolean)
      .join('\n\n')
  }, [componentStack, message, serializedError, stack, status, title])
  const goToHashRoute = (path: string) => {
    window.location.hash = path
  }
  const handleCopyError = async () => {
    shouldShowCopyToast.current = true
    await copy(errorReport)
  }

  useEffect(() => {
    if (!shouldShowCopyToast.current) return

    if (copied) {
      toast.success(t('errorPage.actions.copiedDetails'))
      shouldShowCopyToast.current = false
    } else if (copyError) {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy' }))
      shouldShowCopyToast.current = false
    }
  }, [copied, copyError, t])

  return (
    <div className="bg-background flex min-h-screen w-full items-center justify-center px-4 py-8" dir={dir}>
      <div className="border-border/70 bg-card text-card-foreground w-full max-w-xl rounded-lg border p-6 shadow-[var(--card-shadow)] sm:p-8">
        <div className={cn('flex items-start gap-4')}>
          <div className="bg-destructive/10 text-destructive flex h-11 w-11 shrink-0 items-center justify-center rounded-md">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-muted-foreground text-sm font-medium">{eyebrow}</div>
            <h1 className="mt-1 text-2xl font-semibold">{title}</h1>
            <p className="text-muted-foreground mt-2 text-sm leading-6">{description}</p>
          </div>
        </div>

        {message && message !== description && (
          <div className="border-border/70 bg-muted/40 relative mt-5 rounded-md border" dir="ltr">
            <pre className="text-muted-foreground max-h-44 overflow-auto p-3 pb-12 text-xs leading-5 whitespace-pre-wrap">{message}</pre>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="ghost" size="icon" className="absolute right-2 bottom-2 h-7 w-7" onClick={handleCopyError}>
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  <span className="sr-only">{t('errorPage.actions.copyDetails')}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{copied ? t('errorPage.actions.copiedDetails') : t('errorPage.actions.copyDetails')}</p>
              </TooltipContent>
            </Tooltip>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2 sm:flex-row-reverse sm:flex-wrap">
          <Button type="button" className="w-full sm:w-28" onClick={resetError ?? (() => window.location.reload())}>
            <RefreshCw className="h-4 w-4" />
            <span>{t('errorPage.actions.tryAgain')}</span>
          </Button>
          <Button type="button" variant="outline" className="w-full sm:w-28" onClick={() => window.history.back()}>
            <ArrowLeft className={cn('h-4 w-4', isRtl && 'scale-x-[-1]')} />
            <span>{t('errorPage.actions.back')}</span>
          </Button>
          {showLoginAction && (
            <Button type="button" variant="ghost" className="w-full sm:w-28" onClick={() => goToHashRoute('/login')}>
              <LogIn className="h-4 w-4" />
              <span>{t('errorPage.actions.login')}</span>
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

export function RouteErrorPage() {
  const routeError = useRouteError()
  const error = isRouteErrorResponse(routeError)
    ? {
        status: routeError.status,
        data: {
          detail: routeError.data || routeError.statusText,
        },
      }
    : routeError

  return <ErrorPage error={error} resetError={() => window.location.reload()} />
}
