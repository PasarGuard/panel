import { CopyButton } from '@/components/common/copy-button'
import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderButton } from '@/components/ui/loader-button'
import { PasswordInput } from '@/components/ui/password-input'
import {
  classifyWireguardAddresses,
  deriveWireguardPublicKey,
  parseWireguardMtuInput,
  parseWireguardReservedInput,
  WIREGUARD_DEFAULT_MTU,
  wireguardInboundAddresses,
} from '@/features/core-editor/kit/wireguard-xray-fields'
import { generateWireGuardKeyPair } from '@/utils/wireguard'
import type { Inbound } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'
import { useId, useMemo } from 'react'
import type { UseFormReturn } from 'react-hook-form'
import { toast } from 'sonner'

export interface WireguardInboundFieldsProps {
  inbound: Inbound
  form: UseFormReturn<Record<string, string>>
  patchInbound: (patch: Partial<Inbound>) => void
  t: TFunction
}

/** WireGuard inbound interface settings. Peers stay backend managed, so there is no peer editor here. */
export function WireguardInboundFields({ inbound, form, patchInbound, t }: WireguardInboundFieldsProps) {
  const publicKeyId = useId()
  const model = inbound as { secretKey?: unknown; address?: unknown }
  const secretKey = typeof model.secretKey === 'string' ? model.secretKey : ''
  const publicKey = useMemo(() => deriveWireguardPublicKey(secretKey), [secretKey])
  const addresses = wireguardInboundAddresses(model.address)
  const { allocatable, invalid } = classifyWireguardAddresses(addresses)

  return (
    <div className="grid w-full min-w-0 gap-3 rounded-md border p-3 sm:col-span-2">
      <FormField
        control={form.control}
        name="wgSecretKey"
        render={({ field, fieldState }) => (
          <FormItem className="w-full min-w-0">
            <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.secretKey', { defaultValue: 'Secret Key' })}</FormLabel>
            <FormControl className="w-full">
              <PasswordInput
                {...field}
                dir="ltr"
                className="h-10 w-full text-xs"
                autoComplete="new-password"
                isError={!!fieldState.error}
                onChange={e => {
                  const v = e.target.value
                  field.onChange(v)
                  patchInbound({ secretKey: v.trim() === '' ? undefined : v.trim() } as Partial<Inbound>)
                }}
              />
            </FormControl>
            <div className="mt-2">
              <LoaderButton
                type="button"
                onClick={() => {
                  const keyPair = generateWireGuardKeyPair()
                  form.setValue('wgSecretKey', keyPair.privateKey)
                  patchInbound({ secretKey: keyPair.privateKey } as Partial<Inbound>)
                  toast.success(
                    t('coreConfigModal.wireguardKeyPairGenerated', {
                      defaultValue: 'WireGuard keypair generated',
                    }),
                  )
                }}
                className="h-10 w-full text-sm font-medium transition-all hover:shadow-md sm:h-11"
                isLoading={false}
              >
                <span className="flex items-center gap-2 truncate">{t('coreEditor.inbound.wireguard.generateSecretKey', { defaultValue: 'Generate secret key' })}</span>
              </LoaderButton>
            </div>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="w-full min-w-0 space-y-2">
        <Label htmlFor={publicKeyId} className="block text-sm">
          {t('coreEditor.inbound.wireguard.publicKey', { defaultValue: 'Public Key' })}
        </Label>
        <div dir="ltr" className="flex w-full min-w-0 items-center gap-2">
          <Input
            id={publicKeyId}
            dir="ltr"
            readOnly
            value={publicKey}
            placeholder={t('coreEditor.inbound.wireguard.publicKeyUnavailable', {
              defaultValue: 'Enter a valid secret key to see the public key.',
            })}
            className="h-10 w-full min-w-0 text-xs"
          />
          {publicKey !== '' && <CopyButton value={publicKey} copiedMessage="copied" defaultMessage="clickToCopy" className="h-10 w-10 shrink-0" />}
        </div>
        <p className="text-muted-foreground text-xs leading-relaxed">
          {t('coreEditor.inbound.wireguard.publicKeyHint', {
            defaultValue: 'Derived from the secret key. The panel puts it in client configs.',
          })}
        </p>
      </div>

      <div className="w-full min-w-0 space-y-1.5">
        <Label className="block text-sm">{t('coreEditor.inbound.wireguard.address', { defaultValue: 'Server Address' })}</Label>
        <StringArrayPopoverInput
          value={addresses}
          onChange={nextAddresses => {
            const cleaned = wireguardInboundAddresses(nextAddresses)
            patchInbound({ address: cleaned.length > 0 ? cleaned : undefined } as Partial<Inbound>)
          }}
          placeholder={t('coreEditor.inbound.wireguard.addressHint', {
            defaultValue: 'Example: 10.0.0.1/24',
          })}
          addPlaceholder={t('coreEditor.inbound.wireguard.addressAddPlaceholder', {
            defaultValue: 'Add address',
          })}
          addButtonLabel={t('coreEditor.inbound.wireguard.addItem', { defaultValue: 'Add' })}
          itemsLabel={t('coreEditor.inbound.wireguard.addressItems', { defaultValue: 'Addresses' })}
          emptyMessage={t('coreEditor.inbound.wireguard.noAddresses', {
            defaultValue: 'No address added.',
          })}
          className="h-10 w-full max-w-none min-w-0"
        />
        <p className="text-muted-foreground text-xs leading-relaxed">
          {t('coreEditor.inbound.wireguard.addressPoolHint', {
            defaultValue:
              'Clients get IPs from subnets with room for 4 or more addresses (IPv4 /30 or wider, IPv6 /126 or wider). Bare IPs and /31, /32, /127, /128 stay in the Xray config but give no client pool.',
          })}
        </p>
        {invalid.length > 0 ? (
          <p className="text-destructive text-xs">
            {t('coreEditor.inbound.wireguard.addressInvalid', {
              values: invalid.join(', '),
              defaultValue: 'Not an IP address or CIDR: {{values}}',
            })}
          </p>
        ) : (
          allocatable.length === 0 && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t('coreEditor.inbound.wireguard.addressNoPool', {
                defaultValue: 'No client subnet: the panel will not manage this inbound, so users get no WireGuard config from it.',
              })}
            </p>
          )
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <FormField
          control={form.control}
          name="wgMtu"
          render={({ field, fieldState }) => (
            <FormItem className="w-full min-w-0">
              <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.mtu', { defaultValue: 'MTU' })}</FormLabel>
              <FormControl className="w-full">
                <Input
                  {...field}
                  dir="ltr"
                  inputMode="numeric"
                  className="h-10 w-full min-w-0"
                  placeholder={String(WIREGUARD_DEFAULT_MTU)}
                  isError={!!fieldState.error}
                  onChange={e => {
                    const raw = e.target.value
                    field.onChange(raw)
                    const parsed = parseWireguardMtuInput(raw)
                    if (parsed.ok) patchInbound({ mtu: parsed.value } as Partial<Inbound>)
                  }}
                />
              </FormControl>
              <FormDescription className="text-xs leading-relaxed">{t('coreEditor.inbound.wireguard.mtuHint', { defaultValue: '576 to 9000. Leave empty for 1420.' })}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="wgReserved"
          render={({ field, fieldState }) => (
            <FormItem className="w-full min-w-0">
              <FormLabel className="text-sm">{t('coreEditor.inbound.wireguard.reserved', { defaultValue: 'Reserved' })}</FormLabel>
              <FormControl className="w-full">
                <Input
                  {...field}
                  dir="ltr"
                  className="h-10 w-full min-w-0"
                  placeholder="0, 0, 0"
                  isError={!!fieldState.error}
                  onChange={e => {
                    const raw = e.target.value
                    field.onChange(raw)
                    const parsed = parseWireguardReservedInput(raw)
                    if (parsed.ok) patchInbound({ reserved: parsed.value } as Partial<Inbound>)
                  }}
                />
              </FormControl>
              <FormDescription className="text-xs leading-relaxed">
                {t('coreEditor.inbound.wireguard.reservedHint', {
                  defaultValue: 'Optional. Three bytes from 0 to 255 that clients put in every packet, for example 1, 2, 3 or [1,2,3].',
                })}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
    </div>
  )
}
