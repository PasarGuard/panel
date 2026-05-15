import { DEFAULT_SHADOWSOCKS_METHOD } from '@/constants/Proxies'
import { z } from 'zod'

export const userStatusEnum = z.enum(['active', 'disabled', 'limited', 'expired', 'on_hold'])
export const userDataLimitResetStrategyEnum = z.enum(['no_reset', 'day', 'week', 'month', 'year'])
export const xtlsFlowsEnum = z.enum(['', 'xtls-rprx-vision', 'xtls-rprx-vision-udp443'])
export const shadowsocksMethodsEnum = z.enum(['aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305', 'xchacha20-poly1305'])

export const vMessSettingsSchema = z.object({
  id: z.string().uuid().optional(),
})
export const vlessSettingsSchema = z.object({
  id: z.string().uuid().optional(),
  flow: xtlsFlowsEnum.optional(),
})
export const trojanSettingsSchema = z.object({
  password: z.string().min(2).max(32).optional(),
})
export const shadowsocksSettingsSchema = z.object({
  password: z.string().min(2).max(32).optional(),
  method: shadowsocksMethodsEnum.optional(),
})
export const hysteriaSettingsSchema = z.object({
  auth: z.string().min(1).optional(),
})
export const wireguardSettingsSchema = z.object({
  private_key: z.string().nullable().optional(),
  public_key: z.string().nullable().optional(),
  peer_ips: z.array(z.string()).optional(),
})
export const proxyTableInputSchema = z.object({
  vmess: vMessSettingsSchema.optional(),
  vless: vlessSettingsSchema.optional(),
  trojan: trojanSettingsSchema.optional(),
  shadowsocks: shadowsocksSettingsSchema.optional(),
  wireguard: wireguardSettingsSchema.optional(),
  hysteria: hysteriaSettingsSchema.optional(),
})

export const userStatusCreateEnum = z.enum(['active', 'on_hold'])
export const userStatusEditEnum = z.enum(['active', 'on_hold', 'disabled'])

export const nextPlanModelSchema = z.object({
  user_template_id: z.number().optional(),
  data_limit: z.number().min(0).optional(),
  expire: z.number().min(0).optional(),
  add_remaining_traffic: z.boolean().optional(),
})

const userSharedSchemaShape = {
  username: z.string().min(3, 'validation.minLength').max(128, 'validation.maxLength'),
  group_ids: z.array(z.number()).min(1, { message: 'validation.required' }),
  data_limit: z.number().min(0),
  expire: z.union([z.string(), z.number(), z.null()]).optional(),
  note: z.string().optional(),
  proxy_settings: proxyTableInputSchema.optional(),
  data_limit_reset_strategy: userDataLimitResetStrategyEnum.optional(),
  on_hold_expire_duration: z.number().nullable().optional(),
  on_hold_timeout: z.union([z.string(), z.number(), z.null()]).optional(),
  auto_delete_in_days: z.number().optional(),
  next_plan: nextPlanModelSchema.optional(),
  template_id: z.number().optional(),
} satisfies z.ZodRawShape

function refineOnHoldExpireDuration(data: { status?: string | null; on_hold_expire_duration?: number | null }, ctx: z.RefinementCtx) {
  if (data.status !== 'on_hold') return
  const v = data.on_hold_expire_duration
  const sec = v == null || v === undefined ? 0 : Number(v)
  if (!Number.isFinite(sec) || sec <= 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'validation.required',
      path: ['on_hold_expire_duration'],
    })
  }
}

/** Base shapes (no cross-field refine) — use `.partial()` for touched-field validation; full schemas use `userCreateSchema` / `userEditSchema`. */
export const userCreateObjectSchema = z.object({
  ...userSharedSchemaShape,
  status: userStatusCreateEnum.optional(),
})

export const userEditObjectSchema = z.object({
  ...userSharedSchemaShape,
  status: userStatusEditEnum.optional(),
})

export const userCreateSchema = userCreateObjectSchema.superRefine(refineOnHoldExpireDuration)

export const userEditSchema = userEditObjectSchema.superRefine(refineOnHoldExpireDuration)

export type UserFormValues = z.infer<typeof userEditSchema>
export type UseEditFormValues = UserFormValues
export type UseFormValues = UserFormValues

export const getDefaultUserForm = async () => {
  return {
    username: '',
    status: 'active',
    data_limit: 0,
    expire: '',
    note: '',
    group_ids: [],
    proxy_settings: {
      vmess: {
        id: undefined,
      },
      vless: {
        id: undefined,
        flow: '',
      },
      trojan: {
        password: undefined,
      },
      shadowsocks: {
        password: undefined,
        method: DEFAULT_SHADOWSOCKS_METHOD,
      },
      wireguard: {
        private_key: undefined,
        public_key: undefined,
        peer_ips: [],
      },
      hysteria: {
        auth: undefined,
      },
    },
  } satisfies UseFormValues
}
