import { DataLimitResetStrategy, ShadowsocksMethods, UserStatusCreate, XTLSFlows } from '@/service/api'
import { zodResolver } from '@hookform/resolvers/zod'
import type { TFunction } from 'i18next'
import type { FieldError, FieldErrors, Resolver } from 'react-hook-form'
import { z } from 'zod'

const userTemplateFormObjectSchema = z.object({
  name: z.string().min(1, 'validation.required'),
  status: z.enum([UserStatusCreate.active, UserStatusCreate.on_hold]).default(UserStatusCreate.active),
  username_prefix: z.string().optional(),
  username_suffix: z.string().optional(),
  data_limit: z.number().min(0).optional(),
  expire_duration: z.number().min(0).optional(),
  on_hold_timeout: z.number().optional(),
  method: z
    .enum([ShadowsocksMethods['aes-128-gcm'], ShadowsocksMethods['aes-256-gcm'], ShadowsocksMethods['chacha20-ietf-poly1305'], ShadowsocksMethods['xchacha20-poly1305']])
    .default(ShadowsocksMethods['chacha20-ietf-poly1305']),
  flow: z.enum([XTLSFlows[''], XTLSFlows['xtls-rprx-vision'], XTLSFlows['xtls-rprx-vision-udp443']]).default(XTLSFlows['']),
  groups: z.array(z.number()).min(1, 'validation.required'),
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

function refineUserTemplateOnHold(data: z.infer<typeof userTemplateFormObjectSchema>, ctx: z.RefinementCtx) {
  if (data.status !== UserStatusCreate.on_hold) return
  const exp = data.expire_duration
  if (exp == null || !Number.isFinite(Number(exp)) || Number(exp) <= 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'validation.required',
      path: ['expire_duration'],
    })
  }
}

export const userTemplateFormSchema = userTemplateFormObjectSchema.superRefine(refineUserTemplateOnHold)

export type UserTemplatesFromValueInput = z.input<typeof userTemplateFormSchema>
export type UserTemplatesFromValue = z.infer<typeof userTemplateFormSchema>

export const userTemplateFormDefaultValues: Partial<UserTemplatesFromValueInput> = {
  name: '',
  status: UserStatusCreate.active,
  username_prefix: '',
  username_suffix: '',
  data_limit: 0,
  expire_duration: 0,
  method: ShadowsocksMethods['chacha20-ietf-poly1305'],
  flow: XTLSFlows[''],
  on_hold_timeout: undefined,
  groups: [],
  reset_usages: false,
}

/** Wraps zodResolver: turns `validation.required` into fully translated messages (same idea as `user-modal` `setError` with `t('validation.required', { field: … })`). */
export function createUserTemplateFormResolver(t: TFunction): Resolver<UserTemplatesFromValueInput> {
  const base = zodResolver(userTemplateFormSchema)
  return async (values, context, options) => {
    const result = await base(values, context, options)
    if (!result.errors) return result
    const errors = { ...result.errors } as FieldErrors<UserTemplatesFromValueInput>
    for (const key of Object.keys(errors) as Array<keyof FieldErrors<UserTemplatesFromValueInput>>) {
      const err = errors[key] as FieldError | undefined
      if (err && typeof err === 'object' && err.message === 'validation.required') {
        const fieldName = String(key)
        const fieldLabelKey =
          fieldName === 'name'
            ? 'templates.name'
            : fieldName === 'expire_duration'
              ? 'templates.expire'
              : fieldName === 'groups'
                ? 'templates.groups'
                : `fields.${fieldName}`
        ;(errors as Record<string, FieldError | undefined>)[fieldName] = {
          ...err,
          message: t('validation.required', { field: t(fieldLabelKey, { defaultValue: fieldName }) }),
        }
      }
    }
    return { ...result, errors } as Awaited<ReturnType<typeof base>>
  }
}
