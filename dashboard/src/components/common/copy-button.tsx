import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useClipboard } from '@/hooks/use-clipboard'
import { Check, Copy, Link } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface CopyButtonProps {
  value: string
  className?: string
  copiedMessage?: string
  defaultMessage?: string
  icon?: 'copy' | 'link'
  onClick?: (e: React.MouseEvent) => void
  showToast?: boolean
  toastSuccessMessage?: string
  toastErrorMessage?: string
}

export function CopyButton({ value, className, copiedMessage = 'Copied!', defaultMessage = 'Click to copy', icon = 'copy', onClick, showToast = false, toastSuccessMessage, toastErrorMessage }: CopyButtonProps) {
  const { t } = useTranslation()

  const { copy, copied, error } = useClipboard({ timeout: 1500 })
  const shouldShowToast = useRef(false)

  const handleCopy = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      shouldShowToast.current = showToast
      await copy(value)
      onClick?.(e)
    },
    [copy, value, onClick, showToast],
  )

  useEffect(() => {
    if (!shouldShowToast.current) return

    if (copied) {
      toast.success(toastSuccessMessage ? t(toastSuccessMessage) : t(copiedMessage))
      shouldShowToast.current = false
    } else if (error) {
      toast.error(toastErrorMessage ? t(toastErrorMessage) : t('copyFailed', { defaultValue: 'Failed to copy' }))
      shouldShowToast.current = false
    }
  }, [copied, error, toastSuccessMessage, toastErrorMessage, copiedMessage, t])

  return (
    <Tooltip open={copied ? true : undefined}>
      <TooltipTrigger asChild>
        <div>
          <Button type="button" size="icon" variant="ghost" className={className} aria-label="Copy to clipboard" onClick={handleCopy}>
            {copied ? <Check className="h-4 w-4" /> : icon === 'copy' ? <Copy className="h-4 w-4" /> : <Link className="h-4 w-4" />}
          </Button>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>{copied ? t(copiedMessage) : t(defaultMessage)}</p>
      </TooltipContent>
    </Tooltip>
  )
}
