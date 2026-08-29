import { useFieldArray, type UseFormReturn, useForm, FormProvider } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { FinalMaskTcpType, FinalMaskUdpType, XrayNoiseSettings } from '@/service/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { FormField, FormItem, FormLabel, FormControl } from '@/components/ui/form'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Plus, Trash2, Copy, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import useDirDetection from '@/hooks/use-dir-detection'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

export interface XrayStreamFinalmaskFieldsProps {
  value: Record<string, any> | undefined
  onChange: (next: Record<string, any> | undefined) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

function pruneQuicParams(q: any): any | undefined {
  if (!q || typeof q !== 'object') return undefined
  const out: any = {}
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === '') continue
    if (k === 'udpHop' && typeof v === 'object' && v !== null) {
      const ports = (v as any).ports
      const interval = (v as any).interval
      if (ports || interval) {
        out[k] = { ports, interval }
      }
      continue
    }
    out[k] = v
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function normalizeFragmentSettings(settings: any): any {
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) return settings
  const out: any = { ...settings }

  if (out.length != null && (!Array.isArray(out.lengths) || out.lengths.length === 0)) {
    out.lengths = [out.length]
  }
  delete out.length

  const legacyDelay = out.delay ?? out.interval
  if (legacyDelay != null && legacyDelay !== '' && (!Array.isArray(out.delays) || out.delays.length === 0)) {
    out.delays = [legacyDelay]
  }
  delete out.delay
  delete out.interval

  return out
}

function normalizeFinalmaskLayers(raw: any): any {
  if (!raw || typeof raw !== 'object') return raw
  const out: any = { ...raw }

  if (Array.isArray(raw.tcp)) {
    out.tcp = raw.tcp.map((layer: any) => {
      if (!layer || typeof layer !== 'object' || layer.type !== 'fragment') return layer
      return { ...layer, settings: normalizeFragmentSettings(layer.settings) }
    })
  }

  return out
}

function pruneFinalmask(raw: any): any | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const normalized = normalizeFinalmaskLayers(raw)
  const out: any = {}

  if (Array.isArray(normalized.tcp) && normalized.tcp.length > 0) {
    out.tcp = normalized.tcp
  }

  if (Array.isArray(normalized.udp) && normalized.udp.length > 0) {
    out.udp = normalized.udp
  }

  if (normalized.quicParams && typeof normalized.quicParams === 'object') {
    const q = pruneQuicParams(normalized.quicParams)
    if (q) out.quicParams = q
  }

  return Object.keys(out).length > 0 ? out : undefined
}

function hasFinalmaskContent(value: Record<string, any> | undefined): boolean {
  return Boolean(
    value &&
    ((Array.isArray(value.tcp) && value.tcp.length > 0) ||
      (Array.isArray(value.udp) && value.udp.length > 0) ||
      (value.quicParams && typeof value.quicParams === 'object' && Object.keys(value.quicParams).length > 0)),
  )
}

export function XrayStreamFinalmaskFields({ value, onChange }: XrayStreamFinalmaskFieldsProps) {
  const dir = useDirDetection()

  const form = useForm<any>({
    defaultValues: value || {
      tcp: [],
      udp: [],
      quicParams: {},
    },
  })

  // Sync external value changes into form state without disrupting active typing focus
  useEffect(() => {
    const currentFormValues = form.getValues()
    const nextPruned = pruneFinalmask(currentFormValues)
    const currentPruned = pruneFinalmask(value)
    if (JSON.stringify(currentPruned) !== JSON.stringify(nextPruned)) {
      form.reset(
        value || {
          tcp: [],
          udp: [],
          quicParams: {},
        },
      )
    }
  }, [value, form])

  const watched = form.watch()
  useEffect(() => {
    const nextPruned = pruneFinalmask(watched)
    const currentPruned = pruneFinalmask(value)
    if (JSON.stringify(nextPruned) !== JSON.stringify(currentPruned)) {
      onChange(nextPruned)
    }
  }, [watched, onChange, value])

  return (
    <FormProvider {...form}>
      <Tabs dir={dir} defaultValue="tcp" className="w-full">
        <TabsList className="mb-4 grid w-full grid-cols-3">
          <TabsTrigger value="tcp">TCP</TabsTrigger>
          <TabsTrigger value="udp">UDP</TabsTrigger>
          <TabsTrigger value="quic">QUIC</TabsTrigger>
        </TabsList>

        <TabsContent dir={dir} value="tcp">
          <TcpLayersForm form={form} />
        </TabsContent>

        <TabsContent dir={dir} value="udp">
          <UdpLayersForm form={form} />
        </TabsContent>

        <TabsContent dir={dir} value="quic">
          <QuicParamsForm form={form} />
        </TabsContent>
      </Tabs>
    </FormProvider>
  )
}

