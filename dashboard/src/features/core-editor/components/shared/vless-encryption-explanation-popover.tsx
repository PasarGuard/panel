import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** Info icon + popover copy shared by core-config modal and inbound editor (no label). */
export function VlessEncryptionExplanationPopover() {
  const { t } = useTranslation()
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
          <Info className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-3 sm:w-[340px]" side="top" align="start" sideOffset={5}>
        <div className="space-y-1.5">
          <h4 className="mb-2 text-[11px] font-medium">{t('coreConfigModal.vlessEncryptionInfoTitle')}</h4>
          <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessEncryptionHint')}</p>
          <p className="text-[11px] text-muted-foreground">• {t('coreConfigModal.vlessEncryptionNativeInfo')}</p>
          <p className="text-[11px] text-muted-foreground">• {t('coreConfigModal.vlessEncryptionXorpubInfo')}</p>
          <p className="text-[11px] text-muted-foreground">• {t('coreConfigModal.vlessEncryptionRandomInfo')}</p>
        </div>
      </PopoverContent>
    </Popover>
  )
}
