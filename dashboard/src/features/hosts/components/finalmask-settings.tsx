import { useFieldArray, type UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { HostFormValues } from '../forms/host-form'
import type { FinalMaskTcpType, FinalMaskUdpType, XrayNoiseSettings } from '@/service/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { FormField, FormItem, FormLabel, FormControl } from '@/components/ui/form'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Plus, Trash2, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import useDirDetection from '@/hooks/use-dir-detection'

interface FinalMaskSettingsProps {
  form: UseFormReturn<HostFormValues>
}

export function FinalMaskSettings({ form }: FinalMaskSettingsProps) {
  const dir = useDirDetection()

  return (
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
  )
}

// ==========================================
// TCP Layers component
// ==========================================
function TcpLayersForm({ form }: { form: UseFormReturn<any> }) {
  const { t } = useTranslation()
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'final_mask_settings.tcp',
  })

  const handleAddLayer = () => {
    append({
      type: 'fragment',
      settings: {
        packets: '',
        length: '',
        interval: '',
      },
    })
  }

  const handleTypeChange = (index: number, newType: FinalMaskTcpType) => {
    form.setValue(`final_mask_settings.tcp.${index}.type`, newType)
    if (newType === 'fragment') {
      form.setValue(`final_mask_settings.tcp.${index}.settings`, {
        packets: '',
        length: '',
        interval: '',
      })
    } else if (newType === 'sudoku') {
      form.setValue(`final_mask_settings.tcp.${index}.settings`, {
        password: '',
        ascii: '',
        customTable: '',
        customTables: [],
        paddingMin: undefined,
        paddingMax: undefined,
      })
    } else if (newType === 'header-custom') {
      form.setValue(`final_mask_settings.tcp.${index}.settings`, {
        clients: [],
        servers: [],
        errors: [],
      })
    } else if (newType === 'xmc') {
      form.setValue(`final_mask_settings.tcp.${index}.settings`, {
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
          const type = form.watch(`final_mask_settings.tcp.${index}.type`)
          return (
            <div key={field.id} className="bg-muted/5 relative space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-muted-foreground w-6 text-xs font-semibold">#{index + 1}</span>
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.tcp.${index}.type`}
                    render={({ field: selectField }) => (
                      <FormItem className="w-48">
                        <Select onValueChange={val => handleTypeChange(index, val as FinalMaskTcpType)} value={selectField.value || ''}>
                          <FormControl>
                            <SelectTrigger className="h-8">
                              <SelectValue placeholder="Select type" />
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

              {type === 'fragment' && (
                <div className="bg-background grid grid-cols-3 gap-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.tcp.${index}.settings.packets`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">Packets</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. 100-200" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.tcp.${index}.settings.length`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">Length</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. 10-20" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.tcp.${index}.settings.interval`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">Interval</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. 10-20" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'sudoku' && <SudokuSettingsForm prefix={`final_mask_settings.tcp.${index}.settings`} form={form} />}

              {type === 'header-custom' && (
                <div className="bg-background space-y-4 rounded-md border p-3">
                  <JsonArrayField form={form} name={`final_mask_settings.tcp.${index}.settings.clients`} label="Clients (JSON array of noise arrays)" />
                  <JsonArrayField form={form} name={`final_mask_settings.tcp.${index}.settings.servers`} label="Servers (JSON array of noise arrays)" />
                  <JsonArrayField form={form} name={`final_mask_settings.tcp.${index}.settings.errors`} label="Errors (JSON array of noise arrays)" />
                </div>
              )}

              {type === 'xmc' && (
                <XmcSettingsForm prefix={`final_mask_settings.tcp.${index}.settings`} form={form} />
              )}
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
    name: 'final_mask_settings.udp',
  })

  const handleAddLayer = () => {
    append({
      type: 'header-dns',
      settings: {
        domain: '',
      },
    })
  }

  const handleTypeChange = (index: number, newType: FinalMaskUdpType) => {
    form.setValue(`final_mask_settings.udp.${index}.type`, newType)
    if (newType === 'header-dns' || newType === 'xdns') {
      form.setValue(`final_mask_settings.udp.${index}.settings`, { domain: '' })
    } else if (['header-dtls', 'header-srtp', 'header-utp', 'header-wechat', 'header-wireguard', 'mkcp-original', 'mkcp-aes128gcm', 'salamander'].includes(newType)) {
      form.setValue(`final_mask_settings.udp.${index}.settings`, { password: '' })
    } else if (newType === 'noise') {
      form.setValue(`final_mask_settings.udp.${index}.settings`, { reset: undefined, noise: [] })
    } else if (newType === 'sudoku') {
      form.setValue(`final_mask_settings.udp.${index}.settings`, {
        password: '',
        ascii: '',
        customTable: '',
        customTables: [],
        paddingMin: undefined,
        paddingMax: undefined,
      })
    } else if (newType === 'xicmp') {
      form.setValue(`final_mask_settings.udp.${index}.settings`, { listenIp: '', id: undefined })
    } else if (newType === 'header-custom') {
      form.setValue(`final_mask_settings.udp.${index}.settings`, { client: [], server: [] })
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
          const type = form.watch(`final_mask_settings.udp.${index}.type`)
          return (
            <div key={field.id} className="bg-muted/5 relative space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-muted-foreground w-6 text-xs font-semibold">#{index + 1}</span>
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.udp.${index}.type`}
                    render={({ field: selectField }) => (
                      <FormItem className="w-56">
                        <Select onValueChange={val => handleTypeChange(index, val as FinalMaskUdpType)} value={selectField.value || ''}>
                          <FormControl>
                            <SelectTrigger className="h-8">
                              <SelectValue placeholder="Select type" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="header-dns">header-dns</SelectItem>
                            <SelectItem value="xdns">xdns</SelectItem>
                            <SelectItem value="header-dtls">header-dtls</SelectItem>
                            <SelectItem value="header-srtp">header-srtp</SelectItem>
                            <SelectItem value="header-utp">header-utp</SelectItem>
                            <SelectItem value="header-wechat">header-wechat</SelectItem>
                            <SelectItem value="header-wireguard">header-wireguard</SelectItem>
                            <SelectItem value="mkcp-original">mkcp-original</SelectItem>
                            <SelectItem value="mkcp-aes128gcm">mkcp-aes128gcm</SelectItem>
                            <SelectItem value="noise">noise</SelectItem>
                            <SelectItem value="salamander">salamander</SelectItem>
                            <SelectItem value="sudoku">sudoku</SelectItem>
                            <SelectItem value="xicmp">xicmp</SelectItem>
                            <SelectItem value="header-custom">header-custom</SelectItem>
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

              {(type === 'header-dns' || type === 'xdns') && (
                <div className="bg-background rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.udp.${index}.settings.domain`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">Domain</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. example.com" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {['header-dtls', 'header-srtp', 'header-utp', 'header-wechat', 'header-wireguard', 'mkcp-original', 'mkcp-aes128gcm', 'salamander'].includes(type) && (
                <div className="bg-background rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.udp.${index}.settings.password`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">Password</FormLabel>
                        <FormControl>
                          <Input placeholder="Password" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              )}

              {type === 'sudoku' && <SudokuSettingsForm prefix={`final_mask_settings.udp.${index}.settings`} form={form} />}

              {type === 'xicmp' && (
                <div className="bg-background grid grid-cols-2 gap-3 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.udp.${index}.settings.listenIp`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">Listen IP</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g. 127.0.0.1" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.udp.${index}.settings.id`}
                    render={({ field: inputField }) => (
                      <FormItem>
                        <FormLabel className="text-xs">ID</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="ID number"
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
              )}

              {type === 'noise' && (
                <div className="bg-background space-y-4 rounded-md border p-3">
                  <FormField
                    control={form.control}
                    name={`final_mask_settings.udp.${index}.settings.reset`}
                    render={({ field: inputField }) => (
                      <FormItem className="w-48">
                        <FormLabel className="text-xs">Reset count</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="Reset"
                            {...inputField}
                            value={inputField.value ?? ''}
                            onChange={e => inputField.onChange(e.target.value === '' ? undefined : Number(e.target.value))}
                            className="h-8 text-xs"
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <XrayNoiseSettingsList form={form} name={`final_mask_settings.udp.${index}.settings.noise`} label="Noise Settings" />
                </div>
              )}

              {type === 'header-custom' && (
                <div className="bg-background space-y-4 rounded-md border p-3">
                  <XrayNoiseSettingsList form={form} name={`final_mask_settings.udp.${index}.settings.client`} label="Client Settings" />
                  <XrayNoiseSettingsList form={form} name={`final_mask_settings.udp.${index}.settings.server`} label="Server Settings" />
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
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name="final_mask_settings.quicParams.congestion"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">Congestion</FormLabel>
              <Select onValueChange={field.onChange} value={field.value || ''}>
                <FormControl>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Select congestion" />
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
          name="final_mask_settings.quicParams.debug"
          render={({ field }) => (
            <FormItem dir="ltr" className="mt-6 flex min-h-9 items-center justify-between gap-3 rounded-md border px-3 py-2">
              <FormLabel className="min-w-0 cursor-pointer truncate text-left text-xs font-normal">Debug</FormLabel>
              <FormControl>
                <Switch checked={!!field.value} onCheckedChange={field.onChange} className="scale-75" />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="final_mask_settings.quicParams.brutalUp"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">Brutal Up (Mbps)</FormLabel>
              <FormControl>
                <Input placeholder="e.g. 100" {...field} value={field.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="final_mask_settings.quicParams.brutalDown"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs">Brutal Down (Mbps)</FormLabel>
              <FormControl>
                <Input placeholder="e.g. 100" {...field} value={field.value || ''} className="h-8 text-xs" />
              </FormControl>
            </FormItem>
          )}
        />
      </div>

      <div className="border-t pt-3">
        <h5 className="mb-2 text-xs font-semibold">UDP Hop</h5>
        <div className="bg-muted/5 grid grid-cols-2 gap-3 rounded-md border p-3">
          <FormField
            control={form.control}
            name="final_mask_settings.quicParams.udpHop.ports"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Ports</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. 50000-60000" {...field} value={field.value || ''} className="h-8 text-xs" />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="final_mask_settings.quicParams.udpHop.interval"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Interval (ms or duration)</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. 10s or 10000" {...field} value={field.value || ''} className="h-8 text-xs" />
                </FormControl>
              </FormItem>
            )}
          />
        </div>
      </div>

      <div className="border-t pt-3">
        <h5 className="mb-2 text-xs font-semibold">Windows & Stream settings</h5>
        <div className="grid grid-cols-2 gap-3">
          <FormField
            control={form.control}
            name="final_mask_settings.quicParams.initStreamReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Init Stream RX Window</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="Bytes"
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
            name="final_mask_settings.quicParams.maxStreamReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Max Stream RX Window</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="Bytes"
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
            name="final_mask_settings.quicParams.initConnectionReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Init Connection RX Window</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="Bytes"
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
            name="final_mask_settings.quicParams.maxConnectionReceiveWindow"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Max Connection RX Window</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="Bytes"
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
            name="final_mask_settings.quicParams.maxIncomingStreams"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Max Incoming Streams</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="Streams count"
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
            name="final_mask_settings.quicParams.maxIdleTimeout"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Max Idle Timeout (ms)</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="e.g. 30000"
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
            name="final_mask_settings.quicParams.keepAlivePeriod"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Keep Alive Period (ms)</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    placeholder="e.g. 10000"
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
            name="final_mask_settings.quicParams.disablePathMTUDiscovery"
            render={({ field }) => (
              <FormItem dir="ltr" className="mt-6 flex min-h-9 items-center justify-between gap-3 rounded-md border px-3 py-2">
                <FormLabel className="min-w-0 cursor-pointer truncate text-left text-xs font-normal">Disable PMTU Discovery</FormLabel>
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
            <FormLabel className="text-xs">Password</FormLabel>
            <FormControl>
              <Input placeholder="Password" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.ascii`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">ASCII</FormLabel>
            <FormControl>
              <Input placeholder="ASCII Table" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.customTable`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">Custom Table</FormLabel>
            <FormControl>
              <Input placeholder="Custom Table" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.customTables`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">Custom Tables</FormLabel>
            <FormControl>
              <StringArrayPopoverInput
                value={Array.isArray(inputField.value) ? inputField.value : []}
                onChange={(next: string[]) => inputField.onChange(next)}
                placeholder="Add Table"
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
            <FormLabel className="text-xs">Padding Min</FormLabel>
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
            <FormLabel className="text-xs">Padding Max</FormLabel>
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

function XmcSettingsForm({ prefix, form }: { prefix: string; form: UseFormReturn<HostFormValues> }) {
  const { t } = useTranslation()
  return (
    <div className="grid grid-cols-2 gap-3 bg-background p-3 rounded-md border">
      <FormField
        control={form.control}
        name={`${prefix}.hostname`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">Hostname</FormLabel>
            <FormControl>
              <Input placeholder="Hostname" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.password`}
        render={({ field: inputField }) => (
          <FormItem>
            <FormLabel className="text-xs">Password</FormLabel>
            <FormControl>
              <Input placeholder="Password" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={`${prefix}.usernames`}
        render={({ field: inputField }) => (
          <FormItem className="col-span-2">
            <FormLabel className="text-xs">Usernames</FormLabel>
            <FormControl>
              <StringArrayPopoverInput
                value={Array.isArray(inputField.value) ? inputField.value : []}
                onChange={(next: string[]) => inputField.onChange(next)}
                placeholder="Add Username"
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

// ==========================================
// Noise Settings array editor helper
// ==========================================
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
        <Button type="button" variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={() => append({ type: 'rand', apply_to: 'ip', packet: '', delay: '', randRange: '' })}>
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
                    <Select onValueChange={inputField.onChange} value={inputField.value || 'rand'}>
                      <FormControl>
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue placeholder="Type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent side="top">
                        <SelectItem value="rand">rand</SelectItem>
                        <SelectItem value="array">array</SelectItem>
                        <SelectItem value="str">str</SelectItem>
                        <SelectItem value="base64">base64</SelectItem>
                        <SelectItem value="hex">hex</SelectItem>
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`${name}.${index}.apply_to`}
                render={({ field: inputField }) => (
                  <FormItem className="w-[90px] shrink-0">
                    <Select onValueChange={inputField.onChange} value={inputField.value || 'ip'}>
                      <FormControl>
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue placeholder="Apply To" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent side="top">
                        <SelectItem value="ip">ip</SelectItem>
                        <SelectItem value="ipv4">ipv4</SelectItem>
                        <SelectItem value="ipv6">ipv6</SelectItem>
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
                      <Input placeholder="Packet" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
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
                      <Input placeholder="Delay" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
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
                      <Input placeholder="Rand" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
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
                      <Input placeholder="Rand Range" {...inputField} value={inputField.value || ''} className="h-8 text-xs" />
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
