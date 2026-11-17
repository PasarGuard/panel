import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoaderButton } from '@/components/ui/loader-button'
import { getCoreCertificateFingerprint, type CertificateFingerprintRequest } from '@/service/api'

interface CertificateFingerprintButtonProps {
  request: CertificateFingerprintRequest | undefined
  onFingerprint: (fingerprint: string) => void
}

export function CertificateFingerprintButton({ request, onFingerprint }: CertificateFingerprintButtonProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const requestKey = JSON.stringify(request)

  useEffect(() => {
    setLoading(false)
    setError(null)
    return () => {
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [requestKey])

  const calculate = async () => {
    if (!request) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setLoading(true)
    setError(null)
    try {
      const result = await getCoreCertificateFingerprint(request, { signal: controller.signal })
      if (!controller.signal.aborted) onFingerprint(result.sha256)
    } catch (error) {
      if (!controller.signal.aborted) {
        const detail = (error as { data?: { detail?: unknown } })?.data?.detail
        setError(
          request.file_path && detail === 'Cannot read certificate file'
            ? t('coreEditor.certificateFingerprint.pathUnavailable')
            : typeof detail === 'string'
              ? detail
              : t('coreEditor.certificateFingerprint.failed'),
        )
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return (
    <div className="shrink-0 space-y-1">
      <LoaderButton
        type="button"
        variant="outline"
        size="sm"
        className="h-10"
        isLoading={loading}
        disabled={loading || !request}
        onClick={calculate}
        title={!request ? t('coreEditor.certificateFingerprint.missingSource') : undefined}
      >
        {t('coreEditor.certificateFingerprint.calculate')}
      </LoaderButton>
      {error && (
        <p role="alert" className="text-destructive max-w-64 text-xs">
          {error}
        </p>
      )}
    </div>
  )
}
