import { FC, memo } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { QRCodeCanvas } from 'qrcode.react'
import { useTranslation } from 'react-i18next'
import { ScanQrCode } from 'lucide-react'
import useDirDetection from '@/hooks/use-dir-detection'

interface QRCodeModalProps {
  subscribeUrl: string | null
  onCloseModal: () => void
}

const QRCodeModal: FC<QRCodeModalProps> = memo(({ subscribeUrl, onCloseModal }) => {
  const isOpen = subscribeUrl !== null

  const { t } = useTranslation()
  const dir = useDirDetection()

  const subscribeQrLink = String(subscribeUrl).startsWith('/') ? window.location.origin + subscribeUrl : String(subscribeUrl)

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
            <div className="flex w-full items-center justify-center">
              <div className="flex items-center justify-center overflow-hidden max-w-[calc(100vw-80px)] sm:max-w-[300px]">
                <QRCodeCanvas 
                  value={subscribeQrLink} 
                  size={300}
                  className="rounded-md bg-white p-2 w-full max-w-full h-auto" 
                />
              </div>
            </div>
            <span className="text-center">{t('qrcodeDialog.sublink')}</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
})

export default QRCodeModal
