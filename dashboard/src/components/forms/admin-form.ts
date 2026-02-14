import { z } from 'zod'

const passwordValidation = z.string().refine(
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
    is_sudo: z.boolean().default(false),
    is_disabled: z.boolean().optional(),
    discord_webhook: z.string().optional(),
    sub_domain: z.string().optional(),
    sub_template: z.string().optional(),
    support_url: z.string().optional(),
    telegram_id: z.number().optional(),
    profile_title: z.string().optional(),
    discord_id: z.number().optional(),
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

export const adminFormDefaultValues: Partial<AdminFormValuesInput> = {
  username: '',
  is_sudo: false,
  password: '',
  passwordConfirm: '',
  is_disabled: false,
  discord_webhook: '',
  sub_domain: '',
  sub_template: '',
  support_url: '',
  telegram_id: undefined,
  profile_title: '',
  discord_id: undefined,
  notification_enable: {
    create: true,
    modify: true,
    delete: true,
    status_change: true,
    reset_data_usage: true,
    data_reset_by_next: true,
    subscription_revoked: true,
  },
}
