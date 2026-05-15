import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderButton } from '@/components/ui/loader-button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { VlessEncryptionExplanationPopover } from '@/features/core-editor/components/shared/vless-encryption-explanation-popover'
import {
  createDefaultVlessOptions,
  DEFAULT_VLESS_PADDING,
  generateVlessEncryption,
  VLESS_ENCRYPTION_METHODS,
  VLESS_HANDSHAKE_OPTIONS,
  VLESS_RESUME_OPTIONS,
  type VlessBuilderOptions,
  type VlessEncryptionResult,
} from '@/lib/xray-generation'
import { Info, Key, Shield } from 'lucide-react'
import { useCallback, useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

export type VlessKeyVariant = 'x25519' | 'mlkem768'

function mergeSeedOptions(seed: VlessBuilderOptions | undefined): VlessBuilderOptions {
  const base = createDefaultVlessOptions()
  if (!seed) return base
  return {
    handshakeMethod: seed.handshakeMethod,
    encryptionMethod: seed.encryptionMethod,
    serverTicket: seed.serverTicket,
    clientTicket: seed.clientTicket,
    serverPadding: seed.serverPadding,
    clientPadding: seed.clientPadding,
    includeServerPadding: seed.includeServerPadding,
    includeClientPadding: seed.includeClientPadding,
  }
}

export interface VlessAdvancedGenerationModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Snapshot when the dialog opens (e.g. last run’s options or inbound encryption). */
  seedOptions?: VlessBuilderOptions
  /** Initial authentication variant when the dialog opens. */
  seedVariant?: VlessKeyVariant
  onSuccess: (payload: { result: VlessEncryptionResult; variant: VlessKeyVariant }) => void
}

