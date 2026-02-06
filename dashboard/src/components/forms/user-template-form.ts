import { DataLimitResetStrategy, ShadowsocksMethods, UserStatusCreate, XTLSFlows } from '@/service/api'
import { z } from 'zod'

export const userTemplateFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  status: z.enum([UserStatusCreate.active, UserStatusCreate.on_hold]).default(UserStatusCreate.active),
  username_prefix: z.string().optional(),
  username_suffix: z.string().optional(),
  data_limit: z.number().min(0).optional(),
  expire_duration: z.number().min(0).optional(),
  on_hold_timeout: z.number().optional(),
  method: z
    .enum([ShadowsocksMethods['aes-128-gcm'], ShadowsocksMethods['aes-256-gcm'], ShadowsocksMethods['chacha20-ietf-poly1305'], ShadowsocksMethods['xchacha20-poly1305']])
    .default(ShadowsocksMethods['chacha20-ietf-poly1305']),
  flow: z.enum([XTLSFlows[''], XTLSFlows['xtls-rprx-vision']]).default(XTLSFlows['']),
  groups: z.array(z.number()).min(1, 'Groups is required'),
  data_limit_reset_strategy: z
    .enum([
      DataLimitResetStrategy['month'],
      DataLimitResetStrategy['day'],
      DataLimitResetStrategy['week'],
      DataLimitResetStrategy['no_reset'],
      DataLimitResetStrategy['week'],
      DataLimitResetStrategy['year'],
    ])
    .optional(),
  reset_usages: z.boolean().optional(),
})

export type UserTemplatesFromValueInput = z.input<typeof userTemplateFormSchema>
export type UserTemplatesFromValue = z.infer<typeof userTemplateFormSchema>
