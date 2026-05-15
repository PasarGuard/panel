import { getInboundFormCapabilities } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'
import { z } from 'zod'
import { isValidXrayPortList } from '@/features/core-editor/kit/xray-port-list-validation'
type Caps = ReturnType<typeof getInboundFormCapabilities>

/** Must match `securityFieldName('serverNames')` in xray-inbounds-section (`sec_${jsonKey}`). */
export const INBOUND_FORM_FIELD_SEC_SERVER_NAMES = 'sec_serverNames' as const

/** Must match `securityFieldName('target')` for REALITY. */
export const INBOUND_FORM_FIELD_SEC_TARGET = 'sec_target' as const

/** Form keys to `form.trigger` when validating REALITY before commit (matches Zod `path` entries). */
export function realityInboundZodTriggerFieldNames(): string[] {
  return [
    INBOUND_FORM_FIELD_SEC_SERVER_NAMES,
    'sec_privateKey',
    'sec_shortIds',
    'sec_shortId',
    INBOUND_FORM_FIELD_SEC_TARGET,
  ]
}

/**
 * Aligns with @pasarguard/xray-config-kit REALITY schema: `serverNames` is a non-empty array of non-empty strings.
 * Flags blank lines/slots (e.g. `example.com,` or `["a",""]`) so strict export validation does not fail.
 */
export function validateRealityServerNamesFormRaw(raw: unknown, t: TFunction): string | undefined {
  if (raw === undefined || raw === null) {
    return t('coreEditor.inbound.validation.realityServerNamesRequired', {
      defaultValue: 'REALITY requires at least one server name.',
    })
  }
  const s = String(raw)
  const trimmedAll = s.trim()
  if (trimmedAll === '') {
    return t('coreEditor.inbound.validation.realityServerNamesRequired', {
      defaultValue: 'REALITY requires at least one server name.',
    })
  }

  let parts: string[]
  if (trimmedAll.startsWith('[')) {
    try {
      const parsed: unknown = JSON.parse(trimmedAll)
      if (!Array.isArray(parsed)) {
        return t('coreEditor.inbound.validation.realityServerNamesFormat', {
          defaultValue: 'REALITY server names must be a list of non-empty strings.',
        })
      }
      parts = parsed.map(item => String(item ?? '').trim())
    } catch {
      parts = s.split(/(?:,|\n)/).map(part => part.trim())
    }
  } else {
    parts = s.split(/(?:,|\n)/).map(part => part.trim())
  }

  if (parts.some(p => p.length === 0)) {
    return t('coreEditor.inbound.validation.realityServerNamesNoEmpty', {
      defaultValue: 'Each REALITY server name must be non-empty; remove blank lines or extra commas.',
    })
  }
  return undefined
}

