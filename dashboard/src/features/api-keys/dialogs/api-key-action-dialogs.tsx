import { useTranslation } from 'react-i18next'
import { Check, Copy } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import useDirDetection from '@/hooks/use-dir-detection'
import type { APIKeyResponse } from '@/service/api'

interface ApiKeyConfirmDialogProps {
  apiKey: APIKeyResponse | null
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  isPending?: boolean
}

export function ApiKeyDeleteDialog({ apiKey, onOpenChange, onConfirm, isPending }: ApiKeyConfirmDialogProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={!!apiKey} onOpenChange={onOpenChange}>
      <AlertDialogContent dir={dir}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('apiKeys.deleteTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('apiKeys.deletePrompt', { name: apiKey?.name })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => onOpenChange(false)}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm} disabled={isPending}>
            {t('delete')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export function ApiKeyRevokeDialog({ apiKey, onOpenChange, onConfirm, isPending }: ApiKeyConfirmDialogProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={!!apiKey} onOpenChange={onOpenChange}>
      <AlertDialogContent dir={dir}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('apiKeys.revokeTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('apiKeys.revokePrompt')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => onOpenChange(false)}>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} disabled={isPending}>
            {t('confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

interface ApiKeySecretDialogProps {
  apiKey: string | null
  copied: boolean
  onCopy: () => void
  onOpenChange: (open: boolean) => void
}

export function ApiKeySecretDialog({ apiKey, copied, onCopy, onOpenChange }: ApiKeySecretDialogProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  return (
    <AlertDialog open={!!apiKey} onOpenChange={onOpenChange}>
      <AlertDialogContent dir={dir}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('apiKeys.apiKey')}</AlertDialogTitle>
          <AlertDialogDescription>{t('apiKeys.apiKeyShowWarning')}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="flex items-center gap-2 py-2">
          <Input
            readOnly
            value={apiKey || ''}
            className="font-mono"
            onClick={(event) => (event.target as HTMLInputElement).select()}
          />
          <Button
            size="icon"
            variant="outline"
            onClick={onCopy}
            aria-label={t('apiKeys.apiKeyCopy')}
            title={t('apiKeys.apiKeyCopy')}
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>
        <AlertDialogFooter>
          <AlertDialogAction onClick={() => onOpenChange(false)}>{t('close')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