// ==========================================
// TCP Layers component
// ==========================================
function TcpLayersForm({ form }: { form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'tcp',
  })

  const handleAddLayer = () => {
    append({
      type: 'fragment',
      settings: {
        packets: 'tlshello',
        lengths: [],
        delays: [],
        maxSplit: '',
      },
    })
  }

  const handleTypeChange = (index: number, newType: FinalMaskTcpType) => {
    form.setValue(`tcp.${index}.type`, newType)
    if (newType === 'fragment') {
      form.setValue(`tcp.${index}.settings`, {
        packets: 'tlshello',
        lengths: [],
        delays: [],
        maxSplit: '',
      })
    } else if (newType === 'sudoku') {
      form.setValue(`tcp.${index}.settings`, {
        password: '',
        ascii: '',
        customTable: '',
        customTables: [],
        paddingMin: undefined,
        paddingMax: undefined,
      })
    } else if (newType === 'header-custom') {
      form.setValue(`tcp.${index}.settings`, {
        clients: [],
        servers: [],
        errors: [],
      })
    } else if (newType === 'xmc') {
      form.setValue(`tcp.${index}.settings`, {
        hostname: '',
        usernames: [],
        password: '',
      })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-muted-foreground text-xs font-semibold">{t('hostsDialog.finalmask.tcpLayers', { defaultValue: 'TCP Layers' })}</h4>
        <Button type="button" variant="outline" size="sm" onClick={handleAddLayer}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          {t('hostsDialog.finalmask.addTcpLayer', { defaultValue: 'Add TCP Layer' })}
        </Button>
      </div>

      <div className="space-y-4">
        {fields.map((field, index) => {
          const type = form.watch(`tcp.${index}.type`)
          return (
            <div key={field.id} className="bg-muted/5 relative space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-muted-foreground w-6 text-xs font-semibold">#{index + 1}</span>
                  <FormField
                    control={form.control}
                    name={`tcp.${index}.type`}
                    render={({ field: selectField }) => (
                      <FormItem className="w-48">
                        <Select onValueChange={val => handleTypeChange(index, val as FinalMaskTcpType)} value={selectField.value || ''}>
                          <FormControl>
                            <SelectTrigger className="h-8">
                              <SelectValue placeholder={t('hostsDialog.finalmask.selectType')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="fragment">fragment</SelectItem>
                            <SelectItem value="sudoku">sudoku</SelectItem>
                            <SelectItem value="header-custom">header-custom</SelectItem>
                            <SelectItem value="xmc">xmc</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )}
                  />
                </div>
                <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8" onClick={() => remove(index)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              {type === 'fragment' && <FragmentSettingsForm prefix={`tcp.${index}.settings`} form={form} />}

              {type === 'sudoku' && <SudokuSettingsForm prefix={`tcp.${index}.settings`} form={form} />}

              {type === 'header-custom' && (
                <div className="bg-background space-y-4 rounded-md border p-3">
                  <JsonArrayField form={form} name={`tcp.${index}.settings.clients`} label={t('hostsDialog.finalmask.clientsJson')} />
                  <JsonArrayField form={form} name={`tcp.${index}.settings.servers`} label={t('hostsDialog.finalmask.serversJson')} />
                  <JsonArrayField form={form} name={`tcp.${index}.settings.errors`} label={t('hostsDialog.finalmask.errorsJson')} />
                </div>
              )}

              {type === 'xmc' && <XmcSettingsForm prefix={`tcp.${index}.settings`} form={form} />}
            </div>
          )
        })}

        {fields.length === 0 && (
          <div className="text-muted-foreground bg-muted/10 rounded-lg border border-dashed py-8 text-center text-xs">
            {t('hostsDialog.finalmask.noTcpLayers', { defaultValue: 'No TCP layers configured' })}
          </div>
        )}
      </div>
    </div>
  )
}

// ==========================================
// UDP Layers component
// ==========================================
function UdpLayersForm({ form }: { form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'udp',
  })

  const handleAddLayer = () => {
    append({
      type: 'mkcp-legacy',
      settings: {
        header: 'wechat',
        value: '',
      },
    })
  }

  const handleTypeChange = (index: number, newType: FinalMaskUdpType) => {
    form.setValue(`udp.${index}.type`, newType)
    if (newType === 'mkcp-legacy') {
      form.setValue(`udp.${index}.settings`, { header: 'wechat', value: '' })
    } else if (newType === 'realm') {
      form.setValue(`udp.${index}.settings`, { url: '', stunServers: [], tlsConfig: undefined })
    } else if (newType === 'xdns') {
      form.setValue(`udp.${index}.settings`, { domains: [], resolvers: [] })
    } else if (newType === 'xicmp') {
      form.setValue(`udp.${index}.settings`, { dgram: false, ips: [] })
    } else if (newType === 'header-dns') {
      form.setValue(`udp.${index}.settings`, { domain: '' })
    } else if (['header-dtls', 'header-srtp', 'header-utp', 'header-wechat', 'header-wireguard', 'mkcp-original', 'mkcp-aes128gcm'].includes(newType)) {
      form.setValue(`udp.${index}.settings`, { password: '' })
    } else if (newType === 'salamander') {
      form.setValue(`udp.${index}.settings`, { password: '', packetSize: '' })
    } else if (newType === 'noise') {
      form.setValue(`udp.${index}.settings`, { reset: undefined, noise: [] })
    } else if (newType === 'sudoku') {
      form.setValue(`udp.${index}.settings`, {
        password: '',
        ascii: '',
        customTable: '',
        customTables: [],
        paddingMin: undefined,
        paddingMax: undefined,
      })
    } else if (newType === 'header-custom') {
      form.setValue(`udp.${index}.settings`, { client: [], server: [] })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-muted-foreground text-xs font-semibold">{t('hostsDialog.finalmask.udpLayers', { defaultValue: 'UDP Layers' })}</h4>
        <Button type="button" variant="outline" size="sm" onClick={handleAddLayer}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          {t('hostsDialog.finalmask.addUdpLayer', { defaultValue: 'Add UDP Layer' })}
        </Button>
      </div>

      <div className="space-y-4">
        {fields.map((field, index) => {
          const type = form.watch(`udp.${index}.type`)
          return (
            <div key={field.id} className="bg-muted/5 relative space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-muted-foreground w-6 text-xs font-semibold">#{index + 1}</span>
                  <FormField
                    control={form.control}
                    name={`udp.${index}.type`}
                    render={({ field: selectField }) => (
                      <FormItem className="w-56">
                        <Select onValueChange={val => handleTypeChange(index, val as FinalMaskUdpType)} value={selectField.value || ''}>
                          <FormControl>
                            <SelectTrigger className="h-8">
                              <SelectValue placeholder={t('hostsDialog.finalmask.selectType')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="mkcp-legacy">mkcp-legacy</SelectItem>
                            <SelectItem value="realm">realm</SelectItem>
                            <SelectItem value="xdns">xdns</SelectItem>
                            <SelectItem value="xicmp">xicmp</SelectItem>
                            <SelectItem value="salamander">salamander</SelectItem>
                            <SelectItem value="noise">noise</SelectItem>
                            <SelectItem value="sudoku">sudoku</SelectItem>
                            <SelectItem value="header-custom">header-custom</SelectItem>
                            <SelectItem value="header-dns">{t('hostsDialog.finalmask.legacyType', { type: 'header-dns' })}</SelectItem>
                            <SelectItem value="header-dtls">{t('hostsDialog.finalmask.legacyType', { type: 'header-dtls' })}</SelectItem>
                            <SelectItem value="header-srtp">{t('hostsDialog.finalmask.legacyType', { type: 'header-srtp' })}</SelectItem>
                            <SelectItem value="header-utp">{t('hostsDialog.finalmask.legacyType', { type: 'header-utp' })}</SelectItem>
                            <SelectItem value="header-wechat">{t('hostsDialog.finalmask.legacyType', { type: 'header-wechat' })}</SelectItem>
                            <SelectItem value="header-wireguard">{t('hostsDialog.finalmask.legacyType', { type: 'header-wireguard' })}</SelectItem>
                            <SelectItem value="mkcp-original">{t('hostsDialog.finalmask.legacyType', { type: 'mkcp-original' })}</SelectItem>
                            <SelectItem value="mkcp-aes128gcm">{t('hostsDialog.finalmask.legacyType', { type: 'mkcp-aes128gcm' })}</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )}
                  />
                </div>
                <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-8 w-8" onClick={() => remove(index)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              {type === 'mkcp-legacy' && (
                <div className="bg-background grid grid-cols-2 gap-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.header`}
                    render={({ field: selectField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.header')}</FormLabel>
                        <Select onValueChange={selectField.onChange} value={selectField.value || 'wechat'}>
                          <FormControl>
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue placeholder={t('hostsDialog.finalmask.header')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent side="top">
                            <SelectItem value="dns">dns</SelectItem>
                            <SelectItem value="dtls">dtls</SelectItem>
                            <SelectItem value="srtp">srtp</SelectItem>
                            <SelectItem value="utp">utp</SelectItem>
                            <SelectItem value="wechat">wechat</SelectItem>
                            <SelectItem value="wireguard">wireguard</SelectItem>
                            <SelectItem value="">{t('hostsDialog.finalmask.headerNone')}</SelectItem>
                          </SelectContent>
                        </Select>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.value`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.valueDomainPassword')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('hostsDialog.finalmask.valueDomainPasswordPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'realm' && (
                <div className="bg-background space-y-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.url`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.realmUrl')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('hostsDialog.finalmask.realmUrlPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.stunServers`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.stunServers')}</FormLabel>
                        <FormControl>
                          <StringArrayPopoverInput
                            value={Array.isArray(inputField.value) ? inputField.value : []}
                            onChange={(next: string[]) => inputField.onChange(next)}
                            placeholder={t('hostsDialog.finalmask.stunServersPlaceholder')}
                            addPlaceholder={t('arrayInput.addPlaceholder')}
                            addButtonLabel={t('arrayInput.addButton')}
                            itemsLabel={t('arrayInput.items')}
                            emptyMessage={t('arrayInput.noItems')}
                            duplicateErrorMessage={t('arrayInput.duplicateError')}
                            clickToEditTitle={t('arrayInput.clickToEdit')}
                            editItemTitle={t('arrayInput.editItem')}
                            removeItemTitle={t('arrayInput.removeItem')}
                            saveEditTitle={t('arrayInput.saveEdit')}
                            cancelEditTitle={t('arrayInput.cancelEdit')}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <JsonObjectField form={form} name={`udp.${index}.settings.tlsConfig`} label={t('hostsDialog.finalmask.tlsConfig')} />
                </div>
              )}

              {type === 'xdns' && (
                <div className="bg-background grid grid-cols-2 gap-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.domains`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.serverDomains')}</FormLabel>
                        <FormControl>
                          <StringArrayPopoverInput
                            value={Array.isArray(inputField.value) ? inputField.value : []}
                            onChange={(next: string[]) => inputField.onChange(next)}
                            placeholder={t('hostsDialog.finalmask.serverDomainsPlaceholder')}
                            addPlaceholder={t('arrayInput.addPlaceholder')}
                            addButtonLabel={t('arrayInput.addButton')}
                            itemsLabel={t('arrayInput.items')}
                            emptyMessage={t('arrayInput.noItems')}
                            duplicateErrorMessage={t('arrayInput.duplicateError')}
                            clickToEditTitle={t('arrayInput.clickToEdit')}
                            editItemTitle={t('arrayInput.editItem')}
                            removeItemTitle={t('arrayInput.removeItem')}
                            saveEditTitle={t('arrayInput.saveEdit')}
                            cancelEditTitle={t('arrayInput.cancelEdit')}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.resolvers`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.clientResolvers')}</FormLabel>
                        <FormControl>
                          <StringArrayPopoverInput
                            value={Array.isArray(inputField.value) ? inputField.value : []}
                            onChange={(next: string[]) => inputField.onChange(next)}
                            placeholder={t('hostsDialog.finalmask.clientResolversPlaceholder')}
                            addPlaceholder={t('arrayInput.addPlaceholder')}
                            addButtonLabel={t('arrayInput.addButton')}
                            itemsLabel={t('arrayInput.items')}
                            emptyMessage={t('arrayInput.noItems')}
                            duplicateErrorMessage={t('arrayInput.duplicateError')}
                            clickToEditTitle={t('arrayInput.clickToEdit')}
                            editItemTitle={t('arrayInput.editItem')}
                            removeItemTitle={t('arrayInput.removeItem')}
                            saveEditTitle={t('arrayInput.saveEdit')}
                            cancelEditTitle={t('arrayInput.cancelEdit')}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'header-dns' && (
                <div className="bg-background rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.domain`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.domain')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('hostsDialog.finalmask.domainPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {['header-dtls', 'header-srtp', 'header-utp', 'header-wechat', 'header-wireguard', 'mkcp-original', 'mkcp-aes128gcm'].includes(type) && (
                <div className="bg-background rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.password`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.password')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('hostsDialog.finalmask.password')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'salamander' && (
                <div className="bg-background grid grid-cols-2 gap-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.password`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.password')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('hostsDialog.finalmask.password')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.packetSize`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.packetSize')}</FormLabel>
                        <FormControl>
                          <Input placeholder={t('hostsDialog.finalmask.packetSizePlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'sudoku' && <SudokuSettingsForm prefix={`udp.${index}.settings`} form={form} />}

              {type === 'xicmp' && (
                <div className="bg-background space-y-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.dgram`}
                    render={({ field: inputField }) => (
                      <FormItem dir="ltr" className="flex min-h-8 items-center justify-between gap-3 rounded-md border px-3 py-1">
                        <FormLabel className="min-w-0 cursor-pointer truncate text-left text-xs font-normal">{t('hostsDialog.finalmask.dgramMode')}</FormLabel>
                        <FormControl>
                          <Switch checked={!!inputField.value} onCheckedChange={inputField.onChange} className="scale-75" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.ips`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.ips')}</FormLabel>
                        <FormControl>
                          <StringArrayPopoverInput
                            value={Array.isArray(inputField.value) ? inputField.value : []}
                            onChange={(next: string[]) => inputField.onChange(next)}
                            placeholder={t('hostsDialog.finalmask.ipsPlaceholder')}
                            addPlaceholder={t('arrayInput.addPlaceholder')}
                            addButtonLabel={t('arrayInput.addButton')}
                            itemsLabel={t('arrayInput.items')}
                            emptyMessage={t('arrayInput.noItems')}
                            duplicateErrorMessage={t('arrayInput.duplicateError')}
                            clickToEditTitle={t('arrayInput.clickToEdit')}
                            editItemTitle={t('arrayInput.editItem')}
                            removeItemTitle={t('arrayInput.removeItem')}
                            saveEditTitle={t('arrayInput.saveEdit')}
                            cancelEditTitle={t('arrayInput.cancelEdit')}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'noise' && (
                <div className="bg-background space-y-4 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`udp.${index}.settings.reset`}
                    render={({ field: inputField }) => (
                      <FormItem className="w-56">
                        <FormLabel className="text-xs">{t('hostsDialog.finalmask.reset')}</FormLabel>
                        <FormControl>
                          <Input
                            placeholder={t('hostsDialog.finalmask.resetPlaceholder')}
                            {...inputField}
                            value={inputField.value ?? ''}
                            onChange={e => inputField.onChange(e.target.value === '' ? undefined : e.target.value)}
                            className="h-8 text-xs"
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <XrayNoiseSettingsList form={form} name={`udp.${index}.settings.noise`} label={t('hostsDialog.finalmask.noiseSettings')} />
                </div>
              )}

              {type === 'header-custom' && (
                <div className="bg-background space-y-4 rounded-md border p-3">
                  <XrayNoiseSettingsList form={form} name={`udp.${index}.settings.client`} label={t('hostsDialog.finalmask.clientSettings')} />
                  <XrayNoiseSettingsList form={form} name={`udp.${index}.settings.server`} label={t('hostsDialog.finalmask.serverSettings')} />
                </div>
              )}
            </div>
          )
        })}

        {fields.length === 0 && (
          <div className="text-muted-foreground bg-muted/10 rounded-lg border border-dashed py-8 text-center text-xs">
            {t('hostsDialog.finalmask.noUdpLayers', { defaultValue: 'No UDP layers configured' })}
          </div>
        )}
      </div>
    </div>
  )
}

// ==========================================
// QUIC Params component
// ==========================================
function QuicParamsForm({ form }: { form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name="quicParams.congestion"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.congestion')}</FormLabel>
              <Select onValueChange={field.onChange} value={field.value || ''}>
                <FormControl>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder={t('hostsDialog.finalmask.selectCongestion')} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent side="top">
                  <SelectItem value="reno">reno</SelectItem>
                  <SelectItem value="bbr">bbr</SelectItem>
                  <SelectItem value="brutal">brutal</SelectItem>
                  <SelectItem value="force-brutal">force-brutal</SelectItem>
                </SelectContent>
              </Select>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="quicParams.bbrProfile"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.bbrProfile')}</FormLabel>
              <Select onValueChange={val => field.onChange(val === '__none__' ? undefined : val)} value={field.value || '__none__'}>
                <FormControl>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder={t('hostsDialog.finalmask.selectBbrProfile')} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent side="top">
                  <SelectItem value="__none__">{t('hostsDialog.finalmask.bbrDefault')}</SelectItem>
                  <SelectItem value="conservative">conservative</SelectItem>
                  <SelectItem value="standard">standard</SelectItem>
                  <SelectItem value="aggressive">aggressive</SelectItem>
                </SelectContent>
              </Select>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="quicParams.debug"
          render={({ field }) => (
            <FormItem dir="ltr" className="mt-6 flex min-h-9 items-center justify-between gap-3 rounded-md border px-3 py-2">
              <FormLabel className="min-w-0 cursor-pointer truncate text-left text-xs font-normal">{t('hostsDialog.finalmask.debug')}</FormLabel>
              <FormControl>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} className="scale-75" />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="quicParams.brutalUp"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.brutalUp')}</FormLabel>
              <FormControl>
                <Input placeholder={t('hostsDialog.finalmask.mbpsPlaceholder')} {...field} value={field.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="quicParams.brutalDown"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.brutalDown')}</FormLabel>
              <FormControl>
                <Input placeholder={t('hostsDialog.finalmask.mbpsPlaceholder')} {...field} value={field.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />
      </div>

      <div className="border-t pt-3">
        <h5 className="mb-2 text-xs font-semibold">{t('hostsDialog.finalmask.udpHop')}</h5>
        <div className="bg-muted/5 grid grid-cols-2 gap-3 rounded-md border p-3">
          <FormField
            control={form.control}
            name="quicParams.udpHop.ports"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.ports')}</FormLabel>
                <FormControl>
                  <Input placeholder={t('hostsDialog.finalmask.portsPlaceholder')} {...field} value={field.value || ''} className="h-8 text-xs" />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.udpHop.interval"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.interval')}</FormLabel>
                <FormControl>
                  <Input placeholder={t('hostsDialog.finalmask.intervalPlaceholder')} {...field} value={field.value || ''} className="h-8 text-xs" />
                </FormControl>
              </FormItem>
            )}
          />
        </div>
      </div>

      <div className="border-t pt-3">
        <h5 className="mb-2 text-xs font-semibold">{t('hostsDialog.finalmask.windowsAndStream')}</h5>
        <p className="text-muted-foreground mb-2 text-[11px] leading-relaxed">{t('hostsDialog.finalmask.windowsAndStreamHint')}</p>
        <div className="grid grid-cols-2 gap-3">
          <FormField
            control={form.control}
            name="quicParams.initStreamReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.initStreamRxWindow')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder={t('hostsDialog.finalmask.streamWindowPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.maxStreamReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.maxStreamRxWindow')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder={t('hostsDialog.finalmask.streamWindowPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.initConnectionReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.initConnectionRxWindow')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder={t('hostsDialog.finalmask.connectionWindowPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.maxConnectionReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.maxConnectionRxWindow')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder={t('hostsDialog.finalmask.connectionWindowPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.maxIncomingStreams"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.maxIncomingStreams')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={8}
                    placeholder={t('hostsDialog.finalmask.streamsCountPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.maxIdleTimeout"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.maxIdleTimeout')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={4}
                    max={120}
                    placeholder={t('hostsDialog.finalmask.maxIdleTimeoutPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.keepAlivePeriod"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">{t('hostsDialog.finalmask.keepAlivePeriod')}</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={2}
                    max={60}
                    placeholder={t('hostsDialog.finalmask.keepAlivePeriodPlaceholder')}
                    {...field}
                    value={field.value ?? ''}
                    onChange={e => field.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-8 text-xs"
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="quicParams.disablePathMTUDiscovery"
            render={({ field }) => (
              <FormItem dir="ltr" className="mt-6 flex min-h-9 items-center justify-between gap-3 rounded-md border px-3 py-2">
                <FormLabel className="min-w-0 cursor-pointer truncate text-left text-xs font-normal">{t('hostsDialog.finalmask.disablePmtuDiscovery')}</FormLabel>
                <FormControl>
                  <Switch checked={!!field.value} onCheckedChange={field.onChange} className="scale-75" />
                </FormControl>
              </FormItem>
            )}
          />
        </div>
      </div>
    </div>
  )
}

// ==========================================
// Fragment Settings Form (FinalMask TCP)
// ==========================================
function FragmentSettingsForm({ prefix, form }: { prefix: string; form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  return (
    <div className="bg-background space-y-3 rounded-md border p-3">
      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name={`${prefix}.packets`}
          render={({ field: inputField }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.packets')}</FormLabel>
              <FormControl>
                <Input placeholder={t('hostsDialog.finalmask.packetsPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name={`${prefix}.maxSplit`}
          render={({ field: inputField }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.maxSplit')}</FormLabel>
              <FormControl>
                <Input placeholder={t('hostsDialog.finalmask.maxSplitPlaceholder')} {...inputField} value={inputField.value ?? ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />
      </div>
      <FormField
        control={form.control}
        name={`${prefix}.lengths`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.lengths')}</FormLabel>
            <FormControl>
              <StringArrayPopoverInput
                value={Array.isArray(inputField.value) ? inputField.value.map(String) : []}
                onChange={(next: string[]) => inputField.onChange(next)}
                placeholder={t('hostsDialog.finalmask.lengthsPlaceholder')}
                addPlaceholder={t('arrayInput.addPlaceholder')}
                addButtonLabel={t('arrayInput.addButton')}
                itemsLabel={t('arrayInput.items')}
                emptyMessage={t('arrayInput.noItems')}
                duplicateErrorMessage={t('arrayInput.duplicateError')}
                clickToEditTitle={t('arrayInput.clickToEdit')}
                editItemTitle={t('arrayInput.editItem')}
                removeItemTitle={t('arrayInput.removeItem')}
                saveEditTitle={t('arrayInput.saveEdit')}
                cancelEditTitle={t('arrayInput.cancelEdit')}
              />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.delays`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.delays')}</FormLabel>
            <FormControl>
              <StringArrayPopoverInput
                value={Array.isArray(inputField.value) ? inputField.value.map(String) : []}
                onChange={(next: string[]) => inputField.onChange(next)}
                placeholder={t('hostsDialog.finalmask.delaysPlaceholder')}
                addPlaceholder={t('arrayInput.addPlaceholder')}
                addButtonLabel={t('arrayInput.addButton')}
                itemsLabel={t('arrayInput.items')}
                emptyMessage={t('arrayInput.noItems')}
                duplicateErrorMessage={t('arrayInput.duplicateError')}
                clickToEditTitle={t('arrayInput.clickToEdit')}
                editItemTitle={t('arrayInput.editItem')}
                removeItemTitle={t('arrayInput.removeItem')}
                saveEditTitle={t('arrayInput.saveEdit')}
                cancelEditTitle={t('arrayInput.cancelEdit')}
              />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}

// Sudoku Settings Form
// ==========================================
function SudokuSettingsForm({ prefix, form }: { prefix: string; form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  return (
    <div className="bg-background grid grid-cols-2 gap-3 rounded-md border p-3">
      <FormField
        control={form.control}
        name={`${prefix}.password`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.password')}</FormLabel>
            <FormControl>
              <Input placeholder={t('hostsDialog.finalmask.password')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.ascii`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.ascii')}</FormLabel>
            <FormControl>
              <Input placeholder={t('hostsDialog.finalmask.asciiPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.customTable`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.customTable')}</FormLabel>
            <FormControl>
              <Input placeholder={t('hostsDialog.finalmask.customTable')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.customTables`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.customTables')}</FormLabel>
            <FormControl>
              <StringArrayPopoverInput
                value={Array.isArray(inputField.value) ? inputField.value : []}
                onChange={(next: string[]) => inputField.onChange(next)}
                placeholder={t('hostsDialog.finalmask.customTablesPlaceholder')}
                addPlaceholder={t('arrayInput.addPlaceholder')}
                addButtonLabel={t('arrayInput.addButton')}
                itemsLabel={t('arrayInput.items')}
                emptyMessage={t('arrayInput.noItems')}
                duplicateErrorMessage={t('arrayInput.duplicateError')}
                clickToEditTitle={t('arrayInput.clickToEdit')}
                editItemTitle={t('arrayInput.editItem')}
                removeItemTitle={t('arrayInput.removeItem')}
                saveEditTitle={t('arrayInput.saveEdit')}
                cancelEditTitle={t('arrayInput.cancelEdit')}
              />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.paddingMin`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.paddingMin')}</FormLabel>
            <FormControl>
              <Input
                type="number"
                placeholder="0"
                {...inputField}
                value={inputField.value ?? ''}
                onChange={e => inputField.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                className="h-8 text-xs"
              />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.paddingMax`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.paddingMax')}</FormLabel>
            <FormControl>
              <Input
                type="number"
                placeholder="0"
                {...inputField}
                value={inputField.value ?? ''}
                onChange={e => inputField.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                className="h-8 text-xs"
              />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}

function XmcSettingsForm({ prefix, form }: { prefix: string; form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-3 bg-background p-3 rounded-md border">
      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name={`${prefix}.hostname`}
          render={({ field: inputField }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.hostname')}</FormLabel>
              <FormControl>
                <Input placeholder={t('hostsDialog.finalmask.hostname')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name={`${prefix}.password`}
          render={({ field: inputField }) => (
            <FormItem>
              <FormLabel className="text-xs">{t('hostsDialog.finalmask.password')}</FormLabel>
              <FormControl>
                <Input placeholder={t('hostsDialog.finalmask.password')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />
      </div>
      <JsonArrayField form={form} name={`${prefix}.profiles`} label={t('hostsDialog.finalmask.profilesJson')} />
      <FormField
        control={form.control}
        name={`${prefix}.usernames`}
        render={({ field: inputField }) => (
          <FormItem className="col-span-2">
            <FormLabel className="text-xs">{t('hostsDialog.finalmask.legacyUsernames')}</FormLabel>
            <FormControl>
              <StringArrayPopoverInput
                value={Array.isArray(inputField.value) ? inputField.value : []}
                onChange={(next: string[]) => inputField.onChange(next)}
                placeholder={t('hostsDialog.finalmask.usernamesPlaceholder')}
                addPlaceholder={t('arrayInput.addPlaceholder')}
                addButtonLabel={t('arrayInput.addButton')}
                itemsLabel={t('arrayInput.items')}
                emptyMessage={t('arrayInput.noItems')}
                duplicateErrorMessage={t('arrayInput.duplicateError')}
                clickToEditTitle={t('arrayInput.clickToEdit')}
                editItemTitle={t('arrayInput.editItem')}
                removeItemTitle={t('arrayInput.removeItem')}
                saveEditTitle={t('arrayInput.saveEdit')}
                cancelEditTitle={t('arrayInput.cancelEdit')}
              />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}

interface JsonArrayFieldProps {
  form: UseFormReturn<any>
  name: string
  label: string
}

function JsonArrayField({ form, name, label }: JsonArrayFieldProps) {
  return <FormField control={form.control} name={name} render={({ field }) => <JsonArrayEditor label={label} value={field.value} onChange={field.onChange} />} />
}

function JsonObjectField({ form, name, label }: JsonArrayFieldProps) {
  return <FormField control={form.control} name={name} render={({ field }) => <JsonObjectEditor label={label} value={field.value} onChange={field.onChange} />} />
}

function JsonObjectEditor({ label, value, onChange }: { label: string; value: unknown; onChange: (value: Record<string, unknown> | undefined) => void }) {
  const { t } = useTranslation()
  const serializedValue = value && typeof value === 'object' && !Array.isArray(value) ? JSON.stringify(value, null, 2) : ''
  const [text, setText] = useState(serializedValue)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const next = value && typeof value === 'object' && !Array.isArray(value) ? JSON.stringify(value, null, 2) : ''
    setText(next)
    setError(null)
  }, [value])

  return (
    <div className="space-y-2">
      <FormLabel className="text-xs">{label}</FormLabel>
      <CodeEditorPanel
        language="json"
        value={text}
        onChange={next => {
          setText(next)
          const trimmed = next.trim()
          if (!trimmed) {
            setError(null)
            onChange(undefined)
            return
          }
          try {
            const parsed = JSON.parse(trimmed)
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
              setError(t('hostsDialog.finalmask.mustBeJsonObject'))
              return
            }
            setError(null)
            onChange(parsed as Record<string, unknown>)
          } catch {
            setError(t('hostsDialog.finalmask.invalidJsonObject'))
          }
        }}
        embeddedContainerClassName="h-32"
      />
      {error && <p className="text-destructive text-[11px]">{error}</p>}
    </div>
  )
}

function JsonArrayEditor({ label, value, onChange }: { label: string; value: unknown; onChange: (value: XrayNoiseSettings[][]) => void }) {
  const serializedValue = JSON.stringify(Array.isArray(value) ? value : [], null, 2)
  const [text, setText] = useState(serializedValue)

  useEffect(() => {
    setText(serializedValue)
  }, [serializedValue])

  return (
    <FormItem>
      <FormLabel className="text-xs">{label}</FormLabel>
      <FormControl>
        <CodeEditorPanel
          value={text}
          language="json"
          onChange={val => {
            setText(val)
            try {
              const parsed = JSON.parse(val)
              if (Array.isArray(parsed)) {
                onChange(parsed as XrayNoiseSettings[][])
              }
            } catch {
              return
            }
          }}
          embeddedContainerClassName="h-32"
        />
      </FormControl>
    </FormItem>
  )
}

interface XrayNoiseSettingsListProps {
  form: UseFormReturn<any>
  name: string
  label: string
}

function XrayNoiseSettingsList({ form, name, label }: XrayNoiseSettingsListProps) {
  const { t } = useTranslation()
  const { fields, append, remove, insert } = useFieldArray({
    control: form.control,
    name,
  })

  const handleDuplicate = (index: number) => {
    const item = form.getValues(`${name}.${index}`)
    if (item) {
      insert(index + 1, { ...item })
    }
  }

  return (
    <div className="bg-muted/10 space-y-3 rounded-md border p-3">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-xs font-semibold">{label}</span>
        <Button type="button" variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => append({ type: 'array', packet: '', delay: '', rand: '', randRange: '0-255' })}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          {t('hostsDialog.noise.addNoise', { defaultValue: 'Add' })}
        </Button>
      </div>

      <div className="space-y-2">
        {fields.map((field, index) => (
          <div key={field.id} className="bg-background space-y-2 rounded-md border p-2">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground w-5 shrink-0 text-center text-xs">{index + 1}</span>
              <FormField
                control={form.control}
                name={`${name}.${index}.type`}
                render={({ field: inputField }) => (
                  <FormItem className="w-[100px] shrink-0">
                    <Select onValueChange={inputField.onChange} value={inputField.value || 'array'}>
                      <FormControl>
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue placeholder={t('hostsDialog.noise.type')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent side="top">
                        <SelectItem value="array">array</SelectItem>
                        <SelectItem value="str">str</SelectItem>
                        <SelectItem value="hex">hex</SelectItem>
                        <SelectItem value="base64">base64</SelectItem>
                        <SelectItem value="rand">rand</SelectItem>
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              <div className="ml-auto flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="hover:bg-muted h-7 w-7 transition-colors"
                  onClick={() => handleDuplicate(index)}
                  title={t('hostsDialog.noise.duplicateNoise')}
                >
                  <Copy className="h-3.5 w-3.5" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-7 w-7" onClick={() => remove(index)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2 pl-7">
              <FormField
                control={form.control}
                name={`${name}.${index}.packet`}
                render={({ field: inputField }) => (
                  <FormItem>
                    <FormControl>
                      <Input placeholder={t('hostsDialog.noise.packet')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`${name}.${index}.delay`}
                render={({ field: inputField }) => (
                  <FormItem>
                    <FormControl>
                      <Input placeholder={t('hostsDialog.noise.delayPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`${name}.${index}.rand`}
                render={({ field: inputField }) => (
                  <FormItem>
                    <FormControl>
                      <Input placeholder={t('hostsDialog.finalmask.noiseRandPlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`${name}.${index}.randRange`}
                render={({ field: inputField }) => (
                  <FormItem>
                    <FormControl>
                      <Input placeholder={t('hostsDialog.finalmask.noiseRandRangePlaceholder')} {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
          </div>
        ))}
        {fields.length === 0 && <div className="text-muted-foreground py-4 text-center text-xs">{t('hostsDialog.noise.noNoiseSettings', { defaultValue: 'No noise items' })}</div>}
      </div>
    </div>
  )
}

export interface XrayStreamFinalmaskAccordionProps {
  accordionItemClassName: string
  value: Record<string, any> | undefined
  onChange: (next: Record<string, any> | undefined) => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

export function XrayStreamFinalmaskInboundAccordion({ accordionItemClassName, value, onChange, t }: XrayStreamFinalmaskAccordionProps) {
  const enabled = value !== undefined && value !== null
  const configured = hasFinalmaskContent(value)

  return (
    <Accordion type="single" collapsible className="mt-0! sm:col-span-2">
      <AccordionItem value="finalmask" className={accordionItemClassName}>
        <AccordionTrigger>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="text-muted-foreground h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>{t('hostsDialog.finalmask.title', { defaultValue: 'FinalMask Settings' })}</span>
            {configured && <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px] font-medium">{t('enabled', { defaultValue: 'on' })}</span>}
          </div>
        </AccordionTrigger>
        <AccordionContent className="space-y-4 pt-0 pb-3">
          <div className="flex items-center justify-between gap-3 rounded-md border p-3">
            <div className="min-w-0 space-y-1">
              <p className="text-xs font-medium">{t('enabled', { defaultValue: 'Enabled' })}</p>
            </div>
            <Switch
              checked={enabled}
              onCheckedChange={checked => {
                onChange(checked ? { tcp: [], udp: [], quicParams: {} } : undefined)
              }}
            />
          </div>
          {enabled && <XrayStreamFinalmaskFields value={value} onChange={onChange} t={t} />}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
