import { FC, memo, useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { QRCodeCanvas } from 'qrcode.react'
import { useTranslation } from 'react-i18next'
import { ScanQrCode, ChevronLeft, ChevronRight } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'
import { Button } from '@/components/ui/button'

interface ConfigsQRCodeModalProps {
  subscribeUrl: string | null
  onCloseModal: () => void
}

interface ConfigLink {
  config: string
  index: number
}

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

const ConfigsQRCodeModal: FC<ConfigsQRCodeModalProps> = memo(({ subscribeUrl, onCloseModal }) => {
  const isOpen = subscribeUrl !== null
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isRTL = dir === 'rtl'

  const [configs, setConfigs] = useState<ConfigLink[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const sublink = String(subscribeUrl).startsWith('/') 
    ? window.location.origin + subscribeUrl 
    : String(subscribeUrl)

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
        setConfigs(configLines.map((config, index) => ({ config, index })))
        setCurrentIndex(0)
      } catch (err) {
        console.error('Failed to fetch configs:', err)
        setError(t('configsQrcodeDialog.fetchError', { defaultValue: 'Failed to fetch configurations' }))
      } finally {
        setIsLoading(false)
      }
    }

    fetchConfigs()
  }, [subscribeUrl, sublink, t])

  const handlePrevious = () => {
    setCurrentIndex(prev => (prev > 0 ? prev - 1 : configs.length - 1))
  }

  const handleNext = () => {
    setCurrentIndex(prev => (prev < configs.length - 1 ? prev + 1 : 0))
  }

  const currentConfig = configs[currentIndex]
  const configName = currentConfig ? extractNameFromConfigURL(currentConfig.config) : null

  return (
    <Dialog open={isOpen} onOpenChange={onCloseModal}>
      <DialogContent className="max-h-[100dvh] max-w-[425px] overflow-y-auto overflow-x-hidden">
        <DialogHeader dir={dir}>
          <DialogTitle>
            <div className="px-2">
              <ScanQrCode className="h-8 w-8" />
            </div>
          </DialogTitle>
        </DialogHeader>
        <div dir="ltr" className="flex w-full justify-center overflow-x-hidden">
          <div className="flex w-full flex-col items-center justify-center gap-y-4 py-4 px-2">
            {isLoading ? (
              <div className="flex h-[300px] items-center justify-center">
                <span className="text-muted-foreground">{t('loading', { defaultValue: 'Loading...' })}</span>
              </div>
            ) : error ? (
              <div className="flex h-[300px] items-center justify-center">
                <span className="text-destructive">{error}</span>
              </div>
            ) : configs.length === 0 ? (
              <div className="flex h-[300px] items-center justify-center">
                <span className="text-muted-foreground">
                  {t('configsQrcodeDialog.noConfigs', { defaultValue: 'No configurations found' })}
                </span>
              </div>
            ) : (
              <>
                <div className="flex w-full items-center justify-center">
                  <div className="flex items-center justify-center overflow-hidden max-w-[calc(100vw-80px)] sm:max-w-[300px]">
                    <QRCodeCanvas 
                      value={currentConfig?.config || ''} 
                      size={300}
                      className="rounded-md bg-white p-2 w-full max-w-full h-auto" 
                    />
                  </div>
                </div>
                
                {/* Pagination */}
                <div className="flex items-center justify-center gap-x-4">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={isRTL ? handleNext : handlePrevious}
                    disabled={configs.length <= 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    {currentIndex + 1} / {configs.length}
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={isRTL ? handlePrevious : handleNext}
                    disabled={configs.length <= 1}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>

                <span className="text-center text-sm font-medium">
                  {configName || t('configsQrcodeDialog.unknownConfig', { defaultValue: 'Unknown Config' })}
                </span>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
})

export default ConfigsQRCodeModal
