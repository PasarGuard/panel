import { z } from 'zod'

export const adminStatusEditEnum = z.enum(['active', 'disabled'])

export const passwordValidation = z.string().refine(
  value => {
    if (!value) return false // Don't allow empty passwords

    // Check in priority order
    if (value.length < 12) {
      return false
    }
    if ((value.match(/\d/g) || []).length < 2) {
      return false
    }
    if ((value.match(/[A-Z]/g) || []).length < 2) {
      return false
    }
    if ((value.match(/[a-z]/g) || []).length < 2) {
      return false
    }
    return /[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]/.test(value)
  },
  value => {
    // Return specific error message based on the first validation that fails
    if (!value) {
      return { message: 'Password is required' }
    }
    if (value.length < 12) {
      return { message: 'Password must be at least 12 characters long' }
    }
    if ((value.match(/\d/g) || []).length < 2) {
      return { message: 'Password must contain at least 2 digits' }
    }
    if ((value.match(/[A-Z]/g) || []).length < 2) {
      return { message: 'Password must contain at least 2 uppercase letters' }
    }
    if ((value.match(/[a-z]/g) || []).length < 2) {
      return { message: 'Password must contain at least 2 lowercase letters' }
    }
    if (!/[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]/.test(value)) {
      return { message: 'Password must contain at least one special character' }
    }
    return { message: 'Invalid password' }
  },
)

export const adminFormSchema = z
  .object({
    username: z.string().min(1, 'Username is required'),
    password: z.string().optional(),
    passwordConfirm: z.string().optional(),
    role_id: z.number().min(1, 'Role is required'),
    status: adminStatusEditEnum.optional(),
    data_limit: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number().min(0)]).optional(),
    is_disabled: z.boolean().optional(),
    discord_webhook: z.string().optional(),
    sub_domain: z.string().optional(),
    sub_template: z.string().optional(),
    support_url: z.string().optional(),
    telegram_id: z.number().optional(),
    profile_title: z.string().optional(),
    note: z.string().optional(),
    notification_enable: z
      .object({
        create: z.boolean().optional(),
        modify: z.boolean().optional(),
        delete: z.boolean().optional(),
        status_change: z.boolean().optional(),
        reset_data_usage: z.boolean().optional(),
        data_reset_by_next: z.boolean().optional(),
        subscription_revoked: z.boolean().optional(),
      })
      .optional(),
    permission_overrides: z
      .object({
        max_users: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        data_limit_min: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        data_limit_max: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        expire_days_min: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        expire_days_max: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        min_hwid_per_user: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        max_hwid_per_user: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        on_hold_timeout_days_min: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
        on_hold_timeout_days_max: z.union([z.literal('').transform(() => null), z.null(), z.coerce.number()]).optional(),
      })
      .optional(),
  })
  .superRefine((data, ctx) => {
    // Only validate password if it's provided (for editing) or if it's a new admin
    if (data.password || !data.username) {
      if (!data.password) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Password is required',
          path: ['password'],
        })
        return
      }

      // Validate password strength
      const passwordResult = passwordValidation.safeParse(data.password)
      if (!passwordResult.success) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: passwordResult.error.errors[0].message,
          path: ['password'],
        })
        return
      }

      // Validate password confirmation
      if (data.password !== data.passwordConfirm) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Passwords do not match',
          path: ['passwordConfirm'],
        })
      }
    }
  })

export type AdminFormValuesInput = z.input<typeof adminFormSchema>
export type AdminFormValues = z.infer<typeof adminFormSchema>

export const adminPermissionOverridesDefaultValues = {
  max_users: null,
  data_limit_min: null,
  data_limit_max: null,
  expire_days_min: null,
  expire_days_max: null,
  min_hwid_per_user: null,
  max_hwid_per_user: null,
  on_hold_timeout_days_min: null,
  on_hold_timeout_days_max: null,
} as const

export const adminFormDefaultValues: Partial<AdminFormValuesInput> = {
  username: '',
  role_id: 3,
  password: '',
  passwordConfirm: '',
  status: 'active',
  data_limit: null,
  is_disabled: false,
  discord_webhook: '',
  sub_domain: '',
  sub_template: '',
  support_url: '',
  telegram_id: undefined,
  profile_title: '',
  note: '',
  notification_enable: {
    create: true,
    modify: true,
    delete: true,
    status_change: true,
    reset_data_usage: true,
    data_reset_by_next: true,
    subscription_revoked: true,
  },
  permission_overrides: adminPermissionOverridesDefaultValues,
}
