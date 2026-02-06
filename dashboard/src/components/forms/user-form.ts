import { DEFAULT_SHADOWSOCKS_METHOD } from '@/constants/Proxies'
import { z } from 'zod'

export const userStatusEnum = z.enum(['active', 'disabled', 'limited', 'expired', 'on_hold'])
export const userDataLimitResetStrategyEnum = z.enum(['no_reset', 'day', 'week', 'month', 'year'])
export const xtlsFlowsEnum = z.enum(['', 'xtls-rprx-vision'])
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
export const proxyTableInputSchema = z.object({
  vmess: vMessSettingsSchema.optional(),
  vless: vlessSettingsSchema.optional(),
  trojan: trojanSettingsSchema.optional(),
  shadowsocks: shadowsocksSettingsSchema.optional(),
})

export const userStatusCreateEnum = z.enum(['active', 'on_hold'])
export const userStatusEditEnum = z.enum(['active', 'on_hold', 'disabled'])

export const nextPlanModelSchema = z.object({
  user_template_id: z.number().optional(),
  data_limit: z.number().min(0).optional(),
  expire: z.number().min(0).optional(),
  add_remaining_traffic: z.boolean().optional(),
})

export const userCreateSchema = z.object({
  username: z.string().min(3, 'validation.minLength').max(32, 'validation.maxLength'),
  status: userStatusCreateEnum.optional(),
  group_ids: z.array(z.number()).min(1, { message: 'validation.required' }),
  data_limit: z.number().min(0),
  expire: z.union([z.string(), z.number(), z.null()]).optional(),
  note: z.string().optional(),
  proxy_settings: proxyTableInputSchema.optional(),
  data_limit_reset_strategy: userDataLimitResetStrategyEnum.optional(),
  on_hold_expire_duration: z
    .number()
    .nullable()
    .optional()
    .superRefine((val, ctx) => {
      const status = (ctx.path.length > 0 ? ctx.path[0] : 'status') as string
      if (status === 'on_hold' && (!val || val < 1)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'validation.required',
        })
      }
    }),
  on_hold_timeout: z.union([z.string(), z.number(), z.null()]).optional(),
  auto_delete_in_days: z.number().optional(),
  next_plan: nextPlanModelSchema.optional(),
  template_id: z.number().optional(),
})

export const userEditSchema = z.object({
  username: z.string().min(3, 'validation.minLength').max(32, 'validation.maxLength'),
  status: userStatusEditEnum.optional(),
  group_ids: z.array(z.number()).min(1, { message: 'validation.required' }),
  data_limit: z.number().min(0),
  expire: z.union([z.string(), z.number(), z.null()]).optional(),
  note: z.string().optional(),
  proxy_settings: proxyTableInputSchema.optional(),
  data_limit_reset_strategy: userDataLimitResetStrategyEnum.optional(),
  on_hold_expire_duration: z
    .number()
    .nullable()
    .optional()
    .superRefine((val, ctx) => {
      const status = (ctx.path.length > 0 ? ctx.path[0] : 'status') as string
      if (status === 'on_hold' && (!val || val < 1)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'validation.required',
        })
      }
    }),
  on_hold_timeout: z.union([z.string(), z.number(), z.null()]).optional(),
  auto_delete_in_days: z.number().optional(),
  next_plan: nextPlanModelSchema.optional(),
  template_id: z.number().optional(),
})

export type UseEditFormValues = z.infer<typeof userEditSchema>
export type UseFormValues = z.infer<typeof userCreateSchema>

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
    },
  } satisfies UseFormValues
}

