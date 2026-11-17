import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoaderButton } from '@/components/ui/loader-button'
import { getCoreCertificateFingerprint } from '@/service/api'

interface FetchNodeFingerprintButtonProps {
  address: string
  port: number
  onFingerprint: (fingerprint: string) => void
}

export function FetchNodeFingerprintButton({ address, port, onFingerprint }: FetchNodeFingerprintButtonProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    setLoading(false)
    setError(null)
    return () => {
      controllerRef.current?.abort()
      controllerRef.current = null
    }
  }, [address, port])

  const fetchFingerprint = async () => {
    const controller = new AbortController()
    controllerRef.current = controller
    setLoading(true)
    setError(null)
    try {
      const result = await getCoreCertificateFingerprint({ server: address, port }, { signal: controller.signal })
      if (!controller.signal.aborted) onFingerprint(result.sha256)
    } catch (error) {
      if (!controller.signal.aborted) {
        const detail = (error as { data?: { detail?: unknown } })?.data?.detail
        setError(typeof detail === 'string' ? detail : t('nodeModal.fetchFingerprintFailed'))
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return (
    <div className="space-y-2">
      <LoaderButton
        type="button"
        variant="outline"
        size="sm"
        isLoading={loading}
        disabled={loading || !address.trim() || !Number.isInteger(port) || port < 1 || port > 65535}
        onClick={fetchFingerprint}
      >
        {t('nodeModal.fetchFingerprint')}
      </LoaderButton>
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
    </div>
  )
}