/** Basics validated like host port/remark: required fields + numeric port range. Dynamic form keys pass through. */
export function createInboundDialogSchema(caps: Caps, t: TFunction) {
  const allowedProtocols = caps.protocolOrder.filter(p => caps.protocols[p])
  const protocolLabel = t('coreEditor.field.protocol', { defaultValue: 'Protocol' })
  const tagLabel = t('coreEditor.field.tag', { defaultValue: 'Tag' })
  const portLabel = t('coreEditor.field.port', { defaultValue: 'Port' })

  const required = (fieldLabel: string) =>
    t('validation.required', { field: fieldLabel, defaultValue: `${fieldLabel} is required` })

  return z
    .object({
      protocol: z
        .string()
        .min(1, required(protocolLabel))
        .refine(p => allowedProtocols.includes(p as (typeof allowedProtocols)[number]), {
          message: t('coreEditor.inbound.validation.protocolInvalid', {
            defaultValue: 'Select a valid protocol.',
          }),
        }),
      tag: z.string().refine(v => v.trim().length > 0, {
        message: required(tagLabel),
      }),
      port: z.string().optional(),
    })
    .passthrough()
    .superRefine((data, ctx) => {
      const p = typeof data.protocol === 'string' ? data.protocol.trim() : ''
      if (p === 'tun') return
      const rawPort = typeof data.port === 'string' ? data.port.trim() : ''
      if (rawPort.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(portLabel),
          path: ['port'],
        })
        return
      }
      if (!isValidXrayPortList(rawPort)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: t('coreEditor.inbound.validation.portRange', {
            defaultValue: 'Port must be a port number or list like 443, 1000-2000,444.',
          }),
          path: ['port'],
        })
      }
    })
    .superRefine((data, ctx) => {
      if (data.security !== 'reality') return
      
      const msg = validateRealityServerNamesFormRaw(data[INBOUND_FORM_FIELD_SEC_SERVER_NAMES], t)
      if (msg) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: msg,
          path: [INBOUND_FORM_FIELD_SEC_SERVER_NAMES],
        })
      }
      
      // REALITY: private key required; public key may stay empty (e.g. client-only / derived elsewhere).
      const raw = data as Record<string, unknown>
      const privateKeyLabel = t('coreEditor.field.privateKey', { defaultValue: 'Private Key' })
      const shortIdsLabel = t('coreEditor.field.shortIds', { defaultValue: 'Short IDs' })

      const privateKeyValue = typeof raw.sec_privateKey === 'string' ? raw.sec_privateKey.trim() : ''
      if (privateKeyValue === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(privateKeyLabel),
          path: ['sec_privateKey'],
        })
      }
      
      const shortIdsValue =
        (typeof raw.sec_shortIds === 'string' ? raw.sec_shortIds.trim() : '') ||
        (typeof raw.sec_shortId === 'string' ? raw.sec_shortId.trim() : '')
      if (shortIdsValue === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(shortIdsLabel),
          path: ['sec_shortIds'],
        })
      }

      const targetLabel = t('coreEditor.field.realityTarget', { defaultValue: 'REALITY target' })
      const targetValue = typeof raw[INBOUND_FORM_FIELD_SEC_TARGET] === 'string' ? String(raw[INBOUND_FORM_FIELD_SEC_TARGET]).trim() : ''
      if (targetValue === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(targetLabel),
          path: [INBOUND_FORM_FIELD_SEC_TARGET],
        })
      }
    })
    .superRefine((data, ctx) => {
      const p = typeof data.protocol === 'string' ? data.protocol.trim() : ''
      if (p !== 'tun') return
      const tunNameLabel = t('coreEditor.inbound.tun.name', { defaultValue: 'Interface Name' })
      const tunMtuLabel = t('coreEditor.inbound.tun.mtu', { defaultValue: 'MTU' })
      const raw = data as Record<string, unknown>

      const nameValue = typeof raw.tunName === 'string' ? raw.tunName.trim() : ''
      if (nameValue === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(tunNameLabel),
          path: ['tunName'],
        })
      }

      const mtuRaw = typeof raw.tunMtu === 'string' ? raw.tunMtu.trim() : ''
      if (mtuRaw === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(tunMtuLabel),
          path: ['tunMtu'],
        })
        return
      }
      const mtu = Number(mtuRaw)
      if (!Number.isFinite(mtu) || !Number.isInteger(mtu) || mtu <= 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: t('coreEditor.inbound.validation.tunMtuRange', {
            defaultValue: 'MTU must be a positive whole number.',
          }),
          path: ['tunMtu'],
        })
      }
    })
    .superRefine((data, ctx) => {
      const p = typeof data.protocol === 'string' ? data.protocol.trim() : ''
      if (p !== 'wireguard') return
      const secretKeyLabel = t('coreEditor.inbound.wireguard.secretKey', { defaultValue: 'Secret Key' })
      const raw = data as Record<string, unknown>
      const keyValue = typeof raw.wgSecretKey === 'string' ? raw.wgSecretKey.trim() : ''
      if (keyValue === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(secretKeyLabel),
          path: ['wgSecretKey'],
        })
      }
    })
    .superRefine((data, ctx) => {
      const p = typeof data.protocol === 'string' ? data.protocol.trim() : ''
      if (p !== 'tunnel' && p !== 'dokodemo-door') return

      const targetLabel = t('coreEditor.inbound.tunnel.targetAddress', { defaultValue: 'Target address' })
      const destPortLabel = t('coreEditor.inbound.tunnel.destinationPort', { defaultValue: 'Destination port' })

      const raw = data as Record<string, unknown>
      const addr = typeof raw.tunnelRewriteAddress === 'string' ? raw.tunnelRewriteAddress.trim() : ''
      if (addr === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(targetLabel),
          path: ['tunnelRewriteAddress'],
        })
      }

      const portRaw =
        typeof raw.tunnelRewritePort === 'string' ? raw.tunnelRewritePort.trim() : ''
      if (portRaw === '') {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: required(destPortLabel),
          path: ['tunnelRewritePort'],
        })
        return
      }
      const n = Number(portRaw)
      if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0 || n > 65535) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: t('coreEditor.inbound.validation.destinationPortRange', {
            defaultValue: 'Destination port must be a whole number from 0 to 65535.',
          }),
          path: ['tunnelRewritePort'],
        })
      }
    })
}
