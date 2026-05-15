import { Button } from '@/components/ui/button'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import useDirDetection from '@/hooks/use-dir-detection'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { generateWireGuardKeyPair } from '@pasarguard/core-kit/wireguard'
import { getWireGuardCoreFormCapabilities, syncWireGuardCoreDraftPublicKey } from '@pasarguard/wireguard-config-kit'
import type { WireGuardCoreDraft } from '@pasarguard/wireguard-config-kit'
import { cn } from '@/lib/utils'
import { RefreshCcw } from 'lucide-react'
import { useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

function updateDraft(draft: WireGuardCoreDraft, key: keyof WireGuardCoreDraft, value: unknown): WireGuardCoreDraft {
  if (key === 'privateKey') {
    return syncWireGuardCoreDraftPublicKey({ ...draft, privateKey: String(value) })
  }
  return { ...draft, [key]: value } as WireGuardCoreDraft
}

function draftToFormValues(draft: WireGuardCoreDraft, fieldOrder: readonly string[]): Record<string, string> {
  const o: Record<string, string> = {}
  for (const k of fieldOrder) {
    if (k === 'extra') continue
    const v = draft[k as keyof WireGuardCoreDraft]
    o[k] = Array.isArray(v) ? (v as string[]).join('\n') : String(v ?? '')
  }
  return o
}

export function WireGuardCoreForm({ className }: { className?: string }) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const draft = useCoreEditorStore(s => s.wgDraft)
  const updateWgDraft = useCoreEditorStore(s => s.updateWgDraft)
  const caps = useMemo(() => getWireGuardCoreFormCapabilities(), [])

  const values = useMemo(
    () => (draft ? draftToFormValues(draft, caps.fieldOrder) : {}),
    [draft, caps.fieldOrder],
  )

  const form = useForm<Record<string, string>>({ values })

  if (!draft) return null

  const onField = (key: keyof WireGuardCoreDraft, value: unknown) => {
    updateWgDraft(d => updateDraft(d, key, value))
  }

  const regenKeys = () => {
    try {
      const pair = generateWireGuardKeyPair()
      updateWgDraft(d => syncWireGuardCoreDraftPublicKey({ ...d, privateKey: pair.privateKey, publicKey: pair.publicKey }))
      toast.success(t('coreEditor.wg.keysRegenerated', { defaultValue: 'New keypair generated' }))
    } catch {
      toast.error(t('coreEditor.wg.keysFailed', { defaultValue: 'Could not generate keys' }))
    }
  }

  return (
    <Form {...form}>
      <form className={cn(className)} onSubmit={e => e.preventDefault()}>
        <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">
          {caps.fieldOrder.map(key => {
            if (key === 'extra') return null
            const field = caps.fields[key]
            if (!field) return null
            if (field.input === 'readonly') {
              const isPublicKey = key === 'publicKey'
              return (
                <FormField
                  key={key}
                  control={form.control}
                  name={key}
                  render={({ field: f }) => (
                    <FormItem>
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        <Input
                          readOnly={!isPublicKey}
                          disabled={isPublicKey}
                          className="text-xs"
                          dir="ltr"
                          {...f}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )
            }
            if (field.input === 'secret' || field.input === 'text') {
              if (key === 'publicKey') {
                return (
                  <FormField
                    key={key}
                    control={form.control}
                    name={key}
                    render={({ field: f }) => (
                      <FormItem>
                        <FormLabel>{field.label}</FormLabel>
                        <FormControl>
                          <Input disabled className="text-xs" dir="ltr" placeholder={field.placeholder} {...f} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )
              }
              const showKeygen = key === 'privateKey'
              return (
                <FormField
                  key={key}
                  control={form.control}
                  name={key}
                  render={({ field: f }) => (
                    <FormItem>
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        {showKeygen ? (
                          <div
                            dir="ltr"
                            className={cn(
                              'flex items-center gap-2',
                              dir === 'rtl' ? 'flex-row-reverse' : 'flex-row',
                            )}
                          >
                            <Input
                              type={field.input === 'secret' ? 'password' : 'text'}
                              placeholder={field.placeholder}
                              className="min-w-0 flex-1 text-xs"
                              {...f}
                              onChange={e => {
                                const val = e.target.value
                                f.onChange(val)
                                onField(key as keyof WireGuardCoreDraft, val)
                              }}
                            />
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              className="h-9 w-9 shrink-0"
                              onClick={regenKeys}
                              title={t('coreEditor.wg.regenerateKeys', { defaultValue: 'Regenerate keypair' })}
                            >
                              <RefreshCcw className="h-3 w-3" />
                            </Button>
                          </div>
                        ) : (
                          <Input
                            type={field.input === 'secret' ? 'password' : 'text'}
                            placeholder={field.placeholder}
                            className="text-xs"
                            dir="ltr"
                            {...f}
                            onChange={e => {
                              const val = e.target.value
                              f.onChange(val)
                              onField(key as keyof WireGuardCoreDraft, val)
                            }}
                          />
                        )}
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )
            }
            if (field.input === 'number') {
              return (
                <FormField
                  key={key}
                  control={form.control}
                  name={key}
                  render={({ field: f }) => (
                    <FormItem>
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        <Input
                          type="text"
                          inputMode="numeric"
                          placeholder={field.placeholder}
                          className="text-xs"
                          {...f}
                          onChange={e => {
                            const val = e.target.value
                            f.onChange(val)
                            onField(key as keyof WireGuardCoreDraft, val)
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )
            }
            if (field.input === 'string-array') {
              return (
                <FormField
                  key={key}
                  control={form.control}
                  name={key}
                  render={({ field: f }) => (
                    <FormItem className="sm:col-span-2">
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        <Textarea
                          rows={4}
                          className="text-xs"
                          dir="ltr"
                          placeholder={field.placeholder}
                          {...f}
                          onChange={e => {
                            const val = e.target.value
                            f.onChange(val)
                            onField(
                              key as keyof WireGuardCoreDraft,
                              val
                                .split('\n')
                                .map(s => s.trim())
                                .filter(Boolean),
                            )
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )
            }
            return null
          })}
        </div>
      </form>
    </Form>
  )
}
