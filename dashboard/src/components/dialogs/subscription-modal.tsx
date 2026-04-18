import { FC, memo, useState, useEffect, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { QRCodeCanvas } from 'qrcode.react'
import { useTranslation } from 'react-i18next'
import { ScanQrCode, Copy, QrCode, ChevronLeft, ChevronRight, Check, Loader2, RefreshCw, Download } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  downloadTextFile,
  encodeSubscriptionContentToBase64,
  extractAddressFromConfigUrl,
  extractNameFromConfigUrl,
  fetchSubscriptionContent,
  getWireGuardDownloadPayload,
  prepareSubscriptionContentForCopy,
  resolveSubscriptionQrUrl,
} from '@/utils/subscription-config'

interface SubscriptionModalProps {
  subscribeUrl: string | null
  username: string
  onCloseModal: () => void
}

interface ConfigItem {
  config: string
  name: string
  address: string | null
}

type ConfigCopyMode = 'config' | 'base64'
type ConfigQrMode = 'config' | 'uri'

interface CopiedConfigState {
  config: string
  mode: ConfigCopyMode
}

const CONFIGS_PER_PAGE = 5
const LINKS_FETCH_TIMEOUT_MS = 8000

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
  const [selectedConfigQrMode, setSelectedConfigQrMode] = useState<ConfigQrMode>('config')
  const [copiedConfig, setCopiedConfig] = useState<CopiedConfigState | null>(null)
  const [allConfigsCopied, setAllConfigsCopied] = useState(false)

  const subscribeQrLink = resolveSubscriptionQrUrl(subscribeUrl)

  const fetchConfigs = useCallback(async () => {
    if (!subscribeUrl) return

    setIsLoading(true)
    setError(null)

    try {
      const text = await fetchSubscriptionContent(subscribeUrl, 'links', LINKS_FETCH_TIMEOUT_MS)
      const configLines = text.split('\n').filter(line => line.trim() !== '')

      setConfigs(
        configLines.map(config => ({
          config,
          name: extractNameFromConfigUrl(config) || t('subscriptionModal.unknownConfig', { defaultValue: 'Unknown Config' }),
          address: extractAddressFromConfigUrl(config),
        })),
      )
      setCurrentPage(0)
    } catch (err) {
      console.error('Failed to fetch configs:', err)
      setError(t('subscriptionModal.fetchError', { defaultValue: 'Failed to fetch configurations' }))
    } finally {
      setIsLoading(false)
    }
  }, [subscribeUrl, t])

  useEffect(() => {
    fetchConfigs()
  }, [fetchConfigs])

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

  const handleCopyConfig = useCallback(
    async (config: string, mode: ConfigCopyMode = 'config') => {
      try {
        const preparedContent = prepareSubscriptionContentForCopy(config).content
        const copyContent = mode === 'base64' ? encodeSubscriptionContentToBase64(preparedContent) : preparedContent
        await navigator.clipboard.writeText(copyContent)
        setCopiedConfig({ config, mode })
        toast.success(t('usersTable.copied', { defaultValue: 'Copied' }))
        setTimeout(() => setCopiedConfig(null), 1500)
      } catch {
        toast.error(t('copyFailed', { defaultValue: 'Failed to copy' }))
      }
    },
    [t],
  )

  const handleCopyAllConfigs = useCallback(async () => {
    try {
      const content = prepareSubscriptionContentForCopy(configs.map(item => item.config).join('\n')).content
      await navigator.clipboard.writeText(content)
      setAllConfigsCopied(true)
      toast.success(t('usersTable.copied', { defaultValue: 'Copied' }))
      setTimeout(() => setAllConfigsCopied(false), 1500)
    } catch {
      toast.error(t('copyFailed', { defaultValue: 'Failed to copy' }))
    }
  }, [configs, t])

  const handleDownloadWireGuard = useCallback(
    (config: string) => {
      try {
        const payload = getWireGuardDownloadPayload(config)
        if (!payload) {
          throw new Error('WireGuard config not available')
        }

        downloadTextFile(payload.content, payload.fileName)
        toast.success(t('usersTable.downloadStarted', { defaultValue: 'Download started' }))
      } catch {
        toast.error(t('downloadFailed', { defaultValue: 'Failed to download config' }))
      }
    },
    [t],
  )

  const handleShowConfigQR = (config: ConfigItem) => {
    setSelectedConfigQrMode('config')
    setSelectedConfigQR(config)
  }

  const handleCloseConfigQR = () => {
    setSelectedConfigQrMode('config')
    setSelectedConfigQR(null)
  }

  const selectedConfigWireGuardDownload = selectedConfigQR ? getWireGuardDownloadPayload(selectedConfigQR.config) : null
  const selectedConfigQrValue =
    selectedConfigWireGuardDownload && selectedConfigQrMode === 'config' ? selectedConfigWireGuardDownload.content : selectedConfigQR?.config || ''

  return (
    <>
      <Dialog open={isOpen && !selectedConfigQR} onOpenChange={onCloseModal}>
        <DialogContent className="max-h-[90dvh] max-w-[860px] overflow-y-auto overflow-x-hidden">
          <DialogHeader dir={dir}>
            <DialogTitle className="flex items-center gap-2">
              <ScanQrCode className="h-5 w-5 shrink-0" />
              <span>{t('subscriptionModal.title', { username, defaultValue: "{{username}}'s Subscription" })}</span>
            </DialogTitle>
          </DialogHeader>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:items-center">
            <div className="flex flex-col items-center gap-3">
              <div dir="ltr" className="flex max-w-[280px] items-center justify-center overflow-hidden">
                <QRCodeCanvas value={subscribeQrLink} size={260} className="rounded-sm bg-white p-1.5" />
              </div>
            </div>

            <div className="flex flex-col gap-3 h-full">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{t('subscriptionModal.configs', { defaultValue: 'Configurations' })}</span>
                <Button variant="ghost" size="sm" onClick={handleCopyAllConfigs} disabled={isLoading || configs.length === 0} className="h-7 px-2 text-xs">
                  {allConfigsCopied ? <Check className={cn('h-3 w-3', isRTL ? 'ml-1' : 'mr-1')} /> : <Copy className={cn('h-3 w-3', isRTL ? 'ml-1' : 'mr-1')} />}
                  <span className="hidden sm:inline">{t('subscriptionModal.copyAll', { defaultValue: 'Copy All' })}</span>
                </Button>
              </div>

              {isLoading ? (
                <div className="flex h-[200px] items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : error ? (
                <div className="flex h-[200px] flex-col items-center justify-center gap-3">
                  <span className="text-sm text-destructive">{error}</span>
                  <Button variant="outline" size="sm" onClick={fetchConfigs}>
                    <RefreshCw className={cn('h-4 w-4', isRTL ? 'ml-2' : 'mr-2')} />
                    {t('retry', { defaultValue: 'Retry' })}
                  </Button>
                </div>
              ) : configs.length === 0 ? (
                <div className="flex h-[200px] items-center justify-center">
                  <span className="text-sm text-muted-foreground">{t('subscriptionModal.noConfigs', { defaultValue: 'No configurations found' })}</span>
                </div>
              ) : (
                <>
                  <div dir="ltr" className="flex flex-col gap-2">
                    {currentConfigs.map((item, index) => {
                      const wireGuardDownload = getWireGuardDownloadPayload(item.config)

                      return (
                        <div key={startIndex + index} className="flex items-center justify-between rounded-md border p-2 hover:bg-muted/50">
                          <div className="flex flex-1 flex-col gap-1 overflow-hidden">
                            <span dir="ltr" className="text-sm font-medium" title={item.name}>
                              <span className="sm:hidden">{item.name.length > 30 ? `${item.name.slice(0, 30)}...` : item.name}</span>
                              <span className="hidden sm:inline">{item.name.length > 40 ? `${item.name.slice(0, 40)}...` : item.name}</span>
                            </span>
                            {item.address && (
                              <Badge variant="secondary" className="w-fit text-xs font-normal opacity-70">
                                {item.address}
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-1">
                            {wireGuardDownload && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => handleDownloadWireGuard(item.config)}
                                title={t('configActions.downloadWireGuard', { defaultValue: 'Download WireGuard' })}
                                aria-label={t('configActions.downloadWireGuard', { defaultValue: 'Download WireGuard' })}
                              >
                                <Download className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => handleCopyConfig(item.config)}
                              title={t('configActions.copyConfig', { defaultValue: 'Copy Config' })}
                              aria-label={t('configActions.copyConfig', { defaultValue: 'Copy Config' })}
                            >
                              {copiedConfig?.config === item.config && copiedConfig?.mode === 'config' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                            </Button>
                            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleShowConfigQR(item)}>
                              <QrCode className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-4 pt-2">
                      <Button variant="outline" size="icon" className="h-8 w-8" onClick={isRTL ? handleNextPage : handlePreviousPage} disabled={totalPages <= 1}>
                        <ChevronLeft className={cn('h-4 w-4', dir === 'rtl' && 'rotate-180')} />
                      </Button>
                      <span className="text-sm text-muted-foreground">
                        {currentPage + 1} / {totalPages}
                      </span>
                      <Button variant="outline" size="icon" className="h-8 w-8" onClick={isRTL ? handlePreviousPage : handleNextPage} disabled={totalPages <= 1}>
                        <ChevronRight className={cn('h-4 w-4', dir === 'rtl' && 'rotate-180')} />
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!selectedConfigQR} onOpenChange={handleCloseConfigQR}>
        <DialogContent className="w-[calc(100vw-2rem)] max-w-[380px] sm:max-w-[420px]">
          <DialogHeader dir={dir}>
            <DialogTitle className="flex items-center gap-2">
              <QrCode className="h-5 w-5 shrink-0" />
              <span title={selectedConfigQR?.name}>
                {selectedConfigQR?.name && selectedConfigQR.name.length > 20 ? `${selectedConfigQR.name.slice(0, 20)}...` : selectedConfigQR?.name}
              </span>
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col items-center gap-4 py-2">
            {selectedConfigWireGuardDownload && (
              <ToggleGroup
                type="single"
                value={selectedConfigQrMode}
                onValueChange={value => {
                  if (value === 'config' || value === 'uri') {
                    setSelectedConfigQrMode(value)
                  }
                }}
                variant="outline"
                size="sm"
                className="rounded-md border border-border bg-muted/30 p-1"
                aria-label={t('subscriptionModal.qrFormat', { defaultValue: 'QR code format' })}
              >
                <ToggleGroupItem value="config" className="h-7 px-2.5 text-[11px]">
                  {t('subscriptionModal.qrFormatConfig', { defaultValue: 'Config' })}
                </ToggleGroupItem>
                <ToggleGroupItem value="uri" className="h-7 px-2.5 text-[11px]">
                  URI
                </ToggleGroupItem>
              </ToggleGroup>
            )}
            <div dir="ltr" className="flex items-center justify-center overflow-hidden">
              <QRCodeCanvas value={selectedConfigQrValue} size={220} className="max-w-full rounded-sm bg-white p-2" />
            </div>
            <div dir={dir} className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
              <Button
                variant="outline"
                onClick={() => selectedConfigQR && handleCopyConfig(selectedConfigQR.config)}
                className={cn('h-auto min-h-11 w-full gap-3 px-3 py-3 text-sm leading-tight whitespace-normal', isRTL ? 'flex-row-reverse text-right' : 'justify-start text-left')}
              >
                {copiedConfig?.config === selectedConfigQR?.config && copiedConfig?.mode === 'config' ? (
                  <Check className="h-4 w-4 shrink-0" />
                ) : (
                  <Copy className="h-4 w-4 shrink-0" />
                )}
                {t('configActions.copyConfig', { defaultValue: 'Copy Config' })}
              </Button>
              <Button
                variant="outline"
                onClick={() => selectedConfigQR && handleCopyConfig(selectedConfigQR.config, 'base64')}
                className={cn('h-auto min-h-11 w-full gap-3 px-3 py-3 text-sm leading-tight whitespace-normal', isRTL ? 'flex-row-reverse text-right' : 'justify-start text-left')}
              >
                {copiedConfig?.config === selectedConfigQR?.config && copiedConfig?.mode === 'base64' ? (
                  <Check className="h-4 w-4 shrink-0" />
                ) : (
                  <Copy className="h-4 w-4 shrink-0" />
                )}
                {t('configActions.copyBase64', { defaultValue: 'Copy Base64' })}
              </Button>
              {selectedConfigWireGuardDownload && (
                <Button
                  variant="outline"
                  onClick={() => selectedConfigQR && handleDownloadWireGuard(selectedConfigQR.config)}
                  className={cn('h-auto min-h-11 w-full gap-3 px-3 py-3 text-sm leading-tight whitespace-normal sm:col-span-2', isRTL ? 'flex-row-reverse text-right' : 'justify-start text-left')}
                >
                  <Download className="h-4 w-4 shrink-0" />
                  {t('configActions.downloadWireGuard', { defaultValue: 'Download WireGuard' })}
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
})

export default SubscriptionModal
