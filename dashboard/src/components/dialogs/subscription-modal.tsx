import { FC, memo, useState, useEffect, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { QRCodeCanvas } from 'qrcode.react'
import { useTranslation } from 'react-i18next'
import { ScanQrCode, Copy, QrCode, ChevronLeft, ChevronRight, Check, Loader2 } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface SubscriptionModalProps {
  subscribeUrl: string | null
  username: string
  onCloseModal: () => void
}

interface ConfigItem {
  config: string
  name: string
}

const CONFIGS_PER_PAGE = 3

const extractNameFromConfigURL = (url: string): string | null => {
  const namePattern = /#([^#]*)/
  const match = url.match(namePattern)

  if (match) {
    try {
      return decodeURIComponent(match[1])
    } catch (error) {
      console.error('Malformed URI component:', match[1], error)
      return match[1]
    }
  }

  if (url.startsWith('vmess://')) {
    const encodedString = url.replace('vmess://', '')

    try {
      const decodedString = atob(encodedString)
      return JSON.parse(decodedString).ps
    } catch (error) {
      console.error('Invalid vmess URL format:', error)
      return null
    }
  }
  return null
}

const SubscriptionModal: FC<SubscriptionModalProps> = memo(({ subscribeUrl, username, onCloseModal }) => {
  const isOpen = subscribeUrl !== null
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'

  const [configs, setConfigs] = useState<ConfigItem[]>([])
  const [currentPage, setCurrentPage] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedConfigQR, setSelectedConfigQR] = useState<ConfigItem | null>(null)
  const [copiedConfig, setCopiedConfig] = useState<string | null>(null)
  const [allConfigsCopied, setAllConfigsCopied] = useState(false)

  const sublink = String(subscribeUrl).startsWith('/') 
    ? window.location.origin + subscribeUrl 
    : String(subscribeUrl)

  const subscribeQrLink = sublink

  useEffect(() => {
    if (!subscribeUrl) return

    const fetchConfigs = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const response = await fetch(`${sublink}/links`)
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        const text = await response.text()
        const configLines = text.split('\n').filter(line => line.trim() !== '')
        setConfigs(configLines.map(config => ({
          config,
          name: extractNameFromConfigURL(config) || t('subscriptionModal.unknownConfig', { defaultValue: 'Unknown Config' })
        })))
        setCurrentPage(0)
      } catch (err) {
        console.error('Failed to fetch configs:', err)
        setError(t('subscriptionModal.fetchError', { defaultValue: 'Failed to fetch configurations' }))
      } finally {
        setIsLoading(false)
      }
    }

    fetchConfigs()
  }, [subscribeUrl, sublink, t])

  const totalPages = Math.ceil(configs.length / CONFIGS_PER_PAGE)
  const startIndex = currentPage * CONFIGS_PER_PAGE
  const endIndex = startIndex + CONFIGS_PER_PAGE
  const currentConfigs = configs.slice(startIndex, endIndex)

  const handlePreviousPage = () => {
    setCurrentPage(prev => (prev > 0 ? prev - 1 : totalPages - 1))
  }

  const handleNextPage = () => {
    setCurrentPage(prev => (prev < totalPages - 1 ? prev + 1 : 0))
  }

  const handleCopyConfig = useCallback(async (config: string) => {
    try {
      await navigator.clipboard.writeText(config)
      setCopiedConfig(config)
      toast.success(t('usersTable.copied', { defaultValue: 'Copied' }))
      setTimeout(() => setCopiedConfig(null), 1500)
    } catch (error) {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy' }))
    }
  }, [t])

  const handleCopyAllConfigs = useCallback(async () => {
    try {
      const response = await fetch(`${sublink}/links`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const content = await response.text()
      await navigator.clipboard.writeText(content)
      setAllConfigsCopied(true)
      toast.success(t('usersTable.copied', { defaultValue: 'Copied' }))
      setTimeout(() => setAllConfigsCopied(false), 1500)
    } catch (error) {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy' }))
    }
  }, [sublink, t])

  const handleShowConfigQR = (config: ConfigItem) => {
    setSelectedConfigQR(config)
  }

  const handleCloseConfigQR = () => {
    setSelectedConfigQR(null)
  }

  return (
    <>
      <Dialog open={isOpen && !selectedConfigQR} onOpenChange={onCloseModal}>
        <DialogContent className="max-h-[90dvh] max-w-[500px] overflow-y-auto overflow-x-hidden">
          <DialogHeader dir={dir}>
            <DialogTitle>
              <div className="flex items-center gap-2 px-2">
                <ScanQrCode className="h-6 w-6" />
                <span>{t('subscriptionModal.title', { username, defaultValue: "{{username}}'s Subscription" })}</span>
              </div>
            </DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-4">
            {/* Subscription QR Code Section */}
            <div className="flex w-full items-center justify-between">
              <span className="text-sm font-medium">{t('subscriptionModal.subscriptionLink', { defaultValue: 'Subscription Link' })}</span>
            </div>
            <div className="flex flex-col items-center gap-3 rounded-lg border p-4">
              <div dir="ltr" className="flex max-w-[200px] items-center justify-center overflow-hidden">
                <QRCodeCanvas value={subscribeQrLink} size={200} className="rounded-md bg-white p-2" />
              </div>
            </div>

            <Separator />

            {/* Configs Section */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{t('subscriptionModal.configs', { defaultValue: 'Configurations' })}</span>
                <Button variant="outline" size="sm" onClick={handleCopyAllConfigs} disabled={isLoading || configs.length === 0} className="h-8">
                  {allConfigsCopied ? <Check className={cn('h-4 w-4', isRTL ? 'ml-2' : 'mr-2')} /> : <Copy className={cn('h-4 w-4', isRTL ? 'ml-2' : 'mr-2')} />}
                  {t('subscriptionModal.copyAll', { defaultValue: 'Copy All' })}
                </Button>
              </div>

              {isLoading ? (
                <div className="flex h-[200px] items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : error ? (
                <div className="flex h-[200px] items-center justify-center">
                  <span className="text-sm text-destructive">{error}</span>
                </div>
              ) : configs.length === 0 ? (
                <div className="flex h-[200px] items-center justify-center">
                  <span className="text-sm text-muted-foreground">{t('subscriptionModal.noConfigs', { defaultValue: 'No configurations found' })}</span>
                </div>
              ) : (
                <>
                  {/* Configs List */}
                  <div className="flex flex-col gap-2">
                    {currentConfigs.map((item, index) => (
                      <div key={startIndex + index} className="flex items-center justify-between rounded-md border p-2 hover:bg-muted/50">
                        <span dir="ltr" className="flex-1 truncate text-sm" title={item.name}>
                          {item.name}
                        </span>
                        <div className="flex items-center gap-1">
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleCopyConfig(item.config)}>
                            {copiedConfig === item.config ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleShowConfigQR(item)}>
                            <QrCode className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-4 pt-2">
                      <Button variant="outline" size="icon" className="h-8 w-8" onClick={isRTL ? handleNextPage : handlePreviousPage} disabled={totalPages <= 1}>
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        {currentPage + 1} / {totalPages}
                      </span>
                      <Button variant="outline" size="icon" className="h-8 w-8" onClick={isRTL ? handlePreviousPage : handleNextPage} disabled={totalPages <= 1}>
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Individual Config QR Code Dialog */}
      <Dialog open={!!selectedConfigQR} onOpenChange={handleCloseConfigQR}>
        <DialogContent className="max-w-[350px]">
          <DialogHeader dir={dir}>
            <DialogTitle>
              <div className="flex items-center gap-2 px-2">
                <QrCode className="h-6 w-6" />
                <span className="truncate">{selectedConfigQR?.name}</span>
              </div>
            </DialogTitle>
          </DialogHeader>
          <div dir="ltr" className="flex flex-col items-center gap-4 py-4">
            <div className="flex items-center justify-center overflow-hidden">
              <QRCodeCanvas value={selectedConfigQR?.config || ''} size={280} className="rounded-md bg-white p-2" />
            </div>
            <Button variant="outline" onClick={() => selectedConfigQR && handleCopyConfig(selectedConfigQR.config)} className="w-full">
              {copiedConfig === selectedConfigQR?.config ? <Check className={cn('h-4 w-4', isRTL ? 'ml-2' : 'mr-2')} /> : <Copy className={cn('h-4 w-4', isRTL ? 'ml-2' : 'mr-2')} />}
              {t('subscriptionModal.copyConfig', { defaultValue: 'Copy Config' })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
})

export default SubscriptionModal
