import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useFormField } from '@/components/ui/form'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

const warningKeys = new Map([
  ['android', 'tls13'],
  ['360', 'tls13'],
  ['unsafe', 'unsafe'],
  ['edge', 'modern'],
  ['qq', 'modern'],
  ['ios', 'modern'],
  ['random', 'random'],
  ['randomized', 'random'],
  ['randomizednoalpn', 'random'],
])

interface RealityFingerprintWarningProps {
  fingerprint: string
  onUseChrome: () => void
}

export default function RealityFingerprintWarning({ fingerprint, onUseChrome }: RealityFingerprintWarningProps) {
  const { t } = useTranslation()
  const { formDescriptionId } = useFormField()
  const warningKey = warningKeys.get(fingerprint)

  if (!warningKey) return null

  return (
    <Alert
      id={formDescriptionId}
      className="border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-100 [&>svg]:top-4 [&>svg]:translate-y-0 [&>svg]:text-amber-600 rtl:[&>svg]:right-4 rtl:[&>svg]:left-auto dark:[&>svg]:text-amber-400 rtl:[&>svg~*]:pr-7 rtl:[&>svg~*]:pl-0"
    >
      <AlertTriangle className="h-4 w-4" aria-hidden="true" />
      <AlertTitle className="text-sm leading-snug">{t('hostsDialog.realityFingerprint.title')}</AlertTitle>
      <AlertDescription className="space-y-3 text-xs leading-relaxed sm:text-sm">
        <p>{t(`hostsDialog.realityFingerprint.${warningKey}`)}</p>
        <Button type="button" variant="outline" size="sm" onClick={onUseChrome}>
          {t('hostsDialog.realityFingerprint.useChrome')}
        </Button>
      </AlertDescription>
    </Alert>
  )
}