export function VlessAdvancedGenerationModal({
  open,
  onOpenChange,
  seedOptions,
  seedVariant = 'x25519',
  onSuccess,
}: VlessAdvancedGenerationModalProps) {
  const { t } = useTranslation()
  const uid = useId()
  const serverPadId = `vless-srv-pad-${uid}`
  const clientPadId = `vless-cli-pad-${uid}`

  const [vlessOptions, setVlessOptions] = useState<VlessBuilderOptions>(() => createDefaultVlessOptions())
  const [selectedVariant, setSelectedVariant] = useState<VlessKeyVariant>('x25519')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    if (!open) return
    setVlessOptions(mergeSeedOptions(seedOptions))
    setSelectedVariant(seedVariant)
  }, [open, seedOptions, seedVariant])

  const handleVariantChange = useCallback((value: string) => {
    if (value === 'x25519' || value === 'mlkem768') setSelectedVariant(value)
  }, [])

  const runGenerate = async () => {
    try {
      setIsGenerating(true)
      const result = await generateVlessEncryption(vlessOptions)
      onSuccess({ result, variant: selectedVariant })
      onOpenChange(false)
    } catch {
      toast.error(t('coreConfigModal.vlessEncryptionGenerationFailed'))
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-auto max-w-full sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            <span className="truncate">{t('coreConfigModal.vlessAdvancedSettings', { defaultValue: 'VLESS Advanced Settings' })}</span>
          </DialogTitle>
        </DialogHeader>
        <div className="-mr-4 max-h-[80dvh] space-y-4 overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
          <div className="space-y-2">
            <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.chooseAuthentication')}</Label>
            <Select value={selectedVariant} onValueChange={handleVariantChange}>
              <SelectTrigger className="h-9 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="x25519">
                  <span className="flex items-center gap-2">
                    <Key className="h-3.5 w-3.5" />
                    <span>{t('coreConfigModal.x25519Authentication')}</span>
                  </span>
                </SelectItem>
                <SelectItem value="mlkem768">
                  <span className="flex items-center gap-2">
                    <Shield className="h-3.5 w-3.5" />
                    <span>{t('coreConfigModal.mlkem768Authentication')}</span>
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex flex-1 flex-col justify-end space-y-2">
              <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessHandshakeLabel')}</Label>
              <Select value={vlessOptions.handshakeMethod} onValueChange={value => setVlessOptions(prev => ({ ...prev, handshakeMethod: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VLESS_HANDSHAKE_OPTIONS.map(option => (
                    <SelectItem key={option.value} value={option.value}>
                      <span className="truncate">{option.label}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-1 flex-col justify-end space-y-2">
              <div className="flex items-center gap-1.5">
                <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessEncryptionLabel')}</Label>
                <VlessEncryptionExplanationPopover />
              </div>
              <Select value={vlessOptions.encryptionMethod} onValueChange={value => setVlessOptions(prev => ({ ...prev, encryptionMethod: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VLESS_ENCRYPTION_METHODS.map(method => (
                    <SelectItem key={method.value} value={method.value}>
                      <span className="truncate">{method.label}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessServerTicket')}</Label>
              <Input
                value={vlessOptions.serverTicket}
                placeholder="600s or 100-500s"
                className="h-9"
                onChange={event => setVlessOptions(prev => ({ ...prev, serverTicket: event.target.value }))}
              />
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.vlessClientTicket')}</Label>
              <Select value={vlessOptions.clientTicket} onValueChange={value => setVlessOptions(prev => ({ ...prev, clientTicket: value }))}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VLESS_RESUME_OPTIONS.map(option => (
                    <SelectItem key={option.value} value={option.value}>
                      <span className="truncate">{t(option.translationKey, { defaultValue: option.label })}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-xs font-semibold tracking-wide text-muted-foreground">{t('coreConfigModal.padding', { defaultValue: 'Padding' })}</Label>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id={serverPadId}
                    checked={vlessOptions.includeServerPadding}
                    onCheckedChange={checked => setVlessOptions(prev => ({ ...prev, includeServerPadding: checked === true }))}
                    className="h-4 w-4"
                  />
                  <Label htmlFor={serverPadId} className="cursor-pointer text-xs font-medium">
                    {t('coreConfigModal.vlessServerPaddingToggle')}
                  </Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                        <Info className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[280px] p-3 sm:w-[340px]" side="top" align="start" sideOffset={5}>
                      <div className="space-y-1.5">
                        <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessPaddingHint')}</p>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
                <Input
                  value={vlessOptions.serverPadding}
                  placeholder={DEFAULT_VLESS_PADDING}
                  disabled={!vlessOptions.includeServerPadding}
                  className="h-8 text-xs"
                  onChange={event => setVlessOptions(prev => ({ ...prev, serverPadding: event.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id={clientPadId}
                    checked={vlessOptions.includeClientPadding}
                    onCheckedChange={checked => setVlessOptions(prev => ({ ...prev, includeClientPadding: checked === true }))}
                    className="h-4 w-4"
                  />
                  <Label htmlFor={clientPadId} className="cursor-pointer text-xs font-medium">
                    {t('coreConfigModal.vlessClientPaddingToggle')}
                  </Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button type="button" variant="ghost" size="icon" className="h-4 w-4 p-0 hover:bg-transparent">
                        <Info className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[280px] p-3 sm:w-[340px]" side="top" align="start" sideOffset={5}>
                      <div className="space-y-1.5">
                        <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessPaddingHint')}</p>
                        <p className="text-[11px] text-muted-foreground">{t('coreConfigModal.vlessClientPaddingHint')}</p>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
                <Input
                  value={vlessOptions.clientPadding}
                  placeholder={DEFAULT_VLESS_PADDING}
                  disabled={!vlessOptions.includeClientPadding}
                  className="h-8 text-xs"
                  onChange={event => setVlessOptions(prev => ({ ...prev, clientPadding: event.target.value }))}
                />
              </div>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} size="sm" disabled={isGenerating}>
            {t('close')}
          </Button>
          <LoaderButton type="button" onClick={runGenerate} isLoading={isGenerating} loadingText={t('coreConfigModal.generatingVLESSEncryption')} size="sm">
            {t('coreConfigModal.generate')}
          </LoaderButton>
        </div>
      </DialogContent>
    </Dialog>
  )
}
