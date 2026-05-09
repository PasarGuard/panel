import { z } from 'zod'

const optionalNonNegativeNumber = z.preprocess((value) => {
  if (value === '' || value === null || value === undefined) return undefined
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return undefined
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}, z.number().min(0).optional())

export const advanceSearchFormSchema = z
  .object({
    is_username: z.boolean().default(true),
    is_protocol: z.boolean().default(false),
    show_created_by: z.boolean().default(true),
    show_selection_checkbox: z.boolean().default(false),
    no_data_limit: z.boolean().default(false),
    no_expire: z.boolean().default(false),
    online: z.boolean().default(false),
    admin: z.array(z.string()).optional(),
    group: z.array(z.number()).optional(),
    status: z.enum(['0', 'active', 'on_hold', 'disabled', 'expired', 'limited']).default('0').optional(),
    data_limit_min: optionalNonNegativeNumber,
    data_limit_max: optionalNonNegativeNumber,
    expire_after: z.date().optional(),
    expire_before: z.date().optional(),
    online_after: z.date().optional(),
    online_before: z.date().optional(),
  })
  .superRefine((values, ctx) => {
    if (
      !values.no_data_limit &&
      values.data_limit_min !== undefined &&
      values.data_limit_max !== undefined &&
      values.data_limit_min > values.data_limit_max
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['data_limit_max'],
        message: 'Minimum data limit cannot be greater than maximum.',
      })
    }

    if (
      !values.no_expire &&
      values.expire_after !== undefined &&
      values.expire_before !== undefined &&
      values.expire_after.getTime() > values.expire_before.getTime()
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['expire_before'],
        message: 'Expire-after date cannot be later than expire-before date.',
      })
    }

    if (
      values.online_after !== undefined &&
      values.online_before !== undefined &&
      values.online_after.getTime() > values.online_before.getTime()
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['online_before'],
        message: 'Online-after date cannot be later than online-before date.',
      })
    }
  })

export type AdvanceSearchFormValue = z.infer<typeof advanceSearchFormSchema>
